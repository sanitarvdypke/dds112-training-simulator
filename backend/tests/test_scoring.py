from types import SimpleNamespace
from app.services.scoring import score_actions

def test_required_actions_and_time_limit():
    expected=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":"ПРИНЯТО"},weight=2,order_no=1,id="e1"),SimpleNamespace(action_type="TEXT_INPUT",payload={"text":"ok"},weight=1,order_no=2,id="e2")]
    actual=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":"ПРИНЯТО"},id="a1"),SimpleNamespace(action_type="TEXT_INPUT",payload={"text":"ok"},id="a2")]
    r=score_actions(expected,actual,100,120)
    assert r.score==3 and not r.over_time and not r.details["errors"]

def test_missing_and_over_time():
    expected=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":"ПРИНЯТО"},weight=2,order_no=1,id="e1")]
    r=score_actions(expected,[],121,120)
    assert r.over_time and len(r.details["errors"])==2

def test_final_value_overrides_previous_correct_value():
    expected=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":"ПРИНЯТО"},weight=2,order_no=1)]
    actual=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":s},id=str(i)) for i,s in enumerate(["ПРИНЯТО","НЕ ПРИНЯТО"])]
    assert score_actions(expected,actual,120,120).score==0

def test_empty_comment_not_accepted_by_generic_requirement():
    expected=[SimpleNamespace(action_type="TEXT_INPUT",payload={},weight=1,order_no=1)]
    actual=[SimpleNamespace(action_type="TEXT_INPUT",payload={"text":" "},id="a")]
    assert score_actions(expected,actual,1,120).score==0

def test_timer_boundary():
    assert not score_actions([],[],120,120).over_time
    assert score_actions([],[],121,120).over_time

def test_dds_acceptance_is_retained_after_work_statuses():
    expected=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":"ПРИНЯТО"},weight=2,order_no=1)]
    actual=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":s},id=str(i)) for i,s in enumerate(["ПРИНЯТО","НАЧАЛО РЕАГИРОВАНИЯ","ПРИБЫТИЕ","ПРОВЕДЕНИЕ РАБОТ","РАБОТЫ ЗАВЕРШЕНЫ"])]
    actual.append(SimpleNamespace(action_type="UPDATE_DDS",payload={"fields":{"unit":"7"}},id="fields"))
    result=score_actions(expected,actual,120,120,status_history=True)
    assert result.score==2 and not result.details["errors"]
    assert result.details["matches"][0]["action_id"]=="0"

def test_dds_work_completion_does_not_substitute_for_acceptance():
    expected=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":"ПРИНЯТО"},weight=2,order_no=1)]
    actual=[SimpleNamespace(action_type="SELECT_STATUS",payload={"status":"РАБОТЫ ЗАВЕРШЕНЫ"},id="a")]
    result=score_actions(expected,actual,10,120,status_history=True)
    assert result.score==0 and result.details["errors"][0]["code"]=="MISSING_REQUIRED_ACTION"
