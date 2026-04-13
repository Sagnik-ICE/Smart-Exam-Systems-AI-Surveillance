from collections import defaultdict
import csv
from datetime import datetime, timezone
import io
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
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
    DashboardSummary,
    ExamDashboardResponse,
    SubmissionAnswerRow,
    SubmissionMarkRequest,
    TeacherExamSummary,
)
from ..security import require_role
from ..settings import settings
from ..services.scoring import calculate_suspicion_assessment

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _build_exam_dashboard(exam_id: int, db: Session, teacher: User) -> ExamDashboardResponse:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.created_by != teacher.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    submissions = db.query(Submission).filter(Submission.exam_id == exam_id).all()
    if not submissions:
        raise HTTPException(status_code=404, detail="No submissions for this exam")

    results = []
    safe_count = 0
    suspicious_count = 0
    high_risk_count = 0
    total_score = 0.0
    total_paste = 0
    total_tab_hidden = 0
    try:
        question_count = len(json.loads(exam.questions_json))
    except json.JSONDecodeError:
        question_count = 0

    for submission in submissions:
        student = db.query(User).filter(User.id == submission.student_id).first()
        events = db.query(BehaviorEvent).filter(BehaviorEvent.submission_id == submission.id).all()

        event_counts = defaultdict(int)
        eye_movement_counts = {
            "looking_left": 0,
            "looking_right": 0,
            "looking_up": 0,
            "looking_down": 0,
        }
        timeline = []
        for event in events:
            event_counts[event.event_type] += 1
            try:
                metadata = json.loads(event.metadata_json)
            except json.JSONDecodeError:
                metadata = {}
            if event.event_type == "eye_movement_alert":
                alert_type = str(metadata.get("eye_alert_type") or metadata.get("alert_type") or "").lower()
                if alert_type in eye_movement_counts:
                    eye_movement_counts[alert_type] += 1
            timeline.append(
                {
                    "event_type": event.event_type,
                    "type": event.event_type,
                    "timestamp_ms": event.timestamp_ms,
                    "metadata": metadata,
                }
            )

        calculated_score, calculated_band, risk_breakdown = calculate_suspicion_assessment(
            timeline,
            submission.time_taken_seconds or max(1, int((timeline[-1]["timestamp_ms"] / 1000) if timeline else 1)),
            exam_duration_minutes=exam.duration_minutes,
            question_count=question_count or None,
        )

        display_score = submission.suspicion_score
        display_band = submission.risk_band
        if submission.status != "submitted":
            display_score = calculated_score
            display_band = calculated_band

        total_score += display_score
        total_paste += event_counts.get("paste", 0)
        total_tab_hidden += event_counts.get("tab_hidden", 0) + event_counts.get("window_blur", 0)
        if display_band == "Safe":
            safe_count += 1
        elif display_band == "Suspicious":
            suspicious_count += 1
        else:
            high_risk_count += 1

        results.append(
            {
                "submission_id": submission.id,
                "student_name": student.name if student else "Unknown",
                "status": submission.status,
                "suspicion_score": display_score,
                "risk_band": display_band,
                "event_counts": dict(event_counts),
                "eye_movement_counts": eye_movement_counts,
                "timeline": sorted(timeline, key=lambda item: item["timestamp_ms"]),
                "risk_breakdown": risk_breakdown,
            }
        )

    summary = DashboardSummary(
        total_submissions=len(submissions),
        safe_count=safe_count,
        suspicious_count=suspicious_count,
        high_risk_count=high_risk_count,
        avg_suspicion_score=round(total_score / len(submissions), 2),
        total_paste_events=total_paste,
        total_tab_hidden_events=total_tab_hidden,
    )

    return ExamDashboardResponse(
        exam_id=exam_id,
        summary=summary,
        submissions=sorted(results, key=lambda row: row["suspicion_score"], reverse=True),
    )


@router.get("/exam/{exam_id}")
def exam_dashboard(
    exam_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher")),
) -> ExamDashboardResponse:
    return _build_exam_dashboard(exam_id=exam_id, db=db, teacher=teacher)


@router.get("/exam/{exam_id}/export.csv")
def export_exam_dashboard_csv(
    exam_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher")),
):
    dashboard = _build_exam_dashboard(exam_id=exam_id, db=db, teacher=teacher)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "submission_id",
            "student_name",
            "status",
            "suspicion_score",
            "risk_band",
            "paste_events",
            "tab_hidden_events",
            "window_blur_events",
            "keystroke_events",
        ]
    )
    for row in dashboard.submissions:
        writer.writerow(
            [
                row.submission_id,
                row.student_name,
                row.status,
                row.suspicion_score,
                row.risk_band,
                row.event_counts.get("paste", 0),
                row.event_counts.get("tab_hidden", 0),
                row.event_counts.get("window_blur", 0),
                row.event_counts.get("keystroke", 0),
            ]
        )

    output.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="exam_{exam_id}_report.csv"'}
    return StreamingResponse(output, media_type="text/csv", headers=headers)


@router.get("/exam/{exam_id}/export.pdf")
def export_exam_dashboard_pdf(
    exam_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher")),
):
    dashboard = _build_exam_dashboard(exam_id=exam_id, db=db, teacher=teacher)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 36
    y = height - margin

    # Header band
    pdf.setFillColor(colors.HexColor("#0B3954"))
    pdf.rect(0, height - 90, width, 90, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin, height - 45, settings.report_brand_name)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(margin, height - 64, f"Integrity Analytics Report - Exam {exam_id}")

    y = height - 112

    # Summary KPI cards
    summary = dashboard.summary
    cards = [
        ("Submissions", str(summary.total_submissions)),
        ("Avg Suspicion", str(summary.avg_suspicion_score)),
        ("Safe/Suspicious/High", f"{summary.safe_count}/{summary.suspicious_count}/{summary.high_risk_count}"),
        ("Paste/Tab Events", f"{summary.total_paste_events}/{summary.total_tab_hidden_events}"),
    ]
    card_width = (width - (margin * 2) - 18) / 2
    card_height = 46

    for idx, (label, value) in enumerate(cards):
        col = idx % 2
        row = idx // 2
        x = margin + col * (card_width + 18)
        y_card = y - row * (card_height + 10)

        pdf.setFillColor(colors.HexColor("#F4F8FB"))
        pdf.setStrokeColor(colors.HexColor("#D7E3EE"))
        pdf.roundRect(x, y_card - card_height, card_width, card_height, 6, fill=1, stroke=1)

        pdf.setFillColor(colors.HexColor("#486581"))
        pdf.setFont("Helvetica", 8)
        pdf.drawString(x + 10, y_card - 14, label)
        pdf.setFillColor(colors.HexColor("#102A43"))
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x + 10, y_card - 30, value)

    y -= 115

    # Judge snapshot section for fast review.
    pdf.setFillColor(colors.HexColor("#F7FAFC"))
    pdf.setStrokeColor(colors.HexColor("#D9E2EC"))
    snapshot_h = 86
    pdf.roundRect(margin, y - snapshot_h, width - (margin * 2), snapshot_h, 8, fill=1, stroke=1)

    pdf.setFillColor(colors.HexColor("#102A43"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin + 10, y - 16, "Judge Snapshot")
    pdf.setFont("Helvetica", 8)

    top_three = dashboard.submissions[:3]
    for idx, row in enumerate(top_three):
        snapshot_line = (
            f"{idx + 1}. {row.student_name} | score {row.suspicion_score} | {row.risk_band} | "
            f"paste {row.event_counts.get('paste', 0)} | tab+blur "
            f"{row.event_counts.get('tab_hidden', 0) + row.event_counts.get('window_blur', 0)}"
        )
        pdf.drawString(margin + 10, y - 32 - (idx * 14), snapshot_line[:126])

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.setFillColor(colors.HexColor("#627D98"))
    pdf.setFont("Helvetica", 7)
    pdf.drawRightString(width - margin - 8, y - snapshot_h + 10, f"Generated: {generated_at}")

    y -= snapshot_h + 16

    # Section title
    pdf.setFillColor(colors.HexColor("#102A43"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin, y, "Submission Breakdown")
    y -= 14

    bar_width = 180

    for row in dashboard.submissions:
        if y < 72:
            pdf.showPage()
            y = height - margin
            pdf.setFont("Helvetica-Bold", 11)
            pdf.setFillColor(colors.HexColor("#102A43"))
            pdf.drawString(margin, y, "Submission Breakdown (cont.)")
            y -= 16

        risk_color = colors.HexColor("#17A46B")
        if row.risk_band == "Suspicious":
            risk_color = colors.HexColor("#D09A1D")
        elif row.risk_band == "High Risk":
            risk_color = colors.HexColor("#CF3F4F")

        info_line = (
            f"#{row.submission_id}  {row.student_name}  [{row.risk_band}]  "
            f"paste:{row.event_counts.get('paste', 0)} tab:{row.event_counts.get('tab_hidden', 0)} "
            f"blur:{row.event_counts.get('window_blur', 0)}"
        )
        pdf.setFillColor(colors.HexColor("#243B53"))
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin, y, info_line[:120])

        track_x = width - margin - bar_width
        track_y = y - 8
        pdf.setFillColor(colors.HexColor("#E6EEF5"))
        pdf.roundRect(track_x, track_y, bar_width, 8, 4, fill=1, stroke=0)

        fill_w = max(2, min(bar_width, (row.suspicion_score / 100.0) * bar_width))
        pdf.setFillColor(risk_color)
        pdf.roundRect(track_x, track_y, fill_w, 8, 4, fill=1, stroke=0)

        pdf.setFillColor(colors.HexColor("#102A43"))
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawRightString(track_x - 6, y, f"{row.suspicion_score}")

        y -= 18

    # Footer
    pdf.setFillColor(colors.HexColor("#627D98"))
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(width - margin, 24, f"Generated by {settings.report_brand_name}")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    headers = {"Content-Disposition": f'attachment; filename="exam_{exam_id}_report.pdf"'}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


@router.get("/teacher/exams", response_model=list[TeacherExamSummary])
def teacher_exams_overview(db: Session = Depends(get_db), teacher: User = Depends(require_role("teacher"))):
    exams = db.query(Exam).filter(Exam.created_by == teacher.id).order_by(Exam.created_at.desc()).all()
    room_map = {room.exam_id: room for room in db.query(ExamRoom).filter(ExamRoom.teacher_id == teacher.id).all()}
    now = datetime.now(timezone.utc)

    output = []
    for exam in exams:
        room = room_map.get(exam.id)
        submissions = db.query(Submission).filter(Submission.exam_id == exam.id).all()
        total = len(submissions)
        submitted = len([item for item in submissions if item.status == "submitted"])
        status = "active"
        if total > 0 and submitted == total:
            status = "completed"
        elif room and room.scheduled_start_at and now < room.scheduled_start_at:
            status = "upcoming"
        elif room and room.scheduled_end_at and now > room.scheduled_end_at:
            status = "closed"

        output.append(
            TeacherExamSummary(
                exam_id=exam.id,
                room_id=room.room_id if room else "Room removed",
                title=exam.title,
                course_code=room.course_code if room else "-",
                course_title=room.course_title if room else "Unassigned",
                total_submissions=total,
                submitted_count=submitted,
                status=status,
                scheduled_at=room.scheduled_start_at if room else None,
                scheduled_end_at=room.scheduled_end_at if room else None,
            )
        )
    return output


@router.get("/exam/{exam_id}/answers", response_model=list[SubmissionAnswerRow])
def exam_answer_status(
    exam_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher")),
):
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    rows = []
    question_max_marks = {}
    try:
        parsed_questions = json.loads(exam.questions_json)
        question_count = len(parsed_questions)
        for index, question in enumerate(parsed_questions):
            question_id = str(question.get("id") or f"q{index + 1}")
            try:
                max_marks = float(question.get("max_marks", 10))
            except (TypeError, ValueError):
                max_marks = 10.0
            question_max_marks[question_id] = max(0.1, max_marks)
    except json.JSONDecodeError:
        question_count = 0

    submissions = (
        db.query(Submission)
        .filter(Submission.exam_id == exam_id)
        .order_by(Submission.id.asc())
        .all()
    )
    for submission in submissions:
        student = db.query(User).filter(User.id == submission.student_id).first()
        profile = db.query(UserProfile).filter(UserProfile.user_id == submission.student_id).first()
        review = db.query(SubmissionReview).filter(SubmissionReview.submission_id == submission.id).first()
        qmark_rows = (
            db.query(SubmissionQuestionMark)
            .filter(SubmissionQuestionMark.submission_id == submission.id)
            .all()
        )
        answers = {}
        try:
            answers = json.loads(submission.answers_json)
        except json.JSONDecodeError:
            answers = {}

        event_rows = (
            db.query(BehaviorEvent)
            .filter(BehaviorEvent.submission_id == submission.id)
            .order_by(BehaviorEvent.timestamp_ms.asc())
            .all()
        )
        event_counts = defaultdict(int)
        eye_movement_counts = {
            "looking_left": 0,
            "looking_right": 0,
            "looking_up": 0,
            "looking_down": 0,
        }
        timeline = []
        for event in event_rows:
            event_counts[event.event_type] += 1
            try:
                metadata = json.loads(event.metadata_json)
            except json.JSONDecodeError:
                metadata = {}
            if event.event_type == "eye_movement_alert":
                alert_type = str(metadata.get("eye_alert_type") or metadata.get("alert_type") or "").lower()
                if alert_type in eye_movement_counts:
                    eye_movement_counts[alert_type] += 1
            timeline.append(
                {
                    "event_type": event.event_type,
                    "timestamp_ms": event.timestamp_ms,
                    "metadata": metadata,
                }
            )

        display_score = submission.suspicion_score
        display_band = submission.risk_band
        if submission.status != "submitted":
            display_score, display_band, _ = calculate_suspicion_assessment(
                timeline,
                max(1, int((timeline[-1]["timestamp_ms"] / 1000) if timeline else 1)),
                exam_duration_minutes=exam.duration_minutes,
                question_count=question_count or None,
            )

        rows.append(
            SubmissionAnswerRow(
                submission_id=submission.id,
                student_id=submission.student_id,
                student_name=student.name if student else "Unknown",
                student_code=profile.institution_id if profile else f"ST-{submission.student_id}",
                status=submission.status,
                answers=answers,
                suspicion_score=display_score,
                risk_band=display_band,
                event_counts=dict(event_counts),
                eye_movement_counts=eye_movement_counts,
                marks=review.marks if review else None,
                evaluation_status=review.evaluation_status if review else None,
                question_marks={item.question_id: item.marks for item in qmark_rows},
                question_max_marks=question_max_marks,
            )
        )
    return rows


@router.post("/submission/{submission_id}/mark")
def mark_submission(
    submission_id: int,
    payload: SubmissionMarkRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher")),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    exam = db.query(Exam).filter(Exam.id == submission.exam_id).first()
    if not exam or exam.created_by != teacher.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    review = db.query(SubmissionReview).filter(SubmissionReview.submission_id == submission_id).first()
    calculated_total = payload.marks
    question_max_marks = {}

    try:
        parsed_questions = json.loads(exam.questions_json)
    except json.JSONDecodeError:
        parsed_questions = []

    for index, question in enumerate(parsed_questions):
        question_id = str(question.get("id") or f"q{index + 1}")
        try:
            max_marks = float(question.get("max_marks", 10))
        except (TypeError, ValueError):
            max_marks = 10.0
        question_max_marks[question_id] = max(0.1, max_marks)

    max_total_marks = round(sum(question_max_marks.values()), 2)

    if payload.question_marks:
        normalized_question_marks = {}
        for question_id, mark_value in payload.question_marks.items():
            mark = float(mark_value or 0)
            if mark < 0:
                raise HTTPException(status_code=400, detail=f"Marks cannot be negative for {question_id}")

            allowed_max = question_max_marks.get(str(question_id), 0)
            if mark > allowed_max:
                raise HTTPException(
                    status_code=400,
                    detail=f"Marks for {question_id} cannot exceed fixed max marks ({allowed_max:g})",
                )

            normalized_question_marks[str(question_id)] = mark

        calculated_total = round(sum(normalized_question_marks.values()), 2)

        db.query(SubmissionQuestionMark).filter(SubmissionQuestionMark.submission_id == submission_id).delete(
            synchronize_session=False
        )
        for question_id, mark_value in normalized_question_marks.items():
            db.add(
                SubmissionQuestionMark(
                    submission_id=submission_id,
                    question_id=str(question_id),
                    marks=float(mark_value or 0),
                )
            )
    elif calculated_total > max_total_marks:
        raise HTTPException(
            status_code=400,
            detail=f"Total marks cannot exceed fixed paper marks ({max_total_marks:g})",
        )
    if not review:
        review = SubmissionReview(
            submission_id=submission_id,
            teacher_id=teacher.id,
            marks=calculated_total,
            evaluation_status=payload.evaluation_status,
        )
        db.add(review)
    else:
        review.marks = calculated_total
        review.evaluation_status = payload.evaluation_status

    db.commit()
    return {
        "status": "saved",
        "total_marks": calculated_total,
        "marks": review.marks,
        "evaluation_status": review.evaluation_status
    }


@router.get("/exam/{exam_id}/result-sheet.pdf")
def exam_result_sheet_pdf(
    exam_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher")),
):
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    room = db.query(ExamRoom).filter(ExamRoom.exam_id == exam.id).first()
    answers = exam_answer_status(exam_id=exam_id, db=db, teacher=teacher)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 36
    y = height - margin

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(margin, y, "Daffodil International University")
    y -= 20
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, f"Exam Name: {exam.title}")
    y -= 14
    pdf.drawString(margin, y, f"Course Title: {room.course_title if room else 'N/A'}")
    y -= 14
    pdf.drawString(margin, y, f"Course Code: {room.course_code if room else 'N/A'}")
    y -= 14
    pdf.drawString(margin, y, f"Room ID: {room.room_id if room else 'N/A'}")
    y -= 24

    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(margin, y, "ID")
    pdf.drawString(margin + 90, y, "Name")
    pdf.drawString(margin + 245, y, "Marks")
    pdf.drawString(margin + 310, y, "Status")
    pdf.drawString(margin + 385, y, "Cheat Score")
    y -= 12
    pdf.line(margin, y, width - margin, y)
    y -= 10

    pdf.setFont("Helvetica", 8)
    for row in answers:
        if y < 55:
            pdf.showPage()
            y = height - margin
            pdf.setFont("Helvetica", 8)
        pdf.drawString(margin, y, str(row.student_code)[:15])
        pdf.drawString(margin + 90, y, row.student_name[:25])
        pdf.drawString(margin + 245, y, str(row.marks if row.marks is not None else "-"))
        pdf.drawString(margin + 310, y, str(row.evaluation_status or "pending"))
        pdf.drawString(margin + 385, y, str(row.suspicion_score))
        y -= 12

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="exam_{exam_id}_result_sheet.pdf"'}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


@router.get("/submission/{submission_id}/detail.pdf")
def submission_detail_pdf(
    submission_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher")),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    exam = db.query(Exam).filter(Exam.id == submission.exam_id).first()
    if not exam or exam.created_by != teacher.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    student = db.query(User).filter(User.id == submission.student_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == submission.student_id).first()
    review = db.query(SubmissionReview).filter(SubmissionReview.submission_id == submission_id).first()
    try:
        answers = json.loads(submission.answers_json)
    except json.JSONDecodeError:
        answers = {}

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 36
    y = height - margin

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, y, "Student Exam Details")
    y -= 18
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, f"Student: {student.name if student else 'Unknown'}")
    y -= 14
    pdf.drawString(margin, y, f"ID: {profile.institution_id if profile else submission.student_id}")
    y -= 14
    pdf.drawString(margin, y, f"Exam: {exam.title}")
    y -= 14
    pdf.drawString(margin, y, f"Cheat Score: {submission.suspicion_score} ({submission.risk_band})")
    y -= 14
    pdf.drawString(margin, y, f"Marks: {review.marks if review else '-'}")
    y -= 20

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin, y, "Answers")
    y -= 14
    pdf.setFont("Helvetica", 9)
    for key, value in answers.items():
        if y < 70:
            pdf.showPage()
            y = height - margin
            pdf.setFont("Helvetica", 9)
        pdf.drawString(margin, y, f"{key}: {str(value)[:100]}")
        y -= 12

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="submission_{submission_id}_detail.pdf"'}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


