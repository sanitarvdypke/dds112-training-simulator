"""Integration tests against the running local stack; create only QA-prefixed data."""
import io
import os
import time
import uuid
import httpx
import pytest
from openpyxl import Workbook
from contextlib import contextmanager

BASE = os.getenv("TEST_API_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="Set TEST_API_URL for live PostgreSQL/API checks")

@contextmanager
def login(role):
    client = httpx.Client(base_url=BASE, timeout=20)
    response = client.post("/auth/login", json={"email":role+"@example.local","password":role.title()+"123!"})
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = "Bearer "+response.json()["access_token"]
    try: yield client
    finally: client.close()

@pytest.mark.parametrize("role", ["admin","teacher","student"])
def test_role_login(role):
    with login(role) as c:
        r=c.get("/auth/me")
        assert r.status_code==200, r.text
        assert r.json()["role"]==role.upper()
        assert uuid.UUID(r.json()["id"])

def test_invalid_login():
    with httpx.Client(base_url=BASE) as c:
        assert c.post("/auth/login",json={"email":"teacher@example.local","password":"wrong"}).status_code==401
        assert c.get("/sessions").status_code in (401,403)
        assert c.get("/sessions",headers={"Authorization":"Bearer invalid"}).status_code==401

@pytest.mark.parametrize("path,payload", [
    ("/sessions",{"title":"forbidden","scenario_ids":[str(uuid.uuid4())]}),
    ("/scenarios",{"code":"forbidden","title":"forbidden","category":"ДТП"}),
    ("/scenarios/generate",{"category":"ДТП"}),
])
def test_student_write_denied(path,payload):
    with login("student") as c: assert c.post(path,json=payload).status_code==403

def make_scenario(c, limit=120):
    draft=c.post("/scenarios/generate",json={"category":"ДТП"})
    assert draft.status_code==200
    payload={**draft.json(),"code":"QA-"+str(uuid.uuid4()),"expected_state":{"status":"ПРИНЯТО","services":["ДДС"]},"time_limit_sec":limit}
    r=c.post("/scenarios",json=payload)
    assert r.status_code==200,r.text
    return r.json(),payload

def make_session(c,scenario_ids):
    r=c.post("/sessions",json={"title":"QA интеграционная практика","scenario_ids":scenario_ids})
    assert r.status_code==200,r.text
    return r.json()["id"]

def test_full_workflow():
    with login("teacher") as teacher, login("student") as student, login("admin") as admin:
        scenario,payload=make_scenario(teacher)
        assert teacher.post("/scenarios",json=payload).status_code==409
        assert teacher.post("/sessions",json={"title":"QA","scenario_ids":[scenario["id"]]}).status_code==400
        assert teacher.post(f'/scenarios/{scenario["id"]}/publish').status_code==200
        sid=make_session(teacher,[scenario["id"]])
        assert student.post(f"/sessions/{sid}/calls/start").status_code==400
        assert teacher.post(f"/sessions/{sid}/finish").status_code==409
        assert teacher.post(f"/sessions/{sid}/start").status_code==200
        assert teacher.post(f"/sessions/{sid}/start").status_code==409
        assert sid in [s["id"] for s in student.get("/sessions").json()]
        call=student.post(f"/sessions/{sid}/calls/start").json()
        cid=call["call_id"]
        assert student.post(f"/sessions/{sid}/calls/start").json()["call_id"]==cid
        assert teacher.post(f"/sessions/{sid}/finish").status_code==409
        assert teacher.post(f"/sessions/{sid}/calls/start").status_code==403
        actions=[
            ("SELECT_INCIDENT",{"category":"БПЛА"}),
            ("SELECT_INCIDENT",{"category":"ДТП"}),
            ("SELECT_STATUS",{"status":"ПРИНЯТО"}),
            ("SELECT_SERVICES",{"services":["ДДС"]}),
            ("SELECT_TAGS",{"tags":list(reversed(payload["incident_payload"]["tags"]))}),
            ("TEXT_INPUT",{"text":"Сообщение принято, информация зафиксирована."}),
        ]
        for i,(kind,data) in enumerate(actions,1):
            r=student.post(f"/sessions/calls/{cid}/actions",json={"action_type":kind,"payload":data})
            assert r.status_code==200,r.text
            assert r.json()["sequence_no"]==i
        restored=student.post(f"/sessions/{sid}/calls/start").json()
        assert restored["started_at"]==call["started_at"] and len(restored["actions"])==6
        r=student.post(f"/sessions/calls/{cid}/complete")
        assert r.status_code==200,r.text
        result=r.json()
        assert result["score"]==result["max_score"]==7 and not result["details"]["errors"]
        assert student.post(f"/sessions/calls/{cid}/complete").status_code==400
        assert student.post(f"/sessions/calls/{cid}/actions",json={"action_type":"TEXT_INPUT","payload":{"text":"late"}}).status_code==409
        assert student.post(f"/sessions/{sid}/calls/start").status_code==409
        reports=teacher.get("/reports/assessments")
        assert reports.status_code==200,reports.text
        report=next(r for r in reports.json() if r["call_session_id"]==cid)
        rid=report["id"]
        for fmt in ("csv","pdf"):
            r=teacher.get(f"/reports/assessment/{rid}.{fmt}")
            assert r.status_code==200,r.text
            assert r.content.startswith(b"%PDF") if fmt=="pdf" else "Балл" in r.content.decode("utf-8-sig")
            assert student.get(f"/reports/assessment/{rid}.{fmt}").status_code==403
        assert admin.get("/reports/assessments").status_code==200
        assert teacher.post(f"/sessions/{sid}/finish").status_code==200
        assert teacher.post(f"/sessions/{sid}/start").status_code==409
        assert student.post(f"/sessions/{sid}/calls/start").status_code==400

def test_timeout_and_multiple_scenarios():
    with login("teacher") as t,login("student") as s:
        scenarios=[make_scenario(t,1)[0] for _ in range(2)]
        for row in scenarios: assert t.post(f'/scenarios/{row["id"]}/publish').status_code==200
        sid=make_session(t,[r["id"] for r in scenarios])
        t.post(f"/sessions/{sid}/start")
        first=s.post(f"/sessions/{sid}/calls/start").json()
        time.sleep(2.1)
        result=s.post(f'/sessions/calls/{first["call_id"]}/complete').json()
        assert result["over_time"] and result["score"]==0 and result["max_score"]==7
        second=s.post(f"/sessions/{sid}/calls/start").json()
        assert second["card_id"]!=first["card_id"]
        assert s.post(f'/sessions/calls/{second["call_id"]}/complete').status_code==200
        assert t.post(f"/sessions/{sid}/finish").status_code==200

@pytest.mark.parametrize("path",["/sessions/not-a-uuid/start","/scenarios/not-a-uuid/publish","/imports/classifier/not-a-uuid/commit"])
def test_invalid_uuid(path):
    with login("teacher") as c: assert c.post(path).status_code==422

def test_invalid_session():
    with login("teacher") as c:
        for payload in ({"title":"QA","scenario_ids":[]},{"title":" ","scenario_ids":[str(uuid.uuid4())]}):
            assert c.post("/sessions",json=payload).status_code==422
        assert c.post("/sessions",json={"title":"QA","scenario_ids":[str(uuid.uuid4())]}).status_code==400

def test_classifier_import():
    with login("teacher") as c,login("student") as s:
        bad={"file":("bad.xlsx",b"invalid")}
        assert c.post("/imports/classifier/preview",files=bad).status_code==400
        assert s.post("/imports/classifier/preview",files=bad).status_code==403
        wb=Workbook();wb.active.append(["Код","Название"]);wb.active.append(["QA","Учебная строка"])
        data=io.BytesIO();wb.save(data)
        files={"file":("qa.xlsx",data.getvalue())}
        preview=c.post("/imports/classifier/preview",files=files)
        assert preview.status_code==200 and preview.json()["row_count"]==1
        stage=c.post("/imports/classifier/stage",files=files)
        assert stage.status_code==200,stage.text
        commit=c.post('/imports/classifier/'+stage.json()["import_id"]+'/commit')
        assert commit.status_code==200 and commit.json()["status"]=="COMMITTED"


def test_websocket_authentication():
    from websockets.sync.client import connect
    from websockets.exceptions import ConnectionClosed
    import json
    with login("teacher") as t:
        scenario,_=make_scenario(t)
        t.post(f'/scenarios/{scenario["id"]}/publish')
        sid=make_session(t,[scenario["id"]])
        url=BASE.replace("http://","ws://").replace("https://","wss://")+f"/sessions/ws/{sid}"
        with connect(url) as ws:
            ws.send(json.dumps({"token":t.headers["Authorization"].split()[1]}))
            ws.send(json.dumps({"type":"PING"}))
            assert json.loads(ws.recv(timeout=3))["type"]=="ACK"
        with connect(url) as ws:
            ws.send(json.dumps({"token":"invalid"}))
            with pytest.raises(ConnectionClosed): ws.recv(timeout=3)

def test_recorded_actions_and_audit_links():
    import asyncio
    from sqlalchemy import select
    from app.db.session import SessionLocal,engine
    from app.models.entities import AuditLog,AssessmentResult,CallSession
    async def check():
        try:
            async with SessionLocal() as db:
                rows=(await db.scalars(select(AuditLog).where(AuditLog.event_type.in_(["MESSAGE_RECEIVED","MESSAGE_COMPLETED","STUDENT_ACTION"])).order_by(AuditLog.created_at.desc()).limit(20))).all()
                assert rows and all(r.entity_id for r in rows)
                result=await db.scalar(select(AssessmentResult).order_by(AssessmentResult.created_at.desc()))
                call=await db.get(CallSession,result.call_session_id)
                assert call.completed_at and call.status=="ENDED"
        finally: await engine.dispose()
    asyncio.run(check())


def test_ownership_group_and_inactive_user():
    import asyncio
    from app.db.session import SessionLocal,engine
    from app.models.entities import User,UserRole,Group
    from app.core.security import hash_password,create_access_token
    suffix=str(uuid.uuid4())
    async def setup():
        try:
            async with SessionLocal() as db:
                other_teacher=User(email="qa-teacher-"+suffix+"@example.local",full_name="QA другой преподаватель",password_hash=hash_password("Qa123!"),role=UserRole.TEACHER)
                other_student=User(email="qa-student-"+suffix+"@example.local",full_name="QA другой обучающийся",password_hash=hash_password("Qa123!"),role=UserRole.STUDENT,is_active=False)
                group=Group(name="QA-"+suffix)
                db.add_all([other_teacher,other_student,group]);await db.commit()
                return create_access_token(str(other_teacher.id),"TEACHER"),other_student.email,str(group.id)
        finally: await engine.dispose()
    token,inactive_email,gid=asyncio.run(setup())
    with login("teacher") as t,login("student") as s,httpx.Client(base_url=BASE,headers={"Authorization":"Bearer "+token}) as other:
        scenario,_=make_scenario(t);t.post(f'/scenarios/{scenario["id"]}/publish')
        sid=make_session(t,[scenario["id"]])
        assert other.post(f"/sessions/{sid}/start").status_code==403
        assert sid not in [r["id"] for r in other.get("/sessions").json()]
        assert other.post(f'/scenarios/{scenario["id"]}/publish').status_code==403
        rid=t.get("/reports/assessments").json()[0]["id"]
        assert other.get(f"/reports/assessment/{rid}.csv").status_code==404
        r=t.post("/sessions",json={"title":"QA закрытая группа","group_id":gid,"scenario_ids":[scenario["id"]]})
        grouped=r.json()["id"];t.post(f"/sessions/{grouped}/start")
        assert s.post(f"/sessions/{grouped}/calls/start").status_code==403
        assert grouped not in [r["id"] for r in s.get("/sessions").json()]
        assert t.post("/auth/login",json={"email":inactive_email,"password":"Qa123!"}).status_code==401
        assert t.post(f"/sessions/{grouped}/finish").status_code==200


@pytest.mark.parametrize("code",["DEMO-001","DEMO-002","DEMO-003"])
def test_seed_scenario(code):
    with login("teacher") as t,login("student") as s:
        scenario=next(row for row in t.get("/scenarios").json() if row["code"]==code)
        sid=make_session(t,[scenario["id"]]);assert t.post(f"/sessions/{sid}/start").status_code==200
        call=s.post(f"/sessions/{sid}/calls/start").json()
        cid=call["call_id"]
        for kind,payload in [
            ("SELECT_INCIDENT",{"category":scenario["category"]}),
            ("SELECT_STATUS",{"status":"ПРИНЯТО"}),
            ("SELECT_SERVICES",{"services":["ДДС"]}),
            ("SELECT_TAGS",{"tags":scenario["incident_payload"]["tags"]}),
            ("TEXT_INPUT",{"text":"Сообщение принято, информация зафиксирована."}),
        ]:
            assert s.post(f"/sessions/calls/{cid}/actions",json={"action_type":kind,"payload":payload}).status_code==200
        r=s.post(f"/sessions/calls/{cid}/complete").json()
        assert r["score"]==r["max_score"]==7 and not r["details"]["errors"]
        assert t.post(f"/sessions/{sid}/finish").status_code==200
