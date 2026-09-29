"""Versioned classifier intake. Importing stores source rules; it does not dispatch cards."""
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import select, func, or_, insert
from sqlalchemy.orm import defer
from starlette.concurrency import run_in_threadpool
from app.api.deps import require_roles
from app.models.entities import UserRole
from app.models.classifier import ClassifierImport, ClassifierEntry
from app.db.session import get_db
from app.services.audit import audit
from app.services.classifier import parse_workbook, ClassifierFormatError, MAX_UPLOAD

router = APIRouter(prefix="/imports", tags=["imports"])
staff = require_roles(UserRole.ADMIN, UserRole.TEACHER)


def parse_xlsx(data: bytes):
    """Compatibility helper; EKP rows now retain coordinates and the full source."""
    try:
        return parse_workbook(data)["rows"]
    except ClassifierFormatError as exc:
        raise HTTPException(400, str(exc)) from exc


async def read_upload(file):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "Ожидается XLSX")
    data = await file.read(MAX_UPLOAD + 1)
    try:
        return await run_in_threadpool(parse_workbook, data, file.filename)
    except ClassifierFormatError as exc:
        raise HTTPException(400, str(exc)) from exc


def summary(item):
    return {"import_id": str(item.id), "filename": item.filename, "status": item.status,
            "format": item.format, "source_sha256": item.source_sha256,
            "created_at": item.created_at, "created_by": str(item.created_by) if item.created_by else None,
            "row_count": item.metadata_json.get("statistics", {}).get("source_rows"),
            "statistics": item.metadata_json.get("statistics", {}),
            "validation_errors": item.validation_errors, "warnings": item.warnings}


async def get_import(db, import_id, lock=False, with_rows=False):
    query = select(ClassifierImport).where(ClassifierImport.id == import_id)
    if not with_rows:
        query = query.options(defer(ClassifierImport.rows))
    if lock:
        query = query.with_for_update()
    item = await db.scalar(query)
    if not item:
        raise HTTPException(404, "Импорт не найден")
    return item


@router.post("/classifier/preview")
async def classifier_preview(file: UploadFile = File(...), user=Depends(staff)):
    parsed = await read_upload(file)
    return {"filename": file.filename, "status": "PREVIEW_ONLY", "format": parsed["format"],
            "source_sha256": parsed["source_sha256"], "row_count": len(parsed["rows"]),
            "preview": parsed["rows"][:20], "metadata": parsed["metadata"],
            "validation_errors": parsed["validation_errors"], "warnings": parsed["warnings"]}


@router.post("/classifier/stage")
async def classifier_stage(file: UploadFile = File(...), db=Depends(get_db), user=Depends(staff)):
    parsed = await read_upload(file)
    item = ClassifierImport(filename=file.filename[:255], status="STAGED", rows=parsed["rows"],
        source_sha256=parsed["source_sha256"], format=parsed["format"], metadata_json=parsed["metadata"],
        warnings=parsed["warnings"], validation_errors=parsed["validation_errors"], created_by=user.id)
    db.add(item)
    await db.flush()
    await audit(db, user.id, "CLASSIFIER_STAGED", "ClassifierImport", item.id,
                {"sha256": item.source_sha256, **parsed["metadata"]["statistics"]})
    await db.commit()
    return summary(item)


@router.get("/classifier")
async def classifier_imports(db=Depends(get_db), user=Depends(staff), limit: int = Query(30, ge=1, le=100),
                             offset: int = Query(0, ge=0)):
    query = select(ClassifierImport).options(defer(ClassifierImport.rows)).order_by(ClassifierImport.created_at.desc())
    total = await db.scalar(select(func.count()).select_from(ClassifierImport))
    return {"total": total, "items": [summary(r) for r in (await db.scalars(query.offset(offset).limit(limit))).all()]}


@router.get("/classifier/{import_id}")
async def classifier_details(import_id: uuid.UUID, db=Depends(get_db), user=Depends(staff)):
    item = await get_import(db, import_id)
    return {**summary(item), "metadata": item.metadata_json}


@router.post("/classifier/{import_id}/commit")
async def classifier_commit(import_id: uuid.UUID, db=Depends(get_db), user=Depends(staff)):
    item = await get_import(db, import_id, lock=True, with_rows=True)
    if user.role != UserRole.ADMIN and item.created_by != user.id:
        raise HTTPException(403, "Подтверждать импорт может его автор или администратор")
    if item.status == "COMMITTED":
        return {"ok": True, **summary(item), "rows": len(item.rows)}
    if item.status != "STAGED":
        raise HTTPException(409, "Импорт не является черновиком")
    if item.validation_errors:
        raise HTTPException(400, {"validation_errors": item.validation_errors})
    if item.format == "legacy":
        raise HTTPException(409, "Для старого импорта загрузите исходный XLSX заново")
    records = []
    if item.format == "ekp":
        for row in item.rows:
            if row["kind"] != "incident":
                continue
            records.append({"id": uuid.uuid4(), "import_id": item.id, "source_sheet": row["source_sheet"],
                            "source_row": row["source_row"], "code": row["code"], "title": row["title"],
                            "group_name": row["group_name"], "data": row})
    # Same transaction as status/audit; retry never duplicates normalized entries.
    for start in range(0, len(records), 100):
        await db.execute(insert(ClassifierEntry), records[start:start+100])
    item.status = "COMMITTED"
    await audit(db, user.id, "CLASSIFIER_COMMITTED", "ClassifierImport", item.id,
                {"rows": len(item.rows), "incidents": len(records), "source_sha256": item.source_sha256})
    await db.commit()
    return {"ok": True, **summary(item), "rows": len(item.rows)}


@router.get("/classifier/{import_id}/entries")
async def classifier_entries(import_id: uuid.UUID, q: str = Query("", max_length=200),
                             service_key: str | None = None, review_only: bool = False,
                             offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                             db=Depends(get_db), user=Depends(staff)):
    item = await get_import(db, import_id)
    if item.status != "COMMITTED" or item.format != "ekp":
        raise HTTPException(409, "Справочник доступен после подтверждения импорта ЕКП")
    query = select(ClassifierEntry).where(ClassifierEntry.import_id == item.id)
    if q.strip():
        needle = q.strip()
        query = query.where(or_(ClassifierEntry.code.contains(needle, autoescape=True),
                                ClassifierEntry.title.icontains(needle, autoescape=True)))
    if service_key:
        query = query.where(ClassifierEntry.data["rules"].contains([{"service_key": service_key}]))
    if review_only:
        query = query.where(ClassifierEntry.data["review_required"].as_boolean().is_(True))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.scalars(query.order_by(ClassifierEntry.source_sheet, ClassifierEntry.source_row).offset(offset).limit(limit))).all()
    return {"total": total, "offset": offset, "limit": limit, "items": [
        {"id": str(r.id), "code": r.code, "title": r.title, "group_name": r.group_name,
         "source_sheet": r.source_sheet, "source_row": r.source_row,
         "response_scenario_code": r.data["response_scenario_code"], "lead_service_code": r.data["lead_service_code"],
         "features": r.data["features"], "rule_count": len(r.data["rules"]), "review_required": r.data["review_required"]}
        for r in rows]}


@router.get("/classifier/{import_id}/entries/{entry_id}")
async def classifier_entry(import_id: uuid.UUID, entry_id: uuid.UUID, db=Depends(get_db), user=Depends(staff)):
    row = await db.scalar(select(ClassifierEntry).where(ClassifierEntry.id == entry_id, ClassifierEntry.import_id == import_id))
    if not row:
        raise HTTPException(404, "Происшествие не найдено")
    return {"id": str(row.id), "import_id": str(row.import_id), **row.data}
