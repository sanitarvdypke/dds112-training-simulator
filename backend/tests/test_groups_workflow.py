import uuid

import httpx
import pytest

from test_dds_workflow import new_student
from test_workflow import BASE, login, make_scenario

pytestmark = pytest.mark.skipif(not BASE, reason="Live API required")


def test_teacher_manages_group_and_limits_session_access():
    student_id, token = new_student()
    suffix = uuid.uuid4().hex[:8]
    name = f"QA группа {suffix}"
    with login("teacher") as teacher, login("student") as outsider, httpx.Client(
        base_url=BASE, headers={"Authorization": "Bearer " + token}
    ) as member:
        assert outsider.get("/groups").status_code == 403
        created = teacher.post("/groups", json={"name": name, "member_ids": [student_id]})
        assert created.status_code == 200, created.text
        group = created.json()
        assert group["name"] == name and group["members"][0]["id"] == student_id
        assert teacher.post("/groups", json={"name": name.lower(), "member_ids": []}).status_code == 409
        renamed = teacher.put(f'/groups/{group["id"]}', json={"name": name + " обновлена", "member_ids": [student_id]})
        assert renamed.status_code == 200 and renamed.json()["name"].endswith("обновлена")

        scenario, _ = make_scenario(teacher)
        assert teacher.post(f'/scenarios/{scenario["id"]}/publish').status_code == 200
        session = teacher.post("/sessions", json={
            "title": "QA групповое занятие",
            "group_id": group["id"],
            "scenario_ids": [scenario["id"]],
        })
        assert session.status_code == 200, session.text
        session_id = session.json()["id"]
        assert session.json()["group_id"] == group["id"]
        assert teacher.post(f"/sessions/{session_id}/start").status_code == 200
        assert session_id in [row["id"] for row in member.get("/sessions").json()]
        assert session_id not in [row["id"] for row in outsider.get("/sessions").json()]
        assert teacher.delete(f'/groups/{group["id"]}').status_code == 409

