from uuid import UUID, uuid4
from datetime import datetime, timezone
from copy import deepcopy
from pydantic import ValidationError
from app.schemas.rubric import Rubric
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.entities import Scenario, User, UserRole, ExpectedAction, EventCard
from app.schemas.scenario import ScenarioCreate, ScenarioOut
from app.api.deps import current_user, require_roles
from app.services.audit import audit
from app.ai.gateway import get_ai_provider

router=APIRouter(prefix="/scenarios", tags=["scenarios"])
@router.get("", response_model=list[ScenarioOut])
async def list_scenarios(db: AsyncSession=Depends(get_db), user=Depends(current_user)):
    if user.role == UserRole.STUDENT: raise HTTPException(403,"Эталоны доступны только преподавателю")
    rows=(await db.scalars(select(Scenario).order_by(Scenario.category,Scenario.title))).all(); return rows
@router.post("", response_model=ScenarioOut)
async def create_scenario(data: ScenarioCreate, db: AsyncSession=Depends(get_db), user: User=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    if await db.scalar(select(Scenario.id).where(Scenario.code==data.code)): raise HTTPException(409,"Код сценария уже существует")
    if "rubric" in data.expected_state:
        try: config = Rubric.model_validate(data.expected_state["rubric"]).model_dump()
        except ValidationError: raise HTTPException(422, "Некорректный эталон")
        if data.published: raise HTTPException(422, "Сначала утвердите эталон в черновике")
        data.expected_state = {**data.expected_state, "rubric": config, "rubric_approval": None}
    row=Scenario(**data.model_dump(exclude={"time_limit_sec"}),created_by=user.id); db.add(row); await db.flush()
    db.add(EventCard(scenario_id=row.id,title=row.title,body=row.incident_payload,time_limit_sec=data.time_limit_sec))
    steps=[("SELECT_INCIDENT",{"category":row.category},2), ("SELECT_STATUS",{"status":row.expected_state.get("status","ПРИНЯТО")},2), ("SELECT_SERVICES",{"services":row.expected_state.get("services",["ДДС"])},1), ("SELECT_TAGS",{"tags":row.incident_payload.get("tags",[])},1), ("TEXT_INPUT",{},1)]
    if row.incident_payload.get("mode") == "DDS_MESSAGE":
        steps = [("SELECT_STATUS", {"status": "ПРИНЯТО"}, 2), ("TEXT_INPUT", {}, 1)]
    for n,(kind,payload,weight) in enumerate(steps,1): db.add(ExpectedAction(scenario_id=row.id,action_type=kind,payload=payload,weight=weight,order_no=n))
    await audit(db,user.id,"SCENARIO_CREATED","Scenario",row.id, {"code":row.code}); await db.commit(); await db.refresh(row); return row
@router.post("/generate")
async def generate(data: dict, user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    result=await get_ai_provider().generate_scenario(data); return result
@router.post("/{scenario_id}/publish")
async def publish(scenario_id: UUID, db: AsyncSession=Depends(get_db), user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    row=await db.get(Scenario,scenario_id,with_for_update=True)
    if not row: raise HTTPException(404,"Сценарий не найден")
    if user.role!=UserRole.ADMIN and row.created_by!=user.id: raise HTTPException(403,"Нет доступа к сценарию")
    if row.expected_state.get("rubric") and not row.expected_state.get("rubric_approval"):
        raise HTTPException(409, "Утвердите эталон перед публикацией")
    row.published=True; row.version += 1; await audit(db,user.id,"SCENARIO_PUBLISHED","Scenario",row.id); await db.commit(); return {"ok":True,"version":row.version}

@router.put("/{scenario_id}/rubric", response_model=ScenarioOut)
async def approve_rubric(scenario_id: UUID, data: Rubric, db=Depends(get_db), user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    row = await db.get(Scenario, scenario_id, with_for_update=True)
    if not row: raise HTTPException(404, "Сценарий не найден")
    if user.role != UserRole.ADMIN and row.created_by != user.id: raise HTTPException(403, "Нет доступа к сценарию")
    if row.published: raise HTTPException(409, "Опубликованный эталон неизменяем. Создайте копию сценария")
    if row.incident_payload.get("mode") != "DDS_MESSAGE": raise HTTPException(422, "Эталон событий предназначен для карточек ДДС")
    approval = {"id": str(uuid4()), "approved_by":str(user.id), "approved_at":datetime.now(timezone.utc).isoformat()}
    row.expected_state = {**row.expected_state, "rubric": data.model_dump(), "rubric_approval": approval}
    row.version += 1
    cards = (await db.scalars(select(EventCard).where(EventCard.scenario_id == row.id))).all()
    for card in cards: card.time_limit_sec = data.total_time_sec
    await audit(db,user.id,"RUBRIC_APPROVED","Scenario",row.id,approval)
    await db.commit()
    return row

@router.post("/{scenario_id}/clone", response_model=ScenarioOut)
async def clone_scenario(scenario_id: UUID, db=Depends(get_db), user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    row = await db.get(Scenario, scenario_id)
    if not row: raise HTTPException(404, "Сценарий не найден")
    if user.role != UserRole.ADMIN and row.created_by != user.id: raise HTTPException(403, "Нет доступа к сценарию")
    card = await db.scalar(select(EventCard).where(EventCard.scenario_id == row.id))
    state = deepcopy(row.expected_state)
    state.pop("rubric_approval", None)
    return await create_scenario(ScenarioCreate(code="COPY-"+uuid4().hex,title=(row.title[:240]+" (копия)"),category=row.category,
        difficulty=row.difficulty,participant_role=row.participant_role,incident_payload=deepcopy(row.incident_payload),
        expected_state=state,time_limit_sec=card.time_limit_sec if card else 120),db,user)
