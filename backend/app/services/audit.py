import json

from sqlalchemy.orm import Session

from ..models import AuditLog


def log_audit(
    db: Session,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int | None,
    metadata: dict,
) -> None:
    record = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=json.dumps(metadata),
    )
    db.add(record)
    db.commit()
