from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.schemas.rubric import Rubric
from app.services.rubric import evaluate_rubric

START=datetime(2026,9,29,tzinfo=timezone.utc)
def config():
    return Rubric(steps=[{'status':'ПРИНЯТО','within_sec':30},{'status':'НАЧАЛО РЕАГИРОВАНИЯ','within_sec':60,'anchor':'PREVIOUS','require_comment':True}],required_fields=['outcome'],total_time_sec=120).model_dump()
def action(n,seconds,status=None,kind='SELECT_STATUS',payload=None):
    return SimpleNamespace(id=str(n),sequence_no=n,occurred_at=START+timedelta(seconds=seconds),action_type=kind,payload=payload if payload is not None else {'status':status,'comment':'Обоснование'})
def complete_actions(first=30,second=90):
    return [action(1,first,'ПРИНЯТО'),action(2,second,'НАЧАЛО РЕАГИРОВАНИЯ'),action(3,95,kind='TEXT_INPUT',payload={'text':'Готово'}),action(4,100,kind='UPDATE_DDS',payload={'fields':{'outcome':'Выполнено'}})]

def test_exact_deadlines_and_total_boundary():
    result=evaluate_rubric(config(),complete_actions(),START,START+timedelta(seconds=120))
    assert result.score==result.max_score==6 and not result.details['errors'] and not result.over_time
    assert [c['elapsed_sec'] for c in result.details['criteria'][:2]]==[30,60]

@pytest.mark.parametrize('delay',[0.001,0.000001])
def test_subsecond_late_is_not_rounded_away(delay):
    result=evaluate_rubric(config(),complete_actions(30+delay,90+delay*2),START,START+timedelta(seconds=120.001))
    assert result.score==2 and result.over_time
    assert [e['code'] for e in result.details['errors']].count('STATUS_DEADLINE')==2
    assert result.details['total_deviation_sec']==0.001

def test_out_of_order_cannot_be_repaired_by_repeat():
    events=[action(1,2,'НАЧАЛО РЕАГИРОВАНИЯ'),action(2,3,'ПРИНЯТО'),action(3,4,'НАЧАЛО РЕАГИРОВАНИЯ')]
    result=evaluate_rubric(config(),events,START,START+timedelta(seconds=5))
    assert result.score==2
    assert any(e['code']=='STATUS_ORDER' for e in result.details['errors'])
    assert result.details['criteria'][1]['action_id']=='1'

def test_missing_previous_event_and_missing_comment():
    result=evaluate_rubric(config(),[action(1,3,kind='SELECT_STATUS',payload={'status':'НАЧАЛО РЕАГИРОВАНИЯ'})],START,START+timedelta(seconds=5))
    assert result.score==0
    assert {'MISSING_STATUS','STATUS_ORDER','STATUS_COMMENT','MISSING_COMMENT','MISSING_DDS_FIELD'} <= {e['code'] for e in result.details['errors']}
    assert result.details['criteria'][1]['elapsed_sec'] is None

def test_latest_field_clear_removes_credit():
    events=complete_actions()+[action(5,101,kind='UPDATE_DDS',payload={'fields':{'outcome':''}})]
    result=evaluate_rubric(config(),events,START,START+timedelta(seconds=110))
    assert result.score==5 and result.details['errors'][0]['code']=='MISSING_DDS_FIELD'

@pytest.mark.parametrize('patch',[
    {'steps':[]},{'steps':[{'status':'FAKE'}]},
    {'steps':[{'status':'ПРИНЯТО','anchor':'PREVIOUS'}]},
    {'steps':[{'status':'ПРИНЯТО'},{'status':'ПРИНЯТО'}]},
    {'required_fields':['address']},{'total_time_sec':0},
])
def test_invalid_rubric(patch):
    with pytest.raises(ValidationError): Rubric.model_validate({**config(),**patch})
