from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(200), unique=True, nullable=False, index=True)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    questions_json = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="in_progress")
    answers_json = Column(Text, nullable=False, default="{}")
    time_taken_seconds = Column(Integer, nullable=False, default=0)
    suspicion_score = Column(Float, nullable=False, default=0)
    risk_band = Column(String(30), nullable=False, default="Safe")
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    events = relationship("BehaviorEvent", back_populates="submission")


class BehaviorEvent(Base):
    __tablename__ = "behavior_events"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False, index=True)
    event_type = Column(String(40), nullable=False)
    timestamp_ms = Column(Integer, nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    submission = relationship("Submission", back_populates="events")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(80), nullable=False)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    department = Column(String(120), nullable=False)
    institution_id = Column(String(80), nullable=False, unique=True, index=True)
    contact_number = Column(String(40), nullable=False)
    password_hash = Column(String(300), nullable=False)
    approval_status = Column(String(20), nullable=False, default="pending")
    is_active = Column(Integer, nullable=False, default=1)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExamRoom(Base):
    __tablename__ = "exam_rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String(40), nullable=False, unique=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    course_title = Column(String(200), nullable=False)
    course_code = Column(String(60), nullable=False)
    teacher_name = Column(String(120), nullable=False)
    scheduled_start_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_end_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SubmissionReview(Base):
    __tablename__ = "submission_reviews"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False, unique=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    marks = Column(Float, nullable=False)
    evaluation_status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SubmissionQuestionMark(Base):
    __tablename__ = "submission_question_marks"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False, index=True)
    question_id = Column(String(80), nullable=False)
    marks = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

