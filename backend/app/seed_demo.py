import json
import secrets

from .database import Base, SessionLocal, engine
from .models import Exam, ExamRoom, User, UserProfile
from .security import hash_password


def seed_demo_data() -> dict:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        authority_email = "authority.demo@local"
        teacher_email = "teacher.demo@local"
        student_email = "student.demo@local"

        authority = db.query(User).filter(User.email == authority_email).first()
        if not authority:
            authority = User(name="Authority Demo", email=authority_email, role="authority")
            db.add(authority)
            db.commit()
            db.refresh(authority)

        authority_profile = db.query(UserProfile).filter(UserProfile.user_id == authority.id).first()
        if not authority_profile:
            authority_profile = UserProfile(
                user_id=authority.id,
                department="Admin",
                institution_id="AUTH-DEMO-001",
                contact_number="0000000000",
                password_hash=hash_password("Authority@123"),
                approval_status="approved",
                is_active=1,
            )
            db.add(authority_profile)
            db.commit()

        teacher = db.query(User).filter(User.email == teacher_email).first()
        if not teacher:
            teacher = User(name="Teacher Demo", email=teacher_email, role="teacher")
            db.add(teacher)
            db.commit()
            db.refresh(teacher)

        teacher_profile = db.query(UserProfile).filter(UserProfile.user_id == teacher.id).first()
        if not teacher_profile:
            teacher_profile = UserProfile(
                user_id=teacher.id,
                department="CSE",
                institution_id="TCH-DEMO-001",
                contact_number="1111111111",
                password_hash=hash_password("Teacher@123"),
                approval_status="approved",
                is_active=1,
                approved_by=authority.id,
            )
            db.add(teacher_profile)
            db.commit()

        student = db.query(User).filter(User.email == student_email).first()
        if not student:
            student = User(name="Student Demo", email=student_email, role="student")
            db.add(student)
            db.commit()
            db.refresh(student)

        student_profile = db.query(UserProfile).filter(UserProfile.user_id == student.id).first()
        if not student_profile:
            student_profile = UserProfile(
                user_id=student.id,
                department="CSE",
                institution_id="STD-DEMO-001",
                contact_number="2222222222",
                password_hash=hash_password("Student@123"),
                approval_status="approved",
                is_active=1,
                approved_by=authority.id,
                assigned_teacher_id=teacher.id,
            )
            db.add(student_profile)
            db.commit()

        existing_exam = (
            db.query(Exam)
            .filter(Exam.created_by == teacher.id, Exam.title == "AI Competition Demo Exam")
            .first()
        )

        if existing_exam:
            exam = existing_exam
        else:
            questions = [
                {
                    "id": "q1",
                    "prompt": "Explain one ethical risk in AI proctoring systems.",
                    "type": "text",
                },
                {
                    "id": "q2",
                    "prompt": "Describe how tab-switch and paste behavior can indicate suspicious activity.",
                    "type": "text",
                },
                {
                    "id": "q3",
                    "prompt": "Why should schools use a suspicion score instead of a binary cheating label?",
                    "type": "text",
                },
            ]
            exam = Exam(
                title="AI Competition Demo Exam",
                duration_minutes=20,
                questions_json=json.dumps(questions),
                created_by=teacher.id,
            )
            db.add(exam)
            db.commit()
            db.refresh(exam)

        room = db.query(ExamRoom).filter(ExamRoom.exam_id == exam.id, ExamRoom.teacher_id == teacher.id).first()
        if not room:
            room = ExamRoom(
                room_id=f"TR{teacher.id}-{secrets.token_hex(3).upper()}",
                teacher_id=teacher.id,
                exam_id=exam.id,
                course_title="AI Competition Demo Exam",
                course_code="AIC-101",
                teacher_name=teacher.name,
            )
            db.add(room)
            db.commit()
            db.refresh(room)

        return {
            "authority_code": "AUTH-DEMO-001",
            "authority_password": "Authority@123",
            "teacher_code": "TCH-DEMO-001",
            "teacher_password": "Teacher@123",
            "student_code": "STD-DEMO-001",
            "student_password": "Student@123",
            "teacher_email": teacher.email,
            "student_email": student.email,
            "exam_id": exam.id,
            "room_id": room.room_id,
        }
    finally:
        db.close()


if __name__ == "__main__":
    result = seed_demo_data()
    print("Demo seed completed")
    print(f"Authority login: {result['authority_code']} / {result['authority_password']}")
    print(f"Teacher login: {result['teacher_code']} / {result['teacher_password']}")
    print(f"Student login: {result['student_code']} / {result['student_password']}")
    print(f"Teacher email: {result['teacher_email']}")
    print(f"Student email: {result['student_email']}")
    print(f"Exam ID: {result['exam_id']}")
    print(f"Room ID: {result['room_id']}")
