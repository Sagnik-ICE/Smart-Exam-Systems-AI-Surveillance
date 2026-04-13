from sqlalchemy import inspect, text

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .middleware import RateLimitMiddleware
from .routers import analytics, auth, events, exams, management, rooms, submissions, vision
from .settings import settings

Base.metadata.create_all(bind=engine)


def _ensure_exam_room_schedule_columns() -> None:
    inspector = inspect(engine)
    if "exam_rooms" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("exam_rooms")}
    statements = []
    if "scheduled_start_at" not in existing_columns:
        statements.append("ALTER TABLE exam_rooms ADD COLUMN scheduled_start_at TIMESTAMP")
    if "scheduled_end_at" not in existing_columns:
        statements.append("ALTER TABLE exam_rooms ADD COLUMN scheduled_end_at TIMESTAMP")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


_ensure_exam_room_schedule_columns()

app = FastAPI(title="AI Smart Exam System API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(auth.router)
app.include_router(exams.router)
app.include_router(submissions.router)
app.include_router(events.router)
app.include_router(analytics.router)
app.include_router(rooms.router)
app.include_router(management.router)
app.include_router(vision.router)


@app.get("/health")
def health():
    return {"status": "ok"}

