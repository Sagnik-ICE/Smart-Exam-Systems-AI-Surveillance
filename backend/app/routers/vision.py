"""
Vision analysis router for eye movement detection and gaze tracking.
Processes video frames from students and returns eye movement alerts.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..security import get_current_user
from ..services.eye_tracking import process_student_frame, reset_tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision", tags=["vision-analysis"])


class FrameProcessRequest(BaseModel):
    """Request to process a video frame for eye movement detection."""

    submission_id: int = Field(description="Submission ID for event tracking")
    frame_base64: str = Field(description="Base64-encoded image frame from webcam")


class EyeMovementAlert(BaseModel):
    """Alert for suspicious eye movement or gaze behavior."""

    type: str = Field(description="Alert type (e.g., 'looking_left', 'multiple_faces')")
    severity: str = Field(description="Alert severity: 'low', 'medium', 'high'")
    description: str = Field(description="Human-readable alert description")


class GazeData(BaseModel):
    """Gaze direction and confidence for one eye."""

    direction: str = Field(description="Gaze direction: center|left|right|up|down|up-left|up-right|down-left|down-right")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence of gaze detection")
    iris_ratio_x: float = Field(description="Normalized iris position X (-1.5 to 1.5)")
    iris_ratio_y: float = Field(description="Normalized iris position Y (-1.5 to 1.5)")


class EyeData(BaseModel):
    """Movement and position data for one eye."""

    gaze: GazeData
    blink: bool = Field(description="Whether eye is currently blinking")
    ear: float = Field(ge=0.0, description="Eye Aspect Ratio (blink indicator)")


class FrameProcessResponse(BaseModel):
    """Response from video frame analysis."""

    status: str = Field(description="Processing status: 'success' or 'error'")
    timestamp_ms: int = Field(description="Frame processing timestamp in milliseconds")
    frame_count: int = Field(description="Total frames processed by tracker")
    detections: dict[str, Any] = Field(description="Face and eye detection results")
    alerts: list[EyeMovementAlert] = Field(description="Detected alerts and anomalies")
    metadata: dict[str, Any] = Field(description="Frame processing metadata")
    error: str | None = Field(default=None, description="Error message if processing failed")


@router.post(
    "/process-frame",
    response_model=FrameProcessResponse,
    summary="Process video frame for eye movement detection",
    description="Analyzes a video frame to detect eye movements, gaze direction, blinks, and suspicious behavior",
)
async def process_frame(
    request: FrameProcessRequest,
    current_user = Depends(get_current_user),
) -> FrameProcessResponse:
    """
    Process a single video frame from student webcam.
    
    Detects:
    - Eye gaze direction (center, left, right, up, down, diagonal)
    - Blink patterns (using Eye Aspect Ratio)
    - Multiple faces in frame
    - Face off-screen positioning
    - Sustained looking away (left/right/up for 5+ frames)
    
    Args:
        request: Frame processing request with base64-encoded image
        
    Returns:
        Frame processing result with detections and alerts
        
    Raises:
        HTTPException: If frame processing fails
    """
    try:
        # Process frame with eye tracker
        result = process_student_frame(request.submission_id, request.frame_base64)

        # Convert result to response model
        response = FrameProcessResponse(
            status=result.get("status", "error"),
            timestamp_ms=result.get("timestamp_ms", 0),
            frame_count=result.get("frame_count", 0),
            detections=result.get("detections", {}),
            alerts=[EyeMovementAlert(**alert) for alert in result.get("alerts", [])],
            metadata=result.get("metadata", {}),
            error=result.get("error"),
        )

        return response

    except Exception as error:
        logger.error(f"Frame processing error: {error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process frame",
        ) from error


@router.post(
    "/reset-tracker",
    summary="Reset eye tracker for new session",
    description="Clears all tracking history. Call when exam session ends or new exam starts.",
)
async def reset_eye_tracker(
    submission_id: int | None = Query(default=None, description="Optional submission id to reset a specific tracker"),
    current_user = Depends(get_current_user),
) -> dict[str, str]:
    """
    Reset the eye tracker state (clear history, reset counters).
    Should be called when:
    - New exam session starts
    - Student exits exam
    - Technical issues occur
    
    Args:
        token_data: Verified JWT token data
        
    Returns:
        Confirmation message
    """
    try:
        reset_tracker(submission_id=submission_id)
        return {
            "status": "success",
            "message": "Eye tracker reset successfully",
        }
    except Exception as error:
        logger.error(f"Tracker reset error: {error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset tracker",
        ) from error


@router.get(
    "/health",
    summary="Check vision service health",
    description="Verifies eye tracking service is operational",
)
async def vision_health() -> dict[str, str]:
    """
    Get vision service health status.
    
    Returns:
        Health status
    """
    return {
        "status": "ok",
        "service": "vision-analysis",
        "eye_tracking": "mediapipe",
    }
