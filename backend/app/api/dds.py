"""Prepared 112 messages and teacher-managed DDS profiles."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import select
from sqlalchemy.orm import defer
from app.api.deps import require_roles
from app.db.session import get_db
from app.models.entities import User, UserRole, CallSession
from app.models.classifier import ClassifierImport, ClassifierEntry
from app.schemas.auth import UserOut
from app.schemas.scenario import ScenarioCreate
from app.api.scenarios import create_scenario
from app.services.routing import route
from app.services.audit import audit

router = APIRouter(prefix="/dds", tags=["dds"])
staff = require_roles(UserRole.ADMIN, UserRole.TEACHER)

class Profile(BaseModel):
    service_key: str = Field(min_length=1, max_length=64)

class RoutingInput(BaseModel):
    entry_id: uuid.UUID
    facts: dict[str, StrictBool] = Field(default_factory=dict)

class PreparedCard(RoutingInput):
    title: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=1000)
    message: str = Field(min_length=1, max_length=10000)
    recipients: list[str] = Field(min_length=1, max_length=100)
    review_reason: str = Field(default="", max_length=2000)
    time_limit_sec: int = Field(default=120, ge=1, le=3600)

async def source(db, entry_id):
    entry = await db.get(ClassifierEntry, entry_id)
    if not entry: raise HTTPException(404, "Пункт ЕКП не найден")
    version = await db.scalar(select(ClassifierImport).options(defer(ClassifierImport.rows)).where(ClassifierImport.id == entry.import_id))
    if not version or version.status != "COMMITTED" or version.format != "ekp":
        raise HTTPException(409, "Нужна утверждённая версия ЕКП")
    return entry, version

@router.get("/services")
async def services(db=Depends(get_db), user=Depends(staff)):
    versions = (await db.scalars(select(ClassifierImport).options(defer(ClassifierImport.rows)).where(ClassifierImport.status == "COMMITTED", ClassifierImport.format == "ekp"))).all()
    unique = {s["key"]: s for v in versions for s in v.metadata_json.get("services", [])}
    return sorted(unique.values(), key=lambda s: s["name"])

@router.get("/students", response_model=list[UserOut])
async def students(db=Depends(get_db), user=Depends(staff)):
    return (await db.scalars(select(User).where(User.role == UserRole.STUDENT, User.is_active.is_(True)).order_by(User.email))).all()

@router.put("/students/{student_id}/profile", response_model=UserOut)
async def profile(student_id: uuid.UUID, data: Profile, db=Depends(get_db), user=Depends(staff)):
    row = await db.get(User, student_id, with_for_update=True)
    if not row or row.role != UserRole.STUDENT: raise HTTPException(404, "Обучающийся не найден")
    if data.service_key not in {s["key"] for s in await services(db, user)}: raise HTTPException(422, "Неизвестная служба ЕКП")
    if await db.scalar(select(CallSession.id).where(CallSession.student_id == row.id, CallSession.completed_at.is_(None))):
        raise HTTPException(409, "Сначала завершите активную карточку обучающегося")
    row.dds_service_key = data.service_key
    await audit(db, user.id, "DDS_PROFILE_CHANGED", "User", row.id, {"service_key": data.service_key})
    await db.commit()
    return row

@router.post("/routing/preview")
async def preview(data: RoutingInput, db=Depends(get_db), user=Depends(staff)):
    entry, version = await source(db, data.entry_id)
    return {**route(entry.data, data.facts), "services": version.metadata_json.get("services", [])}

@router.post("/scenarios")
async def prepared(data: PreparedCard, db=Depends(get_db), user=Depends(staff)):
    entry, version = await source(db, data.entry_id)
    decision = route(entry.data, data.facts)
    known = {s["key"]: s["name"] for s in version.metadata_json.get("services", [])}
    selected = set(data.recipients)
    if not selected <= known.keys(): raise HTTPException(422, "Получатель отсутствует в выбранной версии ЕКП")
    automatic = {s["key"] for s in decision["recipients"]}
    if (decision["review_required"] or selected != automatic) and not data.review_reason.strip():
        raise HTTPException(422, "Требуется пояснение решения преподавателя: уточнение правил или изменение получателей")
    if not all(v.strip() for v in (data.title, data.address, data.message)):
        raise HTTPException(422, "Заполните название, адрес и сообщение")
    payload = {"mode": "DDS_MESSAGE", "message": data.message.strip(), "address": data.address.strip(),
        "incident_type": entry.title, "ekp_code": entry.code, "facts": data.facts, "source_features": entry.data.get("features", {}),
        "recipients": [{"key": k, "name": known[k]} for k in sorted(selected)],
        "routing": {"import_id": str(version.id), "entry_id": str(entry.id), "source_sha256": version.source_sha256,
                    "source_sheet": entry.source_sheet, "source_row": entry.source_row,
                    "response_scenario_code": entry.data.get("response_scenario_code"),
                    "decision": decision, "review_reason": data.review_reason.strip(), "reviewed_by": str(user.id)}}
    return await create_scenario(ScenarioCreate(code="EKP-" + uuid.uuid4().hex, title=data.title.strip(),
        category=entry.title[:255], participant_role="Диспетчер ДДС", incident_payload=payload,
        expected_state={"status": "ПРИНЯТО"}, time_limit_sec=data.time_limit_sec), db, user)
