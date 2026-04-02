from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from fastapi.responses import StreamingResponse

from ..database import get_db
from ..models import (
    AuditLog,
    BehaviorEvent,
    Exam,
    ExamRoom,
    Submission,
    SubmissionQuestionMark,
    SubmissionReview,
    User,
    UserProfile,
)
from ..schemas import (
    AccessUpdateRequest,
    ApproveUserRequest,
    ManualUserCreateRequest,
    PasswordResetRequest,
    UserProfileResponse,
    UserWithProfileResponse,
)
from ..security import get_current_user
from ..security import hash_password
from ..services.audit import log_audit

router = APIRouter(prefix="/management", tags=["management"])


def _build_user_with_profile(user: User, profile: UserProfile) -> UserWithProfileResponse:
    return UserWithProfileResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        profile=UserProfileResponse(
            user_id=user.id,
            department=profile.department,
            user_code=profile.institution_id,
            contact_number=profile.contact_number,
            approval_status=profile.approval_status,
            is_active=profile.is_active == 1,
            assigned_teacher_id=profile.assigned_teacher_id,
        ),
    )


@router.get("/pending", response_model=list[UserWithProfileResponse])
def list_pending_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(User, UserProfile)
        .join(UserProfile, User.id == UserProfile.user_id)
        .filter(UserProfile.approval_status == "pending")
        .all()
    )

    if current_user.role == "authority":
        return [_build_user_with_profile(user, profile) for user, profile in rows if user.role in {"teacher", "student"}]

    if current_user.role == "teacher":
        return [
            _build_user_with_profile(user, profile)
            for user, profile in rows
            if user.role == "student" and profile.assigned_teacher_id == current_user.id
        ]

    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/approve/{user_id}")
def approve_user(
    user_id: int,
    payload: ApproveUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = db.query(User).filter(User.id == user_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not target_user or not profile:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role == "authority":
        if target_user.role not in {"teacher", "student"}:
            raise HTTPException(status_code=400, detail="Authority can approve only teacher/student")
    elif current_user.role == "teacher":
        if not (target_user.role == "student" and profile.assigned_teacher_id == current_user.id):
            raise HTTPException(status_code=403, detail="Teacher can approve only assigned students")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    profile.approval_status = "approved" if payload.approve else "rejected"
    profile.is_active = 1 if payload.approve else 0
    profile.approved_by = current_user.id
    db.commit()

    log_audit(
        db,
        user_id=current_user.id,
        action="approve_user" if payload.approve else "reject_user",
        entity_type="user",
        entity_id=user_id,
        metadata={"target_role": target_user.role},
    )

    return {"status": profile.approval_status}


@router.get("/users", response_model=list[UserWithProfileResponse])
def list_users(
    role: str | None = None,
    user_code: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(User, UserProfile)
        .join(UserProfile, User.id == UserProfile.user_id)
        .filter(UserProfile.approval_status != "rejected")
        .all()
    )
    response = []
    for user, profile in rows:
        if role and user.role != role:
            continue
        if user_code and user_code.lower() not in (profile.institution_id or "").lower():
            continue
        if current_user.role == "authority":
            if user.role in {"authority", "teacher", "student"}:
                response.append(_build_user_with_profile(user, profile))
        elif current_user.role == "teacher":
            if user.role == "student" and profile.assigned_teacher_id == current_user.id:
                response.append(_build_user_with_profile(user, profile))
        else:
            raise HTTPException(status_code=403, detail="Forbidden")
    return response


@router.post("/access/{user_id}")
def update_access(
    user_id: int,
    payload: AccessUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = db.query(User).filter(User.id == user_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not target_user or not profile:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role == "authority":
        if target_user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot modify own authority account")
    elif current_user.role == "teacher":
        if not (target_user.role == "student" and profile.assigned_teacher_id == current_user.id):
            raise HTTPException(status_code=403, detail="Teacher can modify only assigned students")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    profile.is_active = 1 if payload.is_active else 0
    db.commit()
    log_audit(
        db,
        user_id=current_user.id,
        action="enable_access" if payload.is_active else "disable_access",
        entity_type="user",
        entity_id=user_id,
        metadata={"target_role": target_user.role},
    )
    return {"status": "updated", "is_active": payload.is_active}


@router.post("/reset-password/{user_id}")
def reset_user_password(
    user_id: int,
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "authority":
        raise HTTPException(status_code=403, detail="Only authority can reset user passwords")

    target_user = db.query(User).filter(User.id == user_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not target_user or not profile:
        raise HTTPException(status_code=404, detail="User not found")

    profile.password_hash = hash_password(payload.new_password)
    db.commit()

    log_audit(
        db,
        user_id=current_user.id,
        action="reset_user_password",
        entity_type="user",
        entity_id=user_id,
        metadata={"target_role": target_user.role},
    )

    return {"status": "updated", "temporary_password_set": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    target_user = db.query(User).filter(User.id == user_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not target_user or not profile:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role == "authority":
        if target_user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot delete own authority account")
    elif current_user.role == "teacher":
        if not (target_user.role == "student" and profile.assigned_teacher_id == current_user.id):
            raise HTTPException(status_code=403, detail="Teacher can delete only assigned students")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    target_role = target_user.role

    if target_role == "teacher":
        db.query(UserProfile).filter(UserProfile.assigned_teacher_id == target_user.id).update(
            {"assigned_teacher_id": None}, synchronize_session=False
        )
        teacher_exam_ids = [item[0] for item in db.query(Exam.id).filter(Exam.created_by == target_user.id).all()]
        if teacher_exam_ids:
            exam_submission_ids = [
                item[0]
                for item in db.query(Submission.id).filter(Submission.exam_id.in_(teacher_exam_ids)).all()
            ]
            if exam_submission_ids:
                db.query(SubmissionQuestionMark).filter(
                    SubmissionQuestionMark.submission_id.in_(exam_submission_ids)
                ).delete(synchronize_session=False)
                db.query(SubmissionReview).filter(SubmissionReview.submission_id.in_(exam_submission_ids)).delete(
                    synchronize_session=False
                )
                db.query(BehaviorEvent).filter(BehaviorEvent.submission_id.in_(exam_submission_ids)).delete(
                    synchronize_session=False
                )
            db.query(Submission).filter(Submission.exam_id.in_(teacher_exam_ids)).delete(synchronize_session=False)
            db.query(ExamRoom).filter(ExamRoom.exam_id.in_(teacher_exam_ids)).delete(synchronize_session=False)
            db.query(Exam).filter(Exam.id.in_(teacher_exam_ids)).delete(synchronize_session=False)

    submission_ids = [item[0] for item in db.query(Submission.id).filter(Submission.student_id == target_user.id).all()]
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
    db.query(Submission).filter(Submission.student_id == target_user.id).delete(synchronize_session=False)
    db.query(SubmissionReview).filter(SubmissionReview.teacher_id == target_user.id).delete(synchronize_session=False)
    db.query(ExamRoom).filter(ExamRoom.teacher_id == target_user.id).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.user_id == target_user.id).delete(synchronize_session=False)

    db.query(UserProfile).filter(UserProfile.approved_by == target_user.id).update(
        {"approved_by": None}, synchronize_session=False
    )
    db.query(UserProfile).filter(UserProfile.assigned_teacher_id == target_user.id).update(
        {"assigned_teacher_id": None}, synchronize_session=False
    )

    db.query(UserProfile).filter(UserProfile.user_id == target_user.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == target_user.id).delete(synchronize_session=False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not delete user due to linked records")

    log_audit(
        db,
        user_id=current_user.id,
        action="delete_user",
        entity_type="user",
        entity_id=user_id,
        metadata={"target_role": target_role},
    )
    return {"status": "deleted"}


@router.get("/users/{user_id}/student-report.pdf")
def student_report_pdf(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    target_user = db.query(User).filter(User.id == user_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not target_user or not profile:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.role != "student":
        raise HTTPException(status_code=400, detail="Report is available only for student users")

    if current_user.role == "teacher":
        if profile.assigned_teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="Teacher can print only assigned student reports")
    elif current_user.role != "authority":
        raise HTTPException(status_code=403, detail="Forbidden")

    submissions = db.query(Submission).filter(Submission.student_id == target_user.id).order_by(Submission.id.asc()).all()

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 36
    y = height - margin

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, y, "Student Profile and Exam Report")
    y -= 20
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, f"Name: {target_user.name}")
    y -= 14
    pdf.drawString(margin, y, f"User ID: {profile.institution_id}")
    y -= 14
    pdf.drawString(margin, y, f"Department: {profile.department}")
    y -= 14
    pdf.drawString(margin, y, f"Approval: {profile.approval_status}")
    y -= 14
    pdf.drawString(margin, y, f"Access: {'enabled' if profile.is_active == 1 else 'disabled'}")
    y -= 22

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin, y, "Submission History")
    y -= 14
    pdf.setFont("Helvetica", 9)
    if not submissions:
        pdf.drawString(margin, y, "No submissions found")
    else:
        for item in submissions:
            exam = db.query(Exam).filter(Exam.id == item.exam_id).first()
            review = db.query(SubmissionReview).filter(SubmissionReview.submission_id == item.id).first()
            line = (
                f"Submission #{item.id} | Exam: {(exam.title if exam else item.exam_id)} | "
                f"Status: {item.status} | Cheat: {item.suspicion_score} ({item.risk_band}) | "
                f"Marks: {(review.marks if review else '-') }"
            )
            if y < 55:
                pdf.showPage()
                y = height - margin
                pdf.setFont("Helvetica", 9)
            pdf.drawString(margin, y, line[:120])
            y -= 12

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="student_{profile.institution_id}_report.pdf"'
    }
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


@router.post("/create-user", response_model=UserWithProfileResponse)
def create_user_manual(
    payload: ManualUserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "authority":
        if payload.role not in {"teacher", "student"}:
            raise HTTPException(status_code=400, detail="Authority can create only teacher/student")
    elif current_user.role == "teacher":
        if payload.role != "student":
            raise HTTPException(status_code=403, detail="Teacher can create only students")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    if db.query(UserProfile).filter(UserProfile.institution_id == payload.user_code).first():
        raise HTTPException(status_code=400, detail="User ID already exists")

    assigned_teacher_id = payload.teacher_user_id
    if payload.role == "student":
        if current_user.role == "teacher":
            assigned_teacher_id = current_user.id
        if not assigned_teacher_id:
            raise HTTPException(status_code=400, detail="Student requires assigned teacher")
        teacher = db.query(User).filter(User.id == assigned_teacher_id, User.role == "teacher").first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Assigned teacher not found")

    user = User(name=payload.name, email=payload.email, role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = UserProfile(
        user_id=user.id,
        department=payload.department,
        institution_id=payload.user_code,
        contact_number=payload.contact_number,
        password_hash=hash_password(payload.password),
        approval_status="approved" if payload.approve_now else "pending",
        is_active=1 if payload.approve_now else 0,
        approved_by=current_user.id if payload.approve_now else None,
        assigned_teacher_id=assigned_teacher_id if payload.role == "student" else None,
    )
    db.add(profile)
    db.commit()

    log_audit(
        db,
        user_id=current_user.id,
        action="manual_create_user",
        entity_type="user",
        entity_id=user.id,
        metadata={"role": payload.role, "approved": payload.approve_now},
    )

    return _build_user_with_profile(user, profile)