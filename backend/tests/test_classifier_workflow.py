"""Live API/PostgreSQL tests of versioned classifier intake."""
import asyncio
import hashlib
import os
import uuid
from pathlib import Path
import httpx
import pytest
from test_classifier import sample_book, binary
from test_workflow import login, BASE

pytestmark=pytest.mark.skipif(not BASE,reason="Set TEST_API_URL to run live classifier tests")

def stage(client,data,name="QA-ekp.xlsx"):
    r=client.post("/imports/classifier/stage",files={"file":(name,data)})
    assert r.status_code==200,r.text
    return r.json()

def test_normalized_roundtrip_filters_and_idempotent_commit():
    data=binary(sample_book())
    with login("teacher") as t,login("student") as s:
        preview=t.post("/imports/classifier/preview",files={"file":("QA.xlsx",data)})
        assert preview.status_code==200 and preview.json()["metadata"]["statistics"]["incident_count"]==1
        version=stage(t,data);vid=version["import_id"]
        assert version["source_sha256"]==hashlib.sha256(data).hexdigest()
        assert version["status"]=="STAGED" and not version["validation_errors"]
        assert t.get(f"/imports/classifier/{vid}/entries").status_code==409
        assert t.post(f"/imports/classifier/{vid}/commit").status_code==200
        assert t.post(f"/imports/classifier/{vid}/commit").status_code==200
        details=t.get(f"/imports/classifier/{vid}").json()
        assert details["metadata"]["sheets"][0]["column_count"]==90
        assert details["status"]=="COMMITTED"
        entries=t.get(f"/imports/classifier/{vid}/entries").json()
        assert entries["total"]==1
        entry=entries["items"][0];eid=entry["id"]
        record=t.get(f"/imports/classifier/{vid}/entries/{eid}").json()
        assert record["raw"]["CL"]=="карточка-112" and record["code"]=="002010000"
        assert len(record["raw"])==90
        assert any(r["effect"]=="NO_RESPONSE" for r in record["rules"])
        svc=next(x["key"] for x in details["metadata"]["services"] if x["name"]=="Мосводоканал")
        assert t.get(f"/imports/classifier/{vid}/entries",params={"service_key":svc}).json()["total"]==1
        assert t.get(f"/imports/classifier/{vid}/entries",params={"q":"учебное"}).json()["total"]==1
        assert t.get(f"/imports/classifier/{vid}/entries",params={"q":"%"}).json()["total"]==0
        assert t.get(f"/imports/classifier/{vid}/entries",params={"offset":1}).json()["items"]==[]
        for path in ["/imports/classifier",f"/imports/classifier/{vid}",f"/imports/classifier/{vid}/entries",f"/imports/classifier/{vid}/entries/{eid}"]:
            assert s.get(path).status_code==403
        assert s.post(f"/imports/classifier/{vid}/commit").status_code==403
        assert t.get(f"/imports/classifier/{uuid.uuid4()}/entries/{eid}").status_code==404

def test_validation_blocks_bad_version_without_changing_good_version():
    with login("teacher") as t:
        good=stage(t,binary(sample_book()));gid=good["import_id"]
        assert t.post(f"/imports/classifier/{gid}/commit").status_code==200
        wb=sample_book();wb.active["E6"]="002010000";wb.active["K6"]="Дубликат"
        bad=stage(t,binary(wb));bid=bad["import_id"]
        assert any(e["code"]=="DUPLICATE_CODE" for e in bad["validation_errors"])
        assert t.post(f"/imports/classifier/{bid}/commit").status_code==400
        assert t.get(f"/imports/classifier/{bid}").json()["status"]=="STAGED"
        assert t.get(f"/imports/classifier/{gid}/entries").json()["total"]==1

def test_commit_author_and_admin():
    from app.db.session import SessionLocal,engine
    from app.models.entities import User,UserRole
    from app.core.security import hash_password,create_access_token
    async def setup():
        try:
            async with SessionLocal() as db:
                user=User(email=f"qa-ekp-{uuid.uuid4()}@example.local",full_name="QA проверка импорта",role=UserRole.TEACHER,password_hash=hash_password("Qa123!"))
                db.add(user);await db.commit()
                return create_access_token(str(user.id),"TEACHER")
        finally: await engine.dispose()
    token=asyncio.run(setup())
    with login("teacher") as t,login("admin") as admin,httpx.Client(base_url=BASE,headers={"Authorization":"Bearer "+token}) as other:
        version=stage(t,binary(sample_book()));vid=version["import_id"]
        assert other.post(f"/imports/classifier/{vid}/commit").status_code==403
        assert admin.post(f"/imports/classifier/{vid}/commit").status_code==200

@pytest.mark.skipif(not os.getenv("EKP_SOURCE_PATH"),reason="Source workbook required")
def test_actual_source_api_and_database():
    data=Path(os.environ["EKP_SOURCE_PATH"]).read_bytes()
    with login("teacher") as t:
        version=stage(t,data,"QA-искл_пожар_задымление.xlsx")
        vid=version["import_id"]
        assert not version["validation_errors"]
        assert version["statistics"]["incident_count"]==1281
        result=t.post(f"/imports/classifier/{vid}/commit")
        assert result.status_code==200,result.text
        assert t.get(f"/imports/classifier/{vid}/entries").json()["total"]==1281
        details=t.get(f"/imports/classifier/{vid}").json()
        assert len(details["metadata"]["services"])==53
        found=[r for r in t.get(f"/imports/classifier/{vid}/entries",params={"q":"2010000"}).json()["items"] if r["code"]=="2010000"]
        assert len(found)==1
        record=t.get(f'/imports/classifier/{vid}/entries/{found[0]["id"]}').json()
        assert record["raw"]["E"]==2010000
        assert record["response_scenario_code"]=="2_4"
        assert next(r for r in record["rules"] if r["column"]=="AO")["condition"]["feature"]=="road_blocked"
        count=t.get(f"/imports/classifier/{vid}/entries",params={"review_only":True}).json()["total"]
        assert count==version["statistics"]["review_required_count"]
        assert t.post(f"/imports/classifier/{vid}/commit").status_code==200
        assert t.get(f"/imports/classifier/{vid}/entries").json()["total"]==1281
