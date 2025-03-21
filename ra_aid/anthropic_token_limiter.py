"""Utilities for handling token limits with Anthropic models."""

from functools import partial
from typing import Any, Dict, List, Optional, Sequence, Tuple
from langchain_core.language_models import BaseChatModel
from ra_aid.config import DEFAULT_MODEL
from ra_aid.model_detection import is_claude_37

from langchain_core.messages import (
    BaseMessage,
    trim_messages,
)
from langchain_core.messages.base import message_to_dict

from ra_aid.anthropic_message_utils import (
    anthropic_trim_messages,
)
from langgraph.prebuilt.chat_agent_executor import AgentState
from litellm import token_counter, get_model_info

from ra_aid.agent_backends.ciayn_agent import CiaynAgent
from ra_aid.database.repositories.config_repository import get_config_repository
from ra_aid.logging_config import get_logger
from ra_aid.models_params import DEFAULT_TOKEN_LIMIT, models_params

logger = get_logger(__name__)


def estimate_messages_tokens(messages: Sequence[BaseMessage]) -> int:
    """Helper function to estimate total tokens in a sequence of messages.

    Args:
        messages: Sequence of messages to count tokens for

    Returns:
        Total estimated token count
    """
    if not messages:
        return 0

    estimate_tokens = CiaynAgent._estimate_tokens
    return sum(estimate_tokens(msg) for msg in messages)


def convert_message_to_litellm_format(message: BaseMessage) -> Dict:
    """Convert a BaseMessage to the format expected by litellm.

    Args:
        message: The BaseMessage to convert

    Returns:
        Dict in litellm format
    """
    message_dict = message_to_dict(message)
    return {
        "role": message_dict["type"],
        "content": message_dict["data"]["content"],
    }


def create_token_counter_wrapper(model: str):
    """Create a wrapper for token counter that handles BaseMessage conversion.

    Args:
        model: The model name to use for token counting

    Returns:
        A function that accepts BaseMessage objects and returns token count
    """

    # Create a partial function that already has the model parameter set
    base_token_counter = partial(token_counter, model=model)

    def wrapped_token_counter(messages: List[BaseMessage]) -> int:
        """Count tokens in a list of messages, converting BaseMessage to dict for litellm token counter usage.

        Args:
            messages: List of BaseMessage objects

        Returns:
            Token count for the messages
        """
        if not messages:
            return 0

        litellm_messages = [convert_message_to_litellm_format(msg) for msg in messages]
        result = base_token_counter(messages=litellm_messages)
        return result

    return wrapped_token_counter


def state_modifier(
    state: AgentState, model: BaseChatModel, max_input_tokens: int = DEFAULT_TOKEN_LIMIT
) -> list[BaseMessage]:
    """Given the agent state and max_tokens, return a trimmed list of messages.

    This uses anthropic_trim_messages which always keeps the first 2 messages.

    Args:
        state: The current agent state containing messages
        model: The language model to use for token counting
        max_input_tokens: Maximum number of tokens to allow (default: DEFAULT_TOKEN_LIMIT)

    Returns:
        list[BaseMessage]: Trimmed list of messages that fits within token limit
    """

    messages = state["messages"]
    if not messages:
        return []

    model_name = get_model_name_from_chat_model(model)
    wrapped_token_counter = create_token_counter_wrapper(model_name)

    result = anthropic_trim_messages(
        messages,
        token_counter=wrapped_token_counter,
        max_tokens=max_input_tokens,
        strategy="last",
        allow_partial=False,
        include_system=True,
        num_messages_to_keep=2,
    )

    if len(result) < len(messages):
        logger.info(
            f"Anthropic Token Limiter Trimmed: {len(messages)} messages → {len(result)} messages"
        )

    return result


def sonnet_35_state_modifier(
    state: AgentState, max_input_tokens: int = DEFAULT_TOKEN_LIMIT
) -> list[BaseMessage]:
    """Given the agent state and max_tokens, return a trimmed list of messages.

    Args:
        state: The current agent state containing messages
        max_tokens: Maximum number of tokens to allow (default: DEFAULT_TOKEN_LIMIT)

    Returns:
        list[BaseMessage]: Trimmed list of messages that fits within token limit
    """
    messages = state["messages"]

    if not messages:
        return []

    first_message = messages[0]
    remaining_messages = messages[1:]
    first_tokens = estimate_messages_tokens([first_message])
    new_max_tokens = max_input_tokens - first_tokens

    trimmed_remaining = trim_messages(
        remaining_messages,
        token_counter=estimate_messages_tokens,
        max_tokens=new_max_tokens,
        strategy="last",
        allow_partial=False,
        include_system=True,
    )

    result = [first_message] + trimmed_remaining

    return result


def get_provider_and_model_for_agent_type(
    config: Dict[str, Any], agent_type: str
) -> Tuple[str, str]:
    """Get the provider and model name for the specified agent type.

    Args:
        config: Configuration dictionary containing provider and model information
        agent_type: Type of agent ("default", "research", or "planner")

    Returns:
        Tuple[str, str]: A tuple containing (provider, model_name)
    """
    if agent_type == "research":
        provider = config.get("research_provider", "") or config.get("provider", "")
        model_name = config.get("research_model", "") or config.get("model", "")
    elif agent_type == "planner":
        provider = config.get("planner_provider", "") or config.get("provider", "")
        model_name = config.get("planner_model", "") or config.get("model", "")
    else:
        provider = config.get("provider", "")
        model_name = config.get("model", "")

    return provider, model_name


def get_model_name_from_chat_model(model: Optional[BaseChatModel]) -> str:
    """Extract the model name from a BaseChatModel instance.

    Args:
        model: The BaseChatModel instance

    Returns:
        str: The model name extracted from the instance, or DEFAULT_MODEL if not found
    """
    if model is None:
        return DEFAULT_MODEL

    if hasattr(model, "model"):
        return model.model
    elif hasattr(model, "model_name"):
        return model.model_name
    else:
        logger.debug(f"Could not extract model name from {model}, using DEFAULT_MODEL")
        return DEFAULT_MODEL


def adjust_claude_37_token_limit(
    max_input_tokens: int, model: Optional[BaseChatModel]
) -> Optional[int]:
    """Adjust token limit for Claude 3.7 models by subtracting max_tokens.

    Args:
        max_input_tokens: The original token limit
        model: The model instance to check

    Returns:
        Optional[int]: Adjusted token limit if model is Claude 3.7, otherwise original limit
    """
    if not max_input_tokens:
        return max_input_tokens

    if model and hasattr(model, "model") and is_claude_37(model.model):
        if hasattr(model, "max_tokens") and model.max_tokens:
            effective_max_input_tokens = max_input_tokens - model.max_tokens
            logger.debug(
                f"Adjusting token limit for Claude 3.7 model: {max_input_tokens} - {model.max_tokens} = {effective_max_input_tokens}"
            )
            return effective_max_input_tokens

    return max_input_tokens


def get_model_token_limit(
    config: Dict[str, Any],
    agent_type: str = "default",
    model: Optional[BaseChatModel] = None,
) -> Optional[int]:
    """Get the token limit for the current model configuration based on agent type.

    Args:
        config: Configuration dictionary containing provider and model information
        agent_type: Type of agent ("default", "research", or "planner")
        model: Optional BaseChatModel instance to check for model-specific attributes

    Returns:
        Optional[int]: The token limit if found, None otherwise
    """
    try:
        # Try to get config from repository for production use
        try:
            config_from_repo = get_config_repository().get_all()
            # If we succeeded, use the repository config instead of passed config
            config = config_from_repo
        except RuntimeError:
            # In tests, this may fail because the repository isn't set up
            # So we'll use the passed config directly
            pass

        provider, model_name = get_provider_and_model_for_agent_type(config, agent_type)

        # Always attempt to get model info from litellm first
        provider_model = model_name if not provider else f"{provider}/{model_name}"

        try:
            model_info = get_model_info(provider_model)
            max_input_tokens = model_info.get("max_input_tokens")
            if max_input_tokens:
                logger.debug(
                    f"Using litellm token limit for {model_name}: {max_input_tokens}"
                )
                return adjust_claude_37_token_limit(max_input_tokens, model)
        except Exception as e:
            logger.debug(
                f"Error getting model info from litellm: {e}, falling back to models_params"
            )

        # Fallback to models_params dict
        # Normalize model name for fallback lookup (e.g. claude-2 -> claude2)
        normalized_name = model_name.replace("-", "")
        provider_tokens = models_params.get(provider, {})
        if normalized_name in provider_tokens:
            max_input_tokens = provider_tokens[normalized_name]["token_limit"]
            logger.debug(
                f"Found token limit for {provider}/{model_name}: {max_input_tokens}"
            )
        else:
            max_input_tokens = None
            logger.debug(f"Could not find token limit for {provider}/{model_name}")

        return adjust_claude_37_token_limit(max_input_tokens, model)

    except Exception as e:
        logger.warning(f"Failed to get model token limit: {e}")
        return None
