import json
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BehaviorEvent, Submission, User
from ..schemas import BehaviorBatchRequest, ExtensionSiteEventRequest
from ..security import require_role
from ..services.audit import log_audit

router = APIRouter(prefix="/events", tags=["events"])


def _extract_hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").strip().lower()
    except Exception:
        return ""


@router.post("/batch")
def ingest_events(
    payload: BehaviorBatchRequest,
    db: Session = Depends(get_db),
    student: User = Depends(require_role("student")),
):
    submission = db.query(Submission).filter(Submission.id == payload.submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.student_id != student.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if submission.status != "in_progress":
        raise HTTPException(status_code=400, detail="Submission already closed")

    for item in payload.events:
        event = BehaviorEvent(
            submission_id=payload.submission_id,
            event_type=item.event_type,
            timestamp_ms=item.timestamp_ms,
            metadata_json=json.dumps(item.metadata),
        )
        db.add(event)
    db.commit()
    log_audit(
        db,
        user_id=student.id,
        action="ingest_events",
        entity_type="submission",
        entity_id=submission.id,
        metadata={"count": len(payload.events)},
    )

    return {"status": "ok", "ingested": len(payload.events), "received_at": datetime.utcnow()}


@router.post("/extension-site")
def ingest_extension_site_event(
    payload: ExtensionSiteEventRequest,
    db: Session = Depends(get_db),
    student: User = Depends(require_role("student")),
):
    submission = db.query(Submission).filter(Submission.id == payload.submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.student_id != student.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if submission.status != "in_progress":
        raise HTTPException(status_code=400, detail="Submission already closed")

    hostname = (payload.hostname or _extract_hostname(payload.url)).strip().lower()
    event = BehaviorEvent(
        submission_id=payload.submission_id,
        event_type="external_site_opened",
        timestamp_ms=payload.timestamp_ms,
        metadata_json=json.dumps(
            {
                "url": payload.url,
                "hostname": hostname,
                "title": payload.title or "",
                "trigger": payload.trigger or "tab_switch",
                "source": "browser_extension",
            }
        ),
    )
    db.add(event)
    db.commit()

    log_audit(
        db,
        user_id=student.id,
        action="ingest_extension_site_event",
        entity_type="submission",
        entity_id=submission.id,
        metadata={"hostname": hostname, "trigger": payload.trigger or "tab_switch"},
    )

    return {"status": "ok", "event_type": "external_site_opened", "received_at": datetime.utcnow()}

