import httpx
import pytest
from test_workflow import BASE,make_session
from test_inbox_workflow import environment
from test_dds_workflow import new_student

pytestmark=pytest.mark.skipif(not BASE,reason='Live API required')

def test_approval_snapshot_detailed_reports_and_immutability(environment):
    t,s,_,scenarios,*_=environment
    rubric={'steps':[{'status':'ПРИНЯТО','weight':2,'within_sec':30,'anchor':'RECEIVED','require_comment':True},
        {'status':'РАБОТЫ ЗАВЕРШЕНЫ','weight':3,'within_sec':300,'anchor':'PREVIOUS'}],
        'require_comment':True,'required_fields':['measures','outcome'],'total_time_sec':600}
    assert t.put(f'/scenarios/{scenarios[0]}/rubric',json=rubric).status_code==409
    cloned=t.post(f'/scenarios/{scenarios[0]}/clone');assert cloned.status_code==200,cloned.text
    sid=cloned.json()['id']
    assert s.put(f'/scenarios/{sid}/rubric',json=rubric).status_code==403
    approved=t.put(f'/scenarios/{sid}/rubric',json=rubric);assert approved.status_code==200,approved.text
    approval=approved.json()['expected_state']['rubric_approval'];assert approval['approved_by']
    assert t.post(f'/scenarios/{sid}/publish').status_code==200
    session=make_session(t,[sid]);assert t.post(f'/sessions/{session}/start').status_code==200
    card=s.post(f'/sessions/{session}/messages/receive').json();cid=card['call_id']
    assert card['time_limit_sec']==600 and 'rubric' not in str(card['body'])
    assert card['norms']==[{'status':'ПРИНЯТО','within_sec':30,'from_status':'ПОЛУЧЕНА СЛУЖБОЙ'},
                            {'status':'РАБОТЫ ЗАВЕРШЕНЫ','within_sec':300,'from_status':'ПРИНЯТО'}]
    for kind,payload in [('SELECT_STATUS',{'status':'ПРИНЯТО','comment':'Проверено'}),('SELECT_STATUS',{'status':'РАБОТЫ ЗАВЕРШЕНЫ'}),
        ('UPDATE_DDS',{'fields':{'measures':'Проведён осмотр','outcome':'Опасность устранена'}}),('TEXT_INPUT',{'text':'=Учебный комментарий <тест>'})]:
        r=s.post(f'/sessions/messages/{cid}/actions',json={'action_type':kind,'payload':payload});assert r.status_code==200,r.text
    assert t.put(f'/scenarios/{sid}/rubric',json={**rubric,'total_time_sec':1}).status_code==409
    result=s.post(f'/sessions/messages/{cid}/complete');assert result.status_code==200,result.text
    assert result.json()['score']==result.json()['max_score']==8 and not result.json()['details']['errors']
    assert result.json()['details']['rubric_approval']==approval
    rid=next(r['id'] for r in t.get('/reports/assessments').json() if r['call_session_id']==cid)
    report=t.get(f'/reports/assessment/{rid}');assert report.status_code==200,report.text
    details=report.json()['details'];assert len(details['criteria'])==5 and len(details['history'])==7
    assert details['history'][-1]['action_type']=='COMPLETED'
    assert details['summary']['service'] and details['summary']['student']=='QA ДДС'
    for ext in ('.csv','.pdf',''):
        assert s.get(f'/reports/assessment/{rid}{ext}').status_code==403
        exported=t.get(f'/reports/assessment/{rid}{ext}');assert exported.status_code==200,exported.text[:100]
        if ext=='.csv':
            text=exported.content.decode('utf-8-sig');assert 'Критерий: ПРИНЯТО' in text and 'Проведён осмотр' in text and 'Учебный комментарий' in text
        if ext=='.pdf': assert exported.content.startswith(b'%PDF') and len(exported.content)>15000
    copied=t.post(f'/scenarios/{sid}/clone').json()
    assert not copied['expected_state'].get('rubric_approval')
    assert t.post(f'/scenarios/{copied["id"]}/publish').status_code==409
    assert t.post(f'/sessions/{session}/finish').status_code==200
