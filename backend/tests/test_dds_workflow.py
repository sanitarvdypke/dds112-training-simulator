import asyncio
import uuid
import httpx
import pytest
from test_workflow import login, BASE, make_session
from test_classifier import sample_book, binary
from test_classifier_workflow import stage

pytestmark=pytest.mark.skipif(not BASE,reason="Live API required")

def new_student():
    from app.db.session import SessionLocal,engine
    from app.models.entities import User,UserRole
    from app.core.security import hash_password,create_access_token
    async def create():
        try:
            async with SessionLocal() as db:
                u=User(email=f"qa-dds-{uuid.uuid4()}@example.local",full_name="QA ДДС",role=UserRole.STUDENT,password_hash=hash_password("Qa123!"))
                db.add(u);await db.commit()
                return str(u.id),create_access_token(str(u.id),"STUDENT")
        finally: await engine.dispose()
    return asyncio.run(create())

def test_prepared_card_routing_profiles_and_end_to_end():
    uid,token=new_student()
    with login("teacher") as t,httpx.Client(base_url=BASE,headers={"Authorization":"Bearer "+token}) as s:
        version=stage(t,binary(sample_book()));vid=version["import_id"]
        assert t.post(f"/imports/classifier/{vid}/commit").status_code==200
        eid=t.get(f"/imports/classifier/{vid}/entries").json()["items"][0]["id"]
        r=t.post('/dds/routing/preview',json={"entry_id":eid,"facts":{}})
        assert r.status_code==200,r.text
        preview=r.json();assert preview["review_required"]
        services=preview["services"];selected=services[0]["key"];other=services[1]["key"]
        data={"entry_id":eid,"facts":{},"title":"QA карточка 112","address":"Учебная улица, 1","message":"Учебное происшествие","recipients":[selected]}
        assert t.post('/dds/scenarios',json=data).status_code==422
        assert t.post('/dds/scenarios',json={**data,"review_reason":"QA решение","recipients":["unknown"]}).status_code==422
        assert t.post('/dds/routing/preview',json={"entry_id":eid,"facts":{"casualties":"false"}}).status_code==422
        assert s.post('/dds/scenarios',json=data).status_code==403
        assert s.get('/dds/students').status_code==403
        r=t.post('/dds/scenarios',json={**data,"review_reason":"QA: выбран один получатель после разбора условий"})
        assert r.status_code==200,r.text
        scenario=r.json();routing=scenario["incident_payload"]["routing"]
        assert routing["import_id"]==vid and routing["reviewed_by"]
        assert t.post(f'/scenarios/{scenario["id"]}/publish').status_code==200
        sid=make_session(t,[scenario["id"]]);assert t.post(f'/sessions/{sid}/start').status_code==200
        assert sid not in [x['id'] for x in s.get('/sessions').json()]
        for endpoint in ('messages/receive','calls/start'):
            assert s.post(f'/sessions/{sid}/{endpoint}').status_code==409
        assert t.put(f'/dds/students/{uid}/profile',json={"service_key":other}).status_code==200
        assert s.post(f'/sessions/{sid}/messages/receive').status_code==409
        assert s.put(f'/dds/students/{uid}/profile',json={"service_key":selected}).status_code==403
        assert t.put(f'/dds/students/{uid}/profile',json={"service_key":selected}).status_code==200
        assert sid in [x['id'] for x in s.get('/sessions').json()]
        card=s.post(f'/sessions/{sid}/messages/receive').json();cid=card['call_id']
        assert card['provider']=='card112' and 'routing' not in card['body']
        assert card['body']['address']==data['address'] and card['body']['recipients'][0]['key']==selected
        assert s.post(f'/sessions/{sid}/calls/start').json()['call_id']==cid
        assert t.put(f'/dds/students/{uid}/profile',json={"service_key":other}).status_code==409
        assert s.post(f'/sessions/messages/{cid}/actions',json={"action_type":"SELECT_SERVICES","payload":{"services":[other]}}).status_code==422
        assert s.post(f'/sessions/messages/{cid}/actions',json={"action_type":"SELECT_STATUS","payload":{"status":"FAKE"}}).status_code==422
        for kind,payload in [('SELECT_STATUS',{'status':'ПРИНЯТО'}),('TEXT_INPUT',{'text':'Информация получена службой.'})]:
            assert s.post(f'/sessions/messages/{cid}/actions',json={'action_type':kind,'payload':payload}).status_code==200
        restored=s.post(f'/sessions/{sid}/messages/receive').json()
        assert len(restored['actions'])==2 and restored['started_at']==card['started_at']
        r=s.post(f'/sessions/messages/{cid}/complete');assert r.status_code==200,r.text
        assert r.json()['score']==r.json()['max_score']==3
        assert s.post(f'/sessions/{sid}/messages/receive').status_code==409
        assert t.post(f'/sessions/{sid}/finish').status_code==200
        report=next(r for r in t.get('/reports/assessments').json() if r['call_session_id']==cid)
        assert t.get(f'/reports/assessment/{report["id"]}.pdf').content.startswith(b'%PDF')
        assert t.put(f'/dds/students/{uid}/profile',json={"service_key":other}).status_code==200
