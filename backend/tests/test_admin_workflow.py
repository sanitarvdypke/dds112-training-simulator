import uuid

import httpx
import pytest

from test_dds_workflow import new_student
from test_workflow import BASE, login, make_scenario, make_session

pytestmark = pytest.mark.skipif(not BASE, reason="Live API required")


def test_admin_user_management_and_system_status():
    suffix = uuid.uuid4().hex[:10]
    email = f"qa-managed-{suffix}@example.local"
    with login("admin") as admin, login("teacher") as teacher, login("student") as student:
        assert teacher.get("/admin/users").status_code == 403
        assert student.get("/admin/system").status_code == 403
        created = admin.post("/admin/users", json={
            "email": email,
            "full_name": "QA управляемый пользователь",
            "password": "QaManaged123!",
            "role": "STUDENT",
        })
        assert created.status_code == 200, created.text
        row = created.json()
        assert row["is_active"] and row["role"] == "STUDENT"
        assert admin.post("/admin/users", json={
            "email": email,
            "full_name": "QA дубль",
            "password": "QaManaged123!",
            "role": "STUDENT",
        }).status_code == 409
        changed = admin.put(f'/admin/users/{row["id"]}', json={"role": "TEACHER"})
        assert changed.status_code == 200 and changed.json()["role"] == "TEACHER"
        assert admin.put(f'/admin/users/{row["id"]}', json={"is_active": False}).status_code == 200
        with httpx.Client(base_url=BASE) as anonymous:
            assert anonymous.post("/auth/login", json={"email": email, "password": "QaManaged123!"}).status_code == 401
        own = admin.get("/auth/me").json()["id"]
        assert admin.put(f"/admin/users/{own}", json={"is_active": False}).status_code == 409
        status = admin.get("/admin/system")
        assert status.status_code == 200, status.text
        assert status.json()["status"] == "ok" and status.json()["database"] == "available"
        assert status.json()["users"]["total"] >= 4 and status.json()["audit_events"] > 0
        assert status.json()["host"]["cpu_count"] >= 1
        assert status.json()["host"]["disk_total_bytes"] > status.json()["host"]["disk_free_bytes"]


def test_teacher_can_force_finish_active_practice_with_report():
    uid, token = new_student()
    with login("teacher") as teacher, httpx.Client(base_url=BASE, headers={"Authorization": "Bearer " + token}) as student:
        scenario, _ = make_scenario(teacher, 120)
        assert teacher.post(f'/scenarios/{scenario["id"]}/publish').status_code == 200
        session_id = make_session(teacher, [scenario["id"]])
        assert teacher.post(f"/sessions/{session_id}/start").status_code == 200
        card = student.post(f"/sessions/{session_id}/calls/start").json()
        call_id = card["call_id"]
        assert student.post(f"/sessions/calls/{call_id}/actions", json={
            "action_type": "SELECT_INCIDENT", "payload": {"category": scenario["category"]}
        }).status_code == 200
        assert teacher.post(f"/sessions/{session_id}/finish").status_code == 409
        finished = teacher.post(f"/sessions/{session_id}/finish?force=true")
        assert finished.status_code == 200, finished.text
        assert finished.json()["forced_cards"] == 1
        restored = student.get(f"/sessions/messages/{call_id}")
        assert restored.status_code == 200 and restored.json()["completed_at"]
        assert restored.json()["assessment"]["score"] < restored.json()["assessment"]["max_score"]
        assert student.post(f"/sessions/calls/{call_id}/actions", json={
            "action_type": "TEXT_INPUT", "payload": {"text": "Позднее действие"}
        }).status_code == 409
        report = next(r for r in teacher.get("/reports/assessments").json() if r["call_session_id"] == call_id)
        assert report["details"]["history"][-1]["action_type"] == "COMPLETED"
        summary = teacher.get("/reports/summary?include_qa=true")
        assert summary.status_code == 200, summary.text
        progress = next(row for row in summary.json()["students"] if row["student_id"] == uid)
        assert progress["attempts"] >= 1 and progress["recent"]
