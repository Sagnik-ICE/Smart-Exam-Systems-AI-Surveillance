import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BehaviorEvent, Exam, ExamRoom, Submission, SubmissionQuestionMark, SubmissionReview, User, UserProfile
from ..schemas import ExamPaperUpdateRequest, ExamResponse, Question, RoomCreateRequest, RoomResponse
from ..security import get_current_user
from ..services.audit import log_audit

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _delete_exam_payload(db: Session, exam_id: int) -> tuple[list[str], int]:
    room_ids = [item[0] for item in db.query(ExamRoom.room_id).filter(ExamRoom.exam_id == exam_id).all()]
    db.query(ExamRoom).filter(ExamRoom.exam_id == exam_id).delete(synchronize_session=False)

    submission_ids = [row[0] for row in db.query(Submission.id).filter(Submission.exam_id == exam_id).all()]
    if submission_ids:
        db.query(SubmissionQuestionMark).filter(SubmissionQuestionMark.submission_id.in_(submission_ids)).delete(
            synchronize_session=False
        )
        db.query(SubmissionReview).filter(SubmissionReview.submission_id.in_(submission_ids)).delete(
            synchronize_session=False
        )
        db.query(BehaviorEvent).filter(BehaviorEvent.submission_id.in_(submission_ids)).delete(
            synchronize_session=False
        )
        db.query(Submission).filter(Submission.id.in_(submission_ids)).delete(synchronize_session=False)

    db.query(Exam).filter(Exam.id == exam_id).delete(synchronize_session=False)
    return room_ids, len(submission_ids)


def _generate_unique_room_id(db: Session, teacher_id: int) -> str:
    for _ in range(20):
        candidate = f"TR{teacher_id}-{secrets.token_hex(3).upper()}"
        exists = db.query(ExamRoom).filter(ExamRoom.room_id == candidate).first()
        if not exists:
            return candidate
    raise HTTPException(status_code=500, detail="Could not generate unique room id")


@router.post("", response_model=RoomResponse)
def create_room(
    payload: RoomCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can create rooms")

    exam = Exam(
        title=payload.exam_name,
        duration_minutes=payload.duration_minutes,
        questions_json=json.dumps([q.model_dump() for q in payload.questions]),
        created_by=current_user.id,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)

    room_id = _generate_unique_room_id(db, current_user.id)
    room = ExamRoom(
        room_id=room_id,
        teacher_id=current_user.id,
        exam_id=exam.id,
        course_title=payload.course_name,
        course_code=payload.course_code,
        teacher_name=current_user.name,
        scheduled_start_at=payload.scheduled_at,
        scheduled_end_at=payload.scheduled_end_at,
    )
    db.add(room)
    db.commit()
    db.refresh(room)

    log_audit(
        db,
        user_id=current_user.id,
        action="create_room",
        entity_type="room",
        entity_id=room.id,
        metadata={"room_id": room.room_id, "course_code": room.course_code},
    )
    return RoomResponse(
        room_id=room.room_id,
        teacher_id=room.teacher_id,
        teacher_name=room.teacher_name,
        course_title=room.course_title,
        course_code=room.course_code,
        exam_title=exam.title,
        exam_id=room.exam_id,
        scheduled_at=room.scheduled_start_at,
        scheduled_end_at=room.scheduled_end_at,
    )


@router.get("/mine", response_model=list[RoomResponse])
def list_my_rooms(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role == "teacher":
        rooms = db.query(ExamRoom).filter(ExamRoom.teacher_id == current_user.id).all()
    elif current_user.role == "student":
        profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
        if not profile or not profile.assigned_teacher_id:
            return []
        rooms = db.query(ExamRoom).filter(ExamRoom.teacher_id == profile.assigned_teacher_id).all()
    elif current_user.role == "authority":
        rooms = db.query(ExamRoom).all()
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    return [
        RoomResponse(
            room_id=row.room_id,
            teacher_id=row.teacher_id,
            teacher_name=row.teacher_name,
            course_title=row.course_title,
            course_code=row.course_code,
            exam_title=db.query(Exam.title).filter(Exam.id == row.exam_id).scalar() or "",
            exam_id=row.exam_id,
            scheduled_at=row.scheduled_start_at,
            scheduled_end_at=row.scheduled_end_at,
        )
        for row in rooms
    ]


@router.get("/resolve/{room_id}", response_model=RoomResponse)
def resolve_room(room_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    room = db.query(ExamRoom).filter(ExamRoom.room_id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if current_user.role == "student":
        profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
        if profile and profile.assigned_teacher_id and profile.assigned_teacher_id != room.teacher_id:
            raise HTTPException(status_code=403, detail="Student can join only assigned teacher rooms")

    exam = db.query(Exam).filter(Exam.id == room.exam_id).first()

    return RoomResponse(
        room_id=room.room_id,
        teacher_id=room.teacher_id,
        teacher_name=room.teacher_name,
        course_title=room.course_title,
        course_code=room.course_code,
        exam_title=exam.title if exam else "",
        exam_id=room.exam_id,
        scheduled_at=room.scheduled_start_at,
        scheduled_end_at=room.scheduled_end_at,
    )


@router.delete("/{room_id}")
def delete_room(
    room_id: str,
    purge_exam: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(ExamRoom).filter(ExamRoom.room_id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if current_user.role == "teacher" and room.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Teacher can delete only own rooms")
    if current_user.role not in {"teacher", "authority"}:
        raise HTTPException(status_code=403, detail="Forbidden")

    room_db_id = room.id
    target_exam_id = room.exam_id
    db.query(ExamRoom).filter(ExamRoom.room_id == room_id).delete(synchronize_session=False)

    if purge_exam:
        _delete_exam_payload(db, target_exam_id)

    db.commit()
    log_audit(
        db,
        user_id=current_user.id,
        action="delete_room",
        entity_type="room",
        entity_id=room_db_id,
        metadata={"room_id": room_id, "purge_exam": purge_exam, "exam_id": target_exam_id},
    )
    return {"status": "deleted", "purge_exam": purge_exam}


@router.delete("/exam/{exam_id}")
def delete_exam_permanently(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if current_user.role == "teacher" and exam.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Teacher can delete only own exams")
    if current_user.role not in {"teacher", "authority"}:
        raise HTTPException(status_code=403, detail="Forbidden")

    room_ids, submission_count = _delete_exam_payload(db, exam_id)
    db.commit()

    log_audit(
        db,
        user_id=current_user.id,
        action="delete_exam_permanent",
        entity_type="exam",
        entity_id=exam_id,
        metadata={"exam_id": exam_id, "room_ids": room_ids, "submission_count": submission_count},
    )
    return {"status": "deleted", "exam_id": exam_id, "room_ids": room_ids}


@router.get("/{room_id}/paper", response_model=ExamResponse)
def get_room_paper(room_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    room = db.query(ExamRoom).filter(ExamRoom.room_id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if current_user.role not in {"teacher", "authority"}:
        raise HTTPException(status_code=403, detail="Forbidden")
    if current_user.role == "teacher" and room.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    exam = db.query(Exam).filter(Exam.id == room.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        questions=[Question(**item) for item in json.loads(exam.questions_json)],
    )


@router.put("/{room_id}/paper", response_model=ExamResponse)
def update_room_paper(
    room_id: str,
    payload: ExamPaperUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(ExamRoom).filter(ExamRoom.room_id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if current_user.role != "teacher" or room.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the room teacher can edit the paper")

    exam = db.query(Exam).filter(Exam.id == room.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    exam.title = payload.title
    exam.duration_minutes = payload.duration_minutes
    exam.questions_json = json.dumps([q.model_dump() for q in payload.questions])
    db.commit()

    log_audit(
        db,
        user_id=current_user.id,
        action="update_exam_paper",
        entity_type="exam",
        entity_id=exam.id,
        metadata={"room_id": room.room_id, "question_count": len(payload.questions)},
    )

    return ExamResponse(
        id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        questions=[Question(**item) for item in json.loads(exam.questions_json)],
    )