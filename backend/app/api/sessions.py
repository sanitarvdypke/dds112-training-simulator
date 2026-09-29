import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db, SessionLocal
from app.models.entities import *
from app.schemas.session import *
from app.api.deps import current_user, require_roles
from app.services.audit import audit
from app.services.scoring import score_actions
from app.services.rubric import evaluate_rubric
from app.ai.gateway import get_ai_provider
from app.simulators.gateway import rtu_adapter
from app.services.dds_card import DDS_STATUSES, DDS_FIELDS, public_body, action_state

router=APIRouter(prefix="/sessions",tags=["sessions"])

@router.post("",response_model=TrainingSessionOut)
async def create_session(data:TrainingSessionCreate,db:AsyncSession=Depends(get_db),user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    for sid in data.scenario_ids:
        scenario = await db.get(Scenario, sid)
        if not scenario or not scenario.published: raise HTTPException(400,"Нужны опубликованные сценарии")
    if data.group_id and not await db.get(Group, data.group_id): raise HTTPException(400,"Группа не найдена")
    row=TrainingSession(title=data.title.strip(),group_id=data.group_id,scenario_ids=[str(x) for x in data.scenario_ids],teacher_id=user.id)
    db.add(row); await db.flush(); await audit(db,user.id,"SESSION_CREATED","TrainingSession",row.id); await db.commit(); await db.refresh(row); return row

@router.get("",response_model=list[TrainingSessionOut])
async def list_sessions(messages_only:bool=False,db=Depends(get_db),user=Depends(current_user)):
    if user.role==UserRole.STUDENT:
        rows=(await db.scalars(select(TrainingSession).where(TrainingSession.status.in_([SessionStatus.RUNNING,SessionStatus.COMPLETED])))).all()
        rows=[r for r in rows if not r.group_id or await db.get(GroupMember,(r.group_id,user.id))]
    else:
        query=select(TrainingSession).order_by(TrainingSession.created_at.desc())
        if user.role==UserRole.TEACHER: query=query.where(TrainingSession.teacher_id==user.id)
        rows=(await db.scalars(query)).all()
    if user.role == UserRole.STUDENT:
        rows = [r for r in rows if await visible_scenarios(db, r, user)]
    if messages_only:
        filtered = []
        for row in rows:
            ids = await visible_scenarios(db, row, user) if user.role == UserRole.STUDENT else row.scenario_ids
            for sid in ids:
                scenario = await db.get(Scenario, uuid.UUID(sid))
                if scenario and scenario.incident_payload.get("mode") == "DDS_MESSAGE":
                    filtered.append(row)
                    break
        rows = filtered
    return rows

@router.post("/{session_id}/start")
async def start_session(session_id:uuid.UUID,db=Depends(get_db),user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    row=await db.get(TrainingSession,session_id,with_for_update=True)
    if not row: raise HTTPException(404,"Сессия не найдена")
    if user.role!=UserRole.ADMIN and row.teacher_id!=user.id: raise HTTPException(403,"Нет доступа к занятию")
    if row.status!=SessionStatus.DRAFT: raise HTTPException(409,"Запустить можно только черновик")
    row.status=SessionStatus.RUNNING; row.started_at=datetime.now(timezone.utc); await audit(db,user.id,"SESSION_STARTED","TrainingSession",row.id); await db.commit(); return {"ok":True}

@router.post("/{session_id}/finish")
async def finish_session(session_id:uuid.UUID,force:bool=False,db=Depends(get_db),user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    row=await db.get(TrainingSession,session_id,with_for_update=True)
    if not row: raise HTTPException(404,"Сессия не найдена")
    if user.role!=UserRole.ADMIN and row.teacher_id!=user.id: raise HTTPException(403,"Нет доступа к занятию")
    if row.status!=SessionStatus.RUNNING: raise HTTPException(409,"Занятие не запущено")
    active=(await db.scalars(select(CallSession).where(CallSession.training_session_id==row.id,CallSession.completed_at.is_(None)).with_for_update())).all()
    if active and not force: raise HTTPException(409,"Есть активные карточки. Завершите их или используйте досрочное завершение занятия")
    for call in active:
        result = await finalize_call(db, call)
        await audit(db,user.id,"MESSAGE_FORCE_COMPLETED","CallSession",call.id,{"score":result.score,"max_score":result.max_score})
    row.status=SessionStatus.COMPLETED; row.ended_at=datetime.now(timezone.utc); await audit(db,user.id,"SESSION_FINISHED","TrainingSession",row.id); await db.commit(); return {"ok":True,"forced_cards":len(active)}

async def visible_scenarios(db, session, user):
    result = []
    for sid in session.scenario_ids:
        scenario = await db.get(Scenario, uuid.UUID(sid))
        if not scenario: continue
        body = scenario.incident_payload
        if body.get("mode") != "DDS_MESSAGE" or user.dds_service_key in {r["key"] for r in body.get("recipients", [])}:
            result.append(sid)
    return result

@router.post("/{session_id}/messages/receive")
@router.post("/{session_id}/calls/start")
async def start_call(session_id:uuid.UUID, scenario_id:uuid.UUID|None=None, db=Depends(get_db), user=Depends(require_roles(UserRole.STUDENT))):
    user = await db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    session=await db.get(TrainingSession,session_id,with_for_update=True)
    if not session or session.status!=SessionStatus.RUNNING: raise HTTPException(400,"Сессия не запущена")
    if session.group_id and not await db.get(GroupMember,(session.group_id,user.id)): raise HTTPException(403,"Нет доступа к группе")
    active=await db.scalar(select(CallSession).where(CallSession.training_session_id==session.id,CallSession.student_id==user.id,CallSession.completed_at.is_(None)))
    if active:
        active_card = await db.get(EventCard, active.event_card_id)
        if scenario_id and active_card.scenario_id != scenario_id:
            raise HTTPException(409, "Сначала завершите активную карточку этого занятия")
        return await call_state(db,active)
    if not session.scenario_ids: raise HTTPException(400,"В сессии нет сценариев")
    completed=(await db.scalars(select(EventCard.scenario_id).join(CallSession,CallSession.event_card_id==EventCard.id).where(CallSession.training_session_id==session.id,CallSession.student_id==user.id,CallSession.completed_at.is_not(None)))).all()
    visible = await visible_scenarios(db, session, user)
    remaining=[sid for sid in visible if uuid.UUID(sid) not in completed]
    if scenario_id:
        if str(scenario_id) not in visible: raise HTTPException(404, "Карточка не найдена")
        remaining = [sid for sid in remaining if sid == str(scenario_id)]
    if not remaining: raise HTTPException(409,"Все сценарии занятия пройдены")
    scenario=await db.get(Scenario,uuid.UUID(remaining[0]));
    if not scenario: raise HTTPException(404,"Сценарий не найден")
    card=await db.scalar(select(EventCard).where(EventCard.scenario_id==scenario.id))
    if not card:
        card=EventCard(scenario_id=scenario.id,title=scenario.title,body=scenario.incident_payload,time_limit_sec=120); db.add(card); await db.flush()
    call=CallSession(training_session_id=session.id,student_id=user.id,event_card_id=card.id,provider="card112",status="ACTIVE",started_at=datetime.now(timezone.utc),answered_at=datetime.now(timezone.utc),metadata_json={"dds_service_key":user.dds_service_key,"rubric":scenario.expected_state.get("rubric"),"rubric_approval":scenario.expected_state.get("rubric_approval"),"scenario_version":scenario.version}); db.add(call); await db.flush(); await audit(db,user.id,"MESSAGE_RECEIVED","CallSession",call.id,{"scenario":scenario.code,"dds_service_key":user.dds_service_key}); await db.commit(); return await call_state(db,call)

async def call_state(db,call):
    card=await db.get(EventCard,call.event_card_id)
    actions=(await db.scalars(select(StudentAction).where(StudentAction.call_session_id==call.id).order_by(StudentAction.sequence_no))).all()
    session = await db.get(TrainingSession, call.training_session_id)
    actor = await db.get(User, call.student_id)
    status, fields = action_state(actions)
    key = call.metadata_json.get("dds_service_key")
    service = next((r["name"] for r in card.body.get("recipients", []) if r["key"] == key), key or "Не назначена")
    history = [{"id":str(a.id),"sequence_no":a.sequence_no,"action_type":a.action_type,"payload":a.payload,
                "occurred_at":a.occurred_at.isoformat(),"actor":actor.full_name,"service":service} for a in actions]
    timeline = [{"id":"added","action_type":"ADDED","payload":{},"occurred_at":(session.started_at or call.started_at).isoformat(),"actor":"Система 112","service":service},
                {"id":"received","action_type":"RECEIVED","payload":{},"occurred_at":call.started_at.isoformat(),"actor":actor.full_name,"service":service}] + history
    if call.completed_at:
        timeline.append({"id":"completed","action_type":"COMPLETED","payload":{},"occurred_at":call.completed_at.isoformat(),"actor":actor.full_name,"service":service})
    assessment = await db.scalar(select(AssessmentResult).where(AssessmentResult.call_session_id == call.id))
    result = {k:getattr(assessment,k) for k in ("score","max_score","duration_sec","over_time","details","ai_feedback")} if assessment else None
    rubric = call.metadata_json.get("rubric") or {}
    norms = [{"status":step["status"],"within_sec":step["within_sec"],
              "from_status":"ПОЛУЧЕНА СЛУЖБОЙ" if step["anchor"] == "RECEIVED" else rubric["steps"][index-1]["status"]}
             for index,step in enumerate(rubric.get("steps", [])) if step.get("within_sec") is not None]
    return {"call_id":str(call.id),"card_id":str(card.id),"scenario":card.title,"body":public_body(card.body),
        "time_limit_sec":card.time_limit_sec,"started_at":call.started_at.isoformat(),"actions":history,"provider":call.provider,
        "number":f"112-{str(session.id)[:8]}-{str(card.scenario_id)[:8]}","session_title":session.title,"session_id":str(session.id),
        "completed_at":call.completed_at,"service_status":status,"dds_fields":fields,"service_name":service,
        "allowed_statuses":DDS_STATUSES,"timeline":timeline,"assessment":result,"norms":norms}

@router.post("/messages/{call_id}/actions")
@router.post("/calls/{call_id}/actions")
async def add_action(call_id:uuid.UUID,data:ActionCreate,db=Depends(get_db),user=Depends(require_roles(UserRole.STUDENT))):
    call=await db.get(CallSession,call_id,with_for_update=True)
    if not call or call.student_id!=user.id: raise HTTPException(404,"Вызов не найден")
    if call.completed_at: raise HTTPException(409,"Вызов уже завершён")
    card = await db.get(EventCard, call.event_card_id)
    if card.body.get("mode") == "DDS_MESSAGE" and data.action_type not in ("SELECT_STATUS", "TEXT_INPUT", "UPDATE_DDS"):
        raise HTTPException(422, "Исходная карточка 112 доступна только для чтения")
    if data.action_type == "SELECT_STATUS" and data.payload.get("status") not in DDS_STATUSES:
        raise HTTPException(422, "Неизвестный статус ДДС")
    keys={"SELECT_INCIDENT":"category","SELECT_STATUS":"status","TEXT_INPUT":"text","SELECT_SERVICES":"services","SELECT_TAGS":"tags","UPDATE_DDS":"fields"}
    key=keys.get(data.action_type)
    if not key or key not in data.payload: raise HTTPException(422,"Неизвестное действие или неверные данные")
    value=data.payload[key]
    if key == "fields":
        if card.body.get("mode") != "DDS_MESSAGE" or not isinstance(value, dict) or not value or not value.keys() <= DDS_FIELDS.keys():
            raise HTTPException(422, "Неизвестные поля обработки ДДС")
        if any(not isinstance(v, str) or len(v) > DDS_FIELDS[k] for k,v in value.items()):
            raise HTTPException(422, "Неверное значение или превышена длина поля ДДС")
    elif key in ("services","tags"):
        if not isinstance(value,list) or not all(isinstance(v,str) for v in value): raise HTTPException(422,"Ожидается список строк")
    elif not isinstance(value,str): raise HTTPException(422,"Ожидается строка")
    if card.body.get("mode") == "DDS_MESSAGE":
        allowed = {key, "comment"} if key == "status" else {key}
        if not data.payload.keys() <= allowed: raise HTTPException(422, "Лишние поля действия")
        if key == "text" and (not value.strip() or len(value) > 4000): raise HTTPException(422, "Комментарий должен содержать от 1 до 4000 символов")
        if key == "status":
            comment = data.payload.get("comment", "")
            if not isinstance(comment, str) or len(comment) > 4000: raise HTTPException(422, "Некорректный комментарий статуса")
    count=await db.scalar(select(StudentAction).where(StudentAction.call_session_id==call.id).order_by(StudentAction.sequence_no.desc()).limit(1))
    seq=(count.sequence_no+1) if count else 1
    if data.action_type == "SELECT_STATUS":
        await rtu_adapter.emit_event("STATUS_CHANGED", {"call_id":str(call.id), **data.payload})
    action=StudentAction(call_session_id=call.id,action_type=data.action_type,payload=data.payload,sequence_no=seq,occurred_at=datetime.now(timezone.utc)); db.add(action); await db.flush(); await audit(db,user.id,"STUDENT_ACTION","StudentAction",action.id,{"type":data.action_type}); await db.commit(); return {"id":str(action.id),"sequence_no":seq,"occurred_at":action.occurred_at.isoformat()}

async def finalize_call(db, call):
    card=await db.get(EventCard,call.event_card_id); scenario=await db.get(Scenario,card.scenario_id)
    student=await db.get(User,call.student_id)
    actions=(await db.scalars(select(StudentAction).where(StudentAction.call_session_id==call.id).order_by(StudentAction.sequence_no))).all()
    ended_at = datetime.now(timezone.utc)
    duration=max(0,int((ended_at-call.started_at).total_seconds()))
    expected=(await db.scalars(select(ExpectedAction).where(ExpectedAction.scenario_id==scenario.id))).all()
    rubric = call.metadata_json.get("rubric")
    result = evaluate_rubric(rubric, actions, call.started_at, ended_at) if rubric else score_actions(expected,actions,duration,card.time_limit_sec,status_history=card.body.get("mode") == "DDS_MESSAGE")
    ai=await get_ai_provider().analyze_text(next((a.payload.get("text","") for a in reversed(actions) if a.action_type=="TEXT_INPUT"),""),None)
    call.status="ENDED"; call.completed_at=ended_at
    public = await call_state(db, call)
    result.details["history"] = public["timeline"]
    result.details["summary"] = {"student":student.full_name,"session":public["session_title"],"scenario":card.title,"number":public["number"],"service":public["service_name"],"started_at":call.started_at.isoformat(),"completed_at":ended_at.isoformat(),"scenario_version":call.metadata_json.get("scenario_version",scenario.version)}
    result.details["rubric_approval"] = call.metadata_json.get("rubric_approval")
    result.details["dds_fields"] = public["dds_fields"]
    assessment=AssessmentResult(call_session_id=call.id,score=result.score,max_score=result.max_score,duration_sec=duration,over_time=result.over_time,details=result.details,ai_feedback=ai); db.add(assessment); await db.flush()
    for e in result.details["errors"]: db.add(AssessmentError(assessment_result_id=assessment.id,code=e["code"],message=e["message"],severity=e["severity"],action_id=uuid.UUID(e["action_id"]) if e.get("action_id") else None))
    return CompleteCallOut(score=result.score,max_score=result.max_score,duration_sec=duration,over_time=result.over_time,details=result.details,ai_feedback=ai)

@router.post("/messages/{call_id}/complete",response_model=CompleteCallOut)
@router.post("/calls/{call_id}/complete",response_model=CompleteCallOut)
async def complete_call(call_id:uuid.UUID,db=Depends(get_db),user=Depends(require_roles(UserRole.STUDENT))):
    call=await db.get(CallSession,call_id,with_for_update=True)
    if not call or call.student_id!=user.id: raise HTTPException(404,"Вызов не найден")
    if call.completed_at: raise HTTPException(400,"Вызов уже завершён")
    result=await finalize_call(db,call)
    await audit(db,user.id,"MESSAGE_COMPLETED","CallSession",call.id,{"score":result.score}); await db.commit()
    return result

@router.websocket("/ws/{session_id}")
async def session_ws(websocket:WebSocket,session_id:str):
    await websocket.accept()
    try:
        import asyncio
        from app.core.security import decode_token
        credentials=await asyncio.wait_for(websocket.receive_json(),timeout=10)
        payload=decode_token(credentials.get("token",""))
        async with SessionLocal() as db:
            user=await db.get(User,uuid.UUID(payload["sub"]))
            session=await db.get(TrainingSession,uuid.UUID(session_id))
            if not user or not user.is_active or not session:
                await websocket.close(code=1008); return
            if user.role==UserRole.TEACHER and session.teacher_id!=user.id:
                await websocket.close(code=1008); return
            if user.role==UserRole.STUDENT and session.group_id and not await db.get(GroupMember,(session.group_id,user.id)):
                await websocket.close(code=1008); return
            if user.role==UserRole.STUDENT and not await visible_scenarios(db, session, user):
                await websocket.close(code=1008); return
        while True:
            msg=await websocket.receive_json()
            await websocket.send_json({"type":"ACK","session_id":session_id,"payload":msg})
    except WebSocketDisconnect: pass
    except Exception: await websocket.close(code=1008)
