from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str
    role: str = Field(pattern="^(student|teacher)$")


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    department: str = Field(min_length=2, max_length=120)
    user_code: str = Field(min_length=3, max_length=80)
    role: str = Field(pattern="^(authority|teacher|student)$")
    email: str
    contact_number: str = Field(min_length=5, max_length=40)
    password: str = Field(min_length=8, max_length=80)
    teacher_user_id: int | None = None


class CredentialLoginRequest(BaseModel):
    user_code: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=6, max_length=80)


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str


class UserProfileResponse(BaseModel):
    user_id: int
    department: str
    user_code: str
    contact_number: str
    approval_status: str
    is_active: bool
    assigned_teacher_id: int | None


class UserWithProfileResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    profile: UserProfileResponse


class ProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    department: str = Field(min_length=2, max_length=120)
    contact_number: str = Field(min_length=5, max_length=40)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=80)
    new_password: str = Field(min_length=8, max_length=80)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserWithProfileResponse


class SignupResponse(BaseModel):
    user_id: int
    status: str
    message: str


class Question(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    prompt: str = Field(min_length=3, max_length=2000)
    max_marks: float = Field(default=10, ge=0.1, le=1000)
    type: str = Field(default="text", pattern="^(text|mcq)$")
    options: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_question_type(self):
        if self.type == "mcq":
            cleaned = [item.strip() for item in self.options if item.strip()]
            if len(cleaned) < 2:
                raise ValueError("MCQ questions require at least 2 options")
            if len(cleaned) > 12:
                raise ValueError("MCQ options exceed limit")
            if any(len(item) > 300 for item in cleaned):
                raise ValueError("MCQ option text is too long")
            self.options = cleaned
        else:
            self.options = []
        return self


class ExamCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    duration_minutes: int = Field(default=30, ge=1, le=300)
    questions: list[Question] = Field(min_length=1, max_length=100)


class ExamResponse(BaseModel):
    id: int
    title: str
    duration_minutes: int
    questions: list[Question]


class StartSubmissionRequest(BaseModel):
    exam_id: int = Field(gt=0)


class StartSubmissionResponse(BaseModel):
    submission_id: int


class BehaviorEventIn(BaseModel):
    event_type: str = Field(min_length=2, max_length=40)
    timestamp_ms: int = Field(ge=0, le=10_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BehaviorBatchRequest(BaseModel):
    submission_id: int = Field(gt=0)
    events: list[BehaviorEventIn] = Field(min_length=1, max_length=200)


class ExtensionSiteEventRequest(BaseModel):
    submission_id: int = Field(gt=0)
    url: str = Field(min_length=6, max_length=2000)
    title: str | None = Field(default=None, max_length=300)
    hostname: str | None = Field(default=None, max_length=255)
    trigger: str | None = Field(default="tab_switch", max_length=60)
    timestamp_ms: int = Field(ge=0, le=18_000_000)


class SubmitRequest(BaseModel):
    answers: dict[str, str] = Field(min_length=1, max_length=100)
    time_taken_seconds: int = Field(ge=1, le=18_000)

    @model_validator(mode="after")
    def validate_answer_lengths(self):
        total_chars = 0
        for key, value in self.answers.items():
            if len(key) > 50:
                raise ValueError("Question ID too long")
            if len(value) > 8000:
                raise ValueError("Answer is too long")
            total_chars += len(value)
        if total_chars > 50_000:
            raise ValueError("Total answer payload is too large")
        return self


class SubmitResponse(BaseModel):
    submission_id: int
    suspicion_score: float
    risk_band: str
    risk_breakdown: dict[str, Any] | None = None


class EventSummary(BaseModel):
    tab_hidden: int = 0
    window_blur: int = 0
    paste: int = 0
    keystroke: int = 0


class SubmissionAnalytics(BaseModel):
    submission_id: int
    student_name: str
    status: str
    suspicion_score: float
    risk_band: str
    event_counts: dict[str, int]
    eye_movement_counts: dict[str, int] = Field(default_factory=dict)
    timeline: list[dict[str, Any]]
    risk_breakdown: dict[str, Any] | None = None


class DashboardSummary(BaseModel):
    total_submissions: int
    safe_count: int
    suspicious_count: int
    high_risk_count: int
    avg_suspicion_score: float
    total_paste_events: int
    total_tab_hidden_events: int


class ExamDashboardResponse(BaseModel):
    exam_id: int
    summary: DashboardSummary
    submissions: list[SubmissionAnalytics]


class TeacherExamSummary(BaseModel):
    exam_id: int
    room_id: str
    title: str
    course_code: str
    course_title: str
    total_submissions: int
    submitted_count: int
    status: str
    scheduled_at: datetime | None = None
    scheduled_end_at: datetime | None = None


class SubmissionAnswerRow(BaseModel):
    submission_id: int
    student_id: int
    student_name: str
    student_code: str
    status: str = "submitted"
    answers: dict[str, str]
    suspicion_score: float
    risk_band: str
    event_counts: dict[str, int] = Field(default_factory=dict)
    eye_movement_counts: dict[str, int] = Field(default_factory=dict)
    marks: float | None = None
    evaluation_status: str | None = None
    question_marks: dict[str, float] = Field(default_factory=dict)
    question_max_marks: dict[str, float] = Field(default_factory=dict)


class SubmissionMarkRequest(BaseModel):
    marks: float = Field(ge=0, le=1000)
    evaluation_status: str = Field(pattern="^(pass|fail|pending)$")
    question_marks: dict[str, float] | None = None


class ApproveUserRequest(BaseModel):
    approve: bool = True


class AccessUpdateRequest(BaseModel):
    is_active: bool


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=80)


class ManualUserCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    department: str = Field(min_length=2, max_length=120)
    user_code: str = Field(min_length=3, max_length=80)
    role: str = Field(pattern="^(teacher|student)$")
    email: str
    contact_number: str = Field(min_length=5, max_length=40)
    password: str = Field(min_length=8, max_length=80)
    teacher_user_id: int | None = None
    approve_now: bool = True


class RoomCreateRequest(BaseModel):
    course_name: str = Field(min_length=3, max_length=200)
    course_code: str = Field(min_length=2, max_length=60)
    exam_name: str = Field(min_length=3, max_length=200)
    duration_minutes: int = Field(default=30, ge=1, le=300)
    scheduled_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    questions: list[Question] | None = Field(default=None, max_length=100)
    total_questions: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def ensure_questions(self):
        if (self.scheduled_at is None) != (self.scheduled_end_at is None):
            raise ValueError("Schedule start and end must be provided together")
        if self.scheduled_at and self.scheduled_end_at and self.scheduled_end_at <= self.scheduled_at:
            raise ValueError("Schedule end must be after schedule start")

        if self.questions and len(self.questions) > 0:
            return self

        if self.total_questions:
            self.questions = [
                Question(
                    id=f"q{index + 1}",
                    prompt=f"Question {index + 1}",
                    type="text",
                    options=[],
                )
                for index in range(self.total_questions)
            ]
            return self
        else:
            # Room can be created first and questions can be added later in paper builder.
            self.questions = []
            return self


class ExamPaperUpdateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    duration_minutes: int = Field(default=30, ge=1, le=300)
    questions: list[Question] = Field(min_length=1, max_length=100)


class RoomResponse(BaseModel):
    room_id: str
    teacher_id: int
    teacher_name: str
    course_title: str
    course_code: str
    exam_title: str
    exam_id: int
    scheduled_at: datetime | None = None
    scheduled_end_at: datetime | None = None

