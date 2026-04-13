import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BehaviorEvent, Exam, ExamRoom, Submission, User
from ..schemas import (
    StartSubmissionRequest,
    StartSubmissionResponse,
    SubmitRequest,
    SubmitResponse,
)
from ..security import require_role
from ..services.scoring import calculate_suspicion_assessment
from ..services.answer_analysis import (
    calculate_ai_style_risk,
    calculate_similarity_risk,
    fetch_external_ai_classifier_risk,
)
from ..services.scoring import merge_behavior_and_answer_risk
from ..services.audit import log_audit

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("/start", response_model=StartSubmissionResponse)
def start_submission(
    payload: StartSubmissionRequest,
    db: Session = Depends(get_db),
    student: User = Depends(require_role("student")),
):
    room = db.query(ExamRoom).filter(ExamRoom.exam_id == payload.exam_id).first()
    now = datetime.now(timezone.utc)
    if room and room.scheduled_start_at and now < room.scheduled_start_at:
        raise HTTPException(status_code=403, detail="This exam has not started yet")
    if room and room.scheduled_end_at and now > room.scheduled_end_at:
        raise HTTPException(status_code=403, detail="This exam has already ended")

    existing = (
        db.query(Submission)
        .filter(
            Submission.exam_id == payload.exam_id,
            Submission.student_id == student.id,
        )
        .order_by(Submission.id.desc())
        .first()
    )
    if existing:
        if existing.status == "submitted":
            raise HTTPException(status_code=403, detail="You have already attempted this exam once")
        return StartSubmissionResponse(submission_id=existing.id)

    submission = Submission(exam_id=payload.exam_id, student_id=student.id)
    db.add(submission)
    db.commit()
    db.refresh(submission)
    log_audit(
        db,
        user_id=student.id,
        action="start_submission",
        entity_type="submission",
        entity_id=submission.id,
        metadata={"exam_id": payload.exam_id},
    )
    return StartSubmissionResponse(submission_id=submission.id)


@router.post("/{submission_id}/submit", response_model=SubmitResponse)
def submit_exam(
    submission_id: int,
    payload: SubmitRequest,
    db: Session = Depends(get_db),
    student: User = Depends(require_role("student")),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.student_id != student.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if submission.status == "submitted":
        return SubmitResponse(
            submission_id=submission.id,
            suspicion_score=submission.suspicion_score,
            risk_band=submission.risk_band,
        )

    db_events = (
        db.query(BehaviorEvent)
        .filter(BehaviorEvent.submission_id == submission_id)
        .order_by(BehaviorEvent.timestamp_ms.asc())
        .all()
    )
    event_payload = [
        {
            "event_type": item.event_type,
            "timestamp_ms": item.timestamp_ms,
            "metadata": json.loads(item.metadata_json),
        }
        for item in db_events
    ]

    exam = db.query(Exam).filter(Exam.id == submission.exam_id).first()
    question_count = 0
    if exam:
        try:
            question_count = len(json.loads(exam.questions_json))
        except json.JSONDecodeError:
            question_count = 0

    behavior_score, _, behavior_assessment = calculate_suspicion_assessment(
        event_payload,
        payload.time_taken_seconds,
        exam_duration_minutes=exam.duration_minutes if exam else None,
        question_count=question_count or None,
    )

    historical_submissions = (
        db.query(Submission)
        .filter(
            Submission.exam_id == submission.exam_id,
            Submission.id != submission.id,
            Submission.status == "submitted",
        )
        .all()
    )
    historical_answers = []
    for item in historical_submissions:
        try:
            historical_answers.append(json.loads(item.answers_json))
        except json.JSONDecodeError:
            continue

    similarity_risk = calculate_similarity_risk(payload.answers, historical_answers)
    external_ai_risk = fetch_external_ai_classifier_risk(
        " ".join([str(item) for item in payload.answers.values() if str(item).strip()])
    )
    ai_style_risk = calculate_ai_style_risk(
        payload.answers,
        payload.time_taken_seconds,
        events=event_payload,
        external_ai_risk=external_ai_risk,
    )

    suspicion_score, risk_band = merge_behavior_and_answer_risk(
        behavior_score,
        similarity_risk,
        ai_style_risk,
    )

    submission.answers_json = json.dumps(payload.answers)
    submission.time_taken_seconds = payload.time_taken_seconds
    submission.suspicion_score = suspicion_score
    submission.risk_band = risk_band
    submission.status = "submitted"
    submission.submitted_at = datetime.utcnow()
    db.commit()
    log_audit(
        db,
        user_id=student.id,
        action="submit_exam",
        entity_type="submission",
        entity_id=submission.id,
        metadata={
            "suspicion_score": suspicion_score,
            "risk_band": risk_band,
            "behavior_assessment": behavior_assessment,
            "answer_similarity_risk": round(similarity_risk, 4),
            "ai_style_risk": round(ai_style_risk, 4),
        },
    )

    return SubmitResponse(
        submission_id=submission.id,
        suspicion_score=suspicion_score,
        risk_band=risk_band,
        risk_breakdown={
            "behavior": behavior_assessment,
            "answer_similarity_risk": round(similarity_risk, 4),
            "ai_style_risk": round(ai_style_risk, 4),
        },
    )

