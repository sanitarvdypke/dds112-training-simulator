"""Inbox and immutable per-student DDS history against real API/PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import httpx
import pytest
from test_workflow import login, BASE, make_session
from test_dds_workflow import new_student
from test_classifier import sample_book, binary
from test_classifier_workflow import stage

pytestmark=pytest.mark.skipif(not BASE,reason="Live API required")

@pytest.fixture
def environment():
    uid, token=new_student()
    with login('teacher') as teacher, httpx.Client(base_url=BASE,headers={'Authorization':'Bearer '+token},timeout=30) as student:
        version=stage(teacher,binary(sample_book()));vid=version['import_id']
        assert teacher.post(f'/imports/classifier/{vid}/commit').status_code==200
        eid=teacher.get(f'/imports/classifier/{vid}/entries').json()['items'][0]['id']
        services=teacher.post('/dds/routing/preview',json={'entry_id':eid}).json()['services']
        service,other=services[0]['key'],services[1]['key']
        assert teacher.put(f'/dds/students/{uid}/profile',json={'service_key':service}).status_code==200
        scenarios=[]
        for index,recipient in enumerate([service,service,other]):
            r=teacher.post('/dds/scenarios',json={'entry_id':eid,'title':f'QA inbox {index}','address':f'Учебная улица, {index}',
                'message':'Учебная карточка 112','recipients':[recipient],'review_reason':'QA: проверка адресации','time_limit_sec':3600})
            assert r.status_code==200,r.text
            scenario=r.json();scenarios.append(scenario['id'])
            assert teacher.post(f'/scenarios/{scenario["id"]}/publish').status_code==200
        sid=make_session(teacher,scenarios)
        assert teacher.post(f'/sessions/{sid}/start').status_code==200
        yield teacher,student,sid,scenarios,uid,service,other

def rows(student,sid):
    response=student.get('/sessions/inbox');assert response.status_code==200,response.text
    return [r for r in response.json() if r['session_id']==sid]

def test_targeted_receive_history_archive_and_isolation(environment):
    t,s,sid,scenarios,uid,service,other=environment
    before=rows(s,sid)
    assert {r['scenario_id'] for r in before}==set(scenarios[:2])
    assert all(r['state']=='NEW' and not r['call_id'] and not r['received_at'] for r in before)
    assert rows(s,sid)==before  # Reading the inbox never starts the timer or allocates a card.
    assert t.get('/sessions/inbox').status_code==403
    assert s.post(f'/sessions/{sid}/messages/receive',params={'scenario_id':scenarios[2]}).status_code==404
    response=s.post(f'/sessions/{sid}/messages/receive',params={'scenario_id':scenarios[1]})
    assert response.status_code==200,response.text
    card=response.json();cid=card['call_id']
    assert card['body']['address']=='Учебная улица, 1' and 'routing' not in card['body']
    assert s.post(f'/sessions/{sid}/messages/receive',params={'scenario_id':scenarios[0]}).status_code==409
    statuses=['ПРИНЯТО','НАЧАЛО РЕАГИРОВАНИЯ','ПРИБЫТИЕ','ПРОВЕДЕНИЕ РАБОТ','РАБОТЫ ЗАВЕРШЕНЫ']
    for status in statuses:
        r=s.post(f'/sessions/messages/{cid}/actions',json={'action_type':'SELECT_STATUS','payload':{'status':status,'comment':'Запись: '+status}})
        assert r.status_code==200,r.text
    for fields in ({'unit':'Бригада 7','responsible':'Диспетчер','measures':'Направлена бригада'}, {'measures':'Осмотр завершён','outcome':'Работы выполнены'}):
        assert s.post(f'/sessions/messages/{cid}/actions',json={'action_type':'UPDATE_DDS','payload':{'fields':fields}}).status_code==200
    for text in ['Информация принята.','Обработка завершена.']:
        assert s.post(f'/sessions/messages/{cid}/actions',json={'action_type':'TEXT_INPUT','payload':{'text':text}}).status_code==200
    restored=s.get(f'/sessions/messages/{cid}').json()
    assert restored['started_at']==card['started_at'] and restored['number']==card['number']
    assert restored['dds_fields']=={'unit':'Бригада 7','responsible':'Диспетчер','measures':'Осмотр завершён','outcome':'Работы выполнены'}
    assert [a['payload']['status'] for a in restored['actions'] if a['action_type']=='SELECT_STATUS']==statuses
    assert len(restored['timeline'])==11 and restored['timeline'][0]['action_type']=='ADDED' and restored['timeline'][1]['action_type']=='RECEIVED'
    assert all(a['actor']=='QA ДДС' and a['service']==restored['service_name'] for a in restored['timeline'][1:])
    assert [a['sequence_no'] for a in restored['actions']]==list(range(1,10))
    times=[datetime.fromisoformat(a['occurred_at']) for a in restored['timeline']]
    assert times==sorted(times) and all(d.tzinfo for d in times)
    assert next(r for r in rows(s,sid) if r['call_id']==cid)['service_status']=='РАБОТЫ ЗАВЕРШЕНЫ'
    result=s.post(f'/sessions/messages/{cid}/complete').json()
    assert result['score']==result['max_score']==3 and result['details']['errors']==[]
    archived=s.get(f'/sessions/messages/{cid}').json()
    assert archived['assessment']==result and archived['timeline'][-1]['action_type']=='COMPLETED'
    assert archived['timeline'][:-1]==restored['timeline']
    assert s.post(f'/sessions/messages/{cid}/actions',json={'action_type':'TEXT_INPUT','payload':{'text':'Позднее изменение'}}).status_code==409
    _,token=new_student()
    with httpx.Client(base_url=BASE,headers={'Authorization':'Bearer '+token}) as stranger:
        assert stranger.get(f'/sessions/messages/{cid}').status_code==404
        assert not rows(stranger,sid)
    assert t.put(f'/dds/students/{uid}/profile',json={'service_key':other}).status_code==200
    assert s.get(f'/sessions/messages/{cid}').json()['service_name']==restored['service_name']
    remaining=rows(s,sid)
    assert {r['scenario_id'] for r in remaining}=={scenarios[1],scenarios[2]}
    assert next(r for r in remaining if r['call_id']==cid)['state']=='COMPLETED'
    assert t.post(f'/sessions/{sid}/finish').status_code==200
    assert [r['call_id'] for r in rows(s,sid)]==[cid]

def test_invalid_changes_do_not_enter_history(environment):
    _,s,sid,scenarios,*_=environment
    card=s.post(f'/sessions/{sid}/messages/receive',params={'scenario_id':scenarios[0]}).json();cid=card['call_id']
    bad=[('UPDATE_DDS',{'fields':{'address':'Подмена'}}),('UPDATE_DDS',{'fields':{'unit':123}}),
         ('UPDATE_DDS',{'fields':{'unit':'x'*201}}),('UPDATE_DDS',{'fields':{}}),
         ('TEXT_INPUT',{'text':'  '}),('TEXT_INPUT',{'text':'x'*4001}),
         ('SELECT_STATUS',{'status':'ПРИНЯТО','comment':5}),('SELECT_STATUS',{'status':'ПРИНЯТО','occurred_at':'2020-01-01'}),
         ('SELECT_STATUS',{'status':'FAKE'})]
    for kind,payload in bad:
        assert s.post(f'/sessions/messages/{cid}/actions',json={'action_type':kind,'payload':payload}).status_code==422
    after=s.get(f'/sessions/messages/{cid}').json()
    assert after['actions']==[] and after['body']==card['body'] and not after['dds_fields']
    assert s.post(f'/sessions/messages/{cid}/complete').status_code==200

def test_concurrent_receive_and_action_sequence(environment):
    t,s,sid,scenarios,*_=environment
    def receive(_):
        with httpx.Client(base_url=BASE,headers=dict(s.headers),timeout=30) as client:
            r=client.post(f'/sessions/{sid}/messages/receive',params={'scenario_id':scenarios[0]})
            assert r.status_code==200,r.text
            return r.json()['call_id']
    with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(receive,range(2)))
    assert len(set(ids))==1;cid=ids[0]
    def comment(n):
        with httpx.Client(base_url=BASE,headers=dict(s.headers),timeout=30) as client:
            r=client.post(f'/sessions/messages/{cid}/actions',json={'action_type':'TEXT_INPUT','payload':{'text':f'Комментарий {n}'}})
            assert r.status_code==200,r.text
            return r.json()['sequence_no']
    with ThreadPoolExecutor(max_workers=4) as pool: sequence=list(pool.map(comment,range(4)))
    assert sorted(sequence)==[1,2,3,4]
    history=s.get(f'/sessions/messages/{cid}').json()['actions']
    assert len({a['id'] for a in history})==4
    assert {a['payload']['text'] for a in history}=={f'Комментарий {n}' for n in range(4)}
    assert s.post(f'/sessions/messages/{cid}/complete').status_code==200
    assert t.post(f'/sessions/{sid}/finish').status_code==200
