from rich.console import Console
from rich.rule import Rule
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()

def print_stage_header(stage: str) -> None:
    """Print a stage header with stage-specific styling and icons.
    
    Args:
        stage: The stage name to print (automatically formatted to Title Case)
    """
    # Define stage icons mapping
    icons = {
        'research stage': '🔎',
        'planning stage': '📝',
        'implementation stage': '🛠️', 
        'task completed': '✅',
        'debug stage': '🐛',
        'testing stage': '🧪',
        'research summary': '📋',
        'research subtasks': '📚',
        'skipping implementation stage': '⏭️'
    }

    # Format stage name to Title Case and normalize for mapping lookup
    stage_title = stage.title()
    stage_key = stage.lower()
    
    # Get appropriate icon with fallback
    icon = icons.get(stage_key, '🚀')
    
    # Create styled rule with icon
    rule_content = f"{icon} {stage_title} {icon}"
    console.print(Rule(rule_content, style="green bold"))

def print_task_header(task: str) -> None:
    """Print a task header with yellow styling and wrench emoji. Content is rendered as Markdown.
    
    Args:
        task: The task text to print (supports Markdown formatting)
    """
    console.print(Panel(Markdown(task), title="🔧 Task", border_style="yellow bold"))
