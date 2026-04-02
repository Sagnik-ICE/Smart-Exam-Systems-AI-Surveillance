from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .middleware import RateLimitMiddleware
from .routers import analytics, auth, events, exams, management, rooms, submissions, vision
from .settings import settings

Base.metadata.create_all(bind=engine)

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

