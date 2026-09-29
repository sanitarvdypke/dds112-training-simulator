import pytest
import os
from pathlib import Path
from app.services.routing import matches, route

@pytest.mark.parametrize("condition,facts,expected", [
    ({"kind":"always"},{},True),
    ({"kind":"flag","feature":"casualties","value":True},{},None),
    ({"kind":"flag","feature":"casualties","value":True},{"casualties":False},False),
    ({"kind":"flag","feature":"casualties","value":False},{"casualties":False},True),
    ({"kind":"all_false","features":["a","b"]},{"a":False},None),
    ({"kind":"all_false","features":["a","b"]},{"a":False,"b":False},True),
    ({"kind":"all_false","features":["a","b"]},{"a":True},False),
    ({"kind":"unresolved","review_required":True},{},None),
])
def test_conditions(condition,facts,expected):
    assert matches(condition,facts) is expected

def test_no_response_is_not_a_recipient_and_uncertainty_is_visible():
    def rule(cell,key,effect,condition):
        return {"source_cell":cell,"service_key":key,"service_name":key,"effect":effect,"condition":condition}
    data={"rules":[rule("A1","a","NO_RESPONSE",{"kind":"always"}),
                   rule("B1","b","CLASSIFICATION",{"kind":"always"}),
                   rule("C1","c","CLASSIFICATION",{"kind":"unresolved"})]}
    result=route(data,{})
    assert result["recipients"]==[{"key":"b","name":"b"}]
    assert result["pending_cells"]==["C1"] and result["review_required"]

@pytest.mark.skipif(not os.getenv("EKP_SOURCE_PATH"), reason="Original EKP required")
def test_actual_ekp_traffic_accident_route():
    from app.services.classifier import parse_workbook
    parsed= parse_workbook(Path(os.environ["EKP_SOURCE_PATH"]).read_bytes())
    entry=next(r for r in parsed["rows"] if r.get("code")=="2010000")
    result=route(entry,{"road_blocked":False,"casualties":False,"offense":False})
    assert {r["name"] for r in result["recipients"]}=={"ЦОДД","Аппарат МЭРА","ГКУ НТУ","ФСО"}
    assert result["pending_cells"]==["V277"]
    assert result["review_required"]
    blocked=route(entry,{"road_blocked":True})
    assert "Мосгортранс" in {r["name"] for r in blocked["recipients"]}
