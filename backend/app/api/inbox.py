import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app.api.deps import require_roles
from app.db.session import get_db
from app.models.entities import UserRole, TrainingSession, SessionStatus, GroupMember, Scenario, EventCard, CallSession, StudentAction
from app.services.dds_card import action_state
from app.api.sessions import call_state

router = APIRouter(prefix="/sessions", tags=["inbox"])

@router.get("/inbox")
async def inbox(db=Depends(get_db), user=Depends(require_roles(UserRole.STUDENT))):
    sessions = (await db.scalars(select(TrainingSession).where(TrainingSession.status.in_([SessionStatus.RUNNING, SessionStatus.COMPLETED])).order_by(TrainingSession.created_at.desc()))).all()
    memberships = set((await db.scalars(select(GroupMember.group_id).where(GroupMember.user_id == user.id))).all())
    sessions = [s for s in sessions if not s.group_id or s.group_id in memberships]
    scenario_ids = {uuid.UUID(sid) for session in sessions for sid in session.scenario_ids}
    if not scenario_ids: return []
    scenarios = {s.id: s for s in (await db.scalars(select(Scenario).where(Scenario.id.in_(scenario_ids)))).all()}
    calls = (await db.execute(select(CallSession, EventCard).join(EventCard, CallSession.event_card_id == EventCard.id).where(CallSession.student_id == user.id))).all()
    by_scenario = {(c.training_session_id, card.scenario_id): (c, card) for c, card in calls}
    active = {c.training_session_id: str(c.id) for c, _ in calls if not c.completed_at}
    call_ids = [c.id for c, _ in calls]
    actions = (await db.scalars(select(StudentAction).where(StudentAction.call_session_id.in_(call_ids)).order_by(StudentAction.sequence_no))).all() if call_ids else []
    histories = {}
    for action in actions: histories.setdefault(action.call_session_id, []).append(action)
    result = []
    for session in sessions:
        for sid in dict.fromkeys(session.scenario_ids):
            scenario = scenarios.get(uuid.UUID(sid))
            if not scenario or scenario.incident_payload.get("mode") != "DDS_MESSAGE": continue
            pair = by_scenario.get((session.id, scenario.id))
            call, card = pair if pair else (None, None)
            body = card.body if card else scenario.incident_payload
            if not call:
                if session.status != SessionStatus.RUNNING or user.dds_service_key not in {r["key"] for r in body.get("recipients", [])}: continue
            state = "COMPLETED" if call and call.completed_at else "ACTIVE" if call else "NEW"
            result.append({"session_id": str(session.id), "session_title": session.title, "scenario_id": sid,
                "number": f"112-{str(session.id)[:8]}-{sid[:8]}", "title": scenario.title,
                "incident_type": body.get("incident_type"), "address": body.get("address"), "ekp_code": body.get("ekp_code"),
                "available_at": session.started_at, "received_at": call.started_at if call else None,
                "completed_at": call.completed_at if call else None, "call_id": str(call.id) if call else None,
                "state": state, "service_status": action_state(histories.get(call.id, []))[0] if call else "ДОБАВЛЕНА",
                "active_call_id": active.get(session.id)})
    return result

@router.get("/messages/{call_id}")
async def read_message(call_id: uuid.UUID, db=Depends(get_db), user=Depends(require_roles(UserRole.STUDENT))):
    call = await db.get(CallSession, call_id)
    if not call or call.student_id != user.id: raise HTTPException(404, "Карточка не найдена")
    return await call_state(db, call)
