import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Exam, User
from ..schemas import ExamCreateRequest, ExamResponse, Question
from ..security import require_role
from ..services.audit import log_audit

router = APIRouter(prefix="/exams", tags=["exams"])


@router.post("", response_model=ExamResponse)
def create_exam(
    payload: ExamCreateRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher")),
):
    exam = Exam(
        title=payload.title,
        duration_minutes=payload.duration_minutes,
        questions_json=json.dumps([q.model_dump() for q in payload.questions]),
        created_by=teacher.id,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    log_audit(
        db,
        user_id=teacher.id,
        action="create_exam",
        entity_type="exam",
        entity_id=exam.id,
        metadata={"title": exam.title, "duration_minutes": exam.duration_minutes},
    )
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        questions=[Question(**item) for item in json.loads(exam.questions_json)],
    )


@router.get("/{exam_id}", response_model=ExamResponse)
def get_exam(exam_id: int, db: Session = Depends(get_db), _: User = Depends(require_role("student"))):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        questions=[Question(**item) for item in json.loads(exam.questions_json)],
    )

