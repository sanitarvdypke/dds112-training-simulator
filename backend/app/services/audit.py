from app.models.entities import AuditLog
async def audit(db, user_id, event_type, entity_type=None, entity_id=None, payload=None):
    db.add(AuditLog(user_id=user_id, event_type=event_type, entity_type=entity_type, entity_id=entity_id, payload=payload or {}))
