#!/usr/bin/env python3
"""
API v1 Session Endpoints.

This module provides RESTful API endpoints for managing sessions.
It implements routes for creating, listing, and retrieving sessions
with proper validation and error handling.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
import peewee
from pydantic import BaseModel, Field

from ra_aid.database.repositories.session_repository import SessionRepository, get_session_repository
from ra_aid.database.pydantic_models import SessionModel

# Create API router
router = APIRouter(
    prefix="/v1/sessions",
    tags=["sessions"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Session not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Validation error"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Database error"},
    },
)


class PaginatedResponse(BaseModel):
    """
    Pydantic model for paginated API responses.
    
    This model provides a standardized format for API responses that include
    pagination, with a total count and the requested items.
    
    Attributes:
        total: The total number of items available
        items: List of items for the current page
        limit: The limit parameter that was used
        offset: The offset parameter that was used
    """
    total: int
    items: List[Any]
    limit: int
    offset: int


class CreateSessionRequest(BaseModel):
    """
    Pydantic model for session creation requests.
    
    This model provides validation for creating new sessions.
    
    Attributes:
        metadata: Optional dictionary of additional metadata to store with the session
    """
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional dictionary of additional metadata to store with the session"
    )


class PaginatedSessionResponse(PaginatedResponse):
    """
    Pydantic model for paginated session responses.
    
    This model specializes the generic PaginatedResponse for SessionModel items.
    
    Attributes:
        items: List of SessionModel items for the current page
    """
    items: List[SessionModel]


# Dependency to get the session repository
def get_repository() -> SessionRepository:
    """
    Get the SessionRepository instance.
    
    This function is used as a FastAPI dependency and can be overridden
    in tests using dependency_overrides.
    
    Returns:
        SessionRepository: The repository instance
    """
    return get_session_repository()


@router.get(
    "",
    response_model=PaginatedSessionResponse,
    summary="List sessions",
    description="Get a paginated list of sessions",
)
async def list_sessions(
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of sessions to return"),
    repo: SessionRepository = Depends(get_repository),
) -> PaginatedSessionResponse:
    """
    Get a paginated list of sessions.
    
    Args:
        offset: Number of sessions to skip (default: 0)
        limit: Maximum number of sessions to return (default: 10)
        repo: SessionRepository dependency injection
        
    Returns:
        PaginatedSessionResponse: Response with paginated sessions
        
    Raises:
        HTTPException: With a 500 status code if there's a database error
    """
    try:
        sessions, total = repo.get_all(offset=offset, limit=limit)
        return PaginatedSessionResponse(
            total=total,
            items=sessions,
            limit=limit,
            offset=offset,
        )
    except peewee.DatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )


@router.get(
    "/{session_id}",
    response_model=SessionModel,
    summary="Get session",
    description="Get a specific session by ID",
)
async def get_session(
    session_id: int,
    repo: SessionRepository = Depends(get_repository),
) -> SessionModel:
    """
    Get a specific session by ID.
    
    Args:
        session_id: The ID of the session to retrieve
        repo: SessionRepository dependency injection
        
    Returns:
        SessionModel: The requested session
        
    Raises:
        HTTPException: With a 404 status code if the session is not found
        HTTPException: With a 500 status code if there's a database error
    """
    try:
        session = repo.get(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found",
            )
        return session
    except peewee.DatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )


@router.post(
    "",
    response_model=SessionModel,
    status_code=status.HTTP_201_CREATED,
    summary="Create session",
    description="Create a new session",
)
async def create_session(
    request: Optional[CreateSessionRequest] = None,
    repo: SessionRepository = Depends(get_repository),
) -> SessionModel:
    """
    Create a new session.
    
    Args:
        request: Optional request body with session metadata
        repo: SessionRepository dependency injection
        
    Returns:
        SessionModel: The newly created session
        
    Raises:
        HTTPException: With a 500 status code if there's a database error
    """
    try:
        metadata = request.metadata if request else None
        return repo.create_session(metadata=metadata)
    except peewee.DatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )