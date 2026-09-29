"""Opt-in browser check for admin controls and forced lesson completion.

Run inside the backend container after installing Playwright Chromium.
Creates only QA-prefixed records.
"""
import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/tests")
from test_dds_workflow import new_student
from test_workflow import login, make_scenario, make_session


class FrontendProxy(BaseHTTPRequestHandler):
    def do_GET(self):
        response = httpx.get("http://frontend:5173" + self.path, headers={"Host": "localhost:5173"})
        self.send_response(response.status_code)
        self.send_header("Content-Type", response.headers.get("content-type", "application/octet-stream"))
        self.end_headers()
        self.wfile.write(response.content)

    def log_message(self, *_):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 5173), FrontendProxy)
threading.Thread(target=server.serve_forever, daemon=True).start()
out = Path("/tmp/tz-quick-browser")
out.mkdir(exist_ok=True)
suffix = uuid.uuid4().hex[:8]
managed_email = f"qa-ui-managed-{suffix}@example.local"
session_title = f"QA досрочное завершение {suffix}"

student_id, student_token = new_student()
with login("teacher") as teacher:
    scenario, _ = make_scenario(teacher)
    assert teacher.post(f'/scenarios/{scenario["id"]}/publish').status_code == 200
    session_id = make_session(teacher, [scenario["id"]])
    # Give the browser test a unique, searchable title.
    from app.db.session import SessionLocal, engine
    from app.models.entities import TrainingSession
    import asyncio

    async def rename_session():
        try:
            async with SessionLocal() as db:
                row = await db.get(TrainingSession, uuid.UUID(session_id))
                row.title = session_title
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(rename_session())
    assert teacher.post(f"/sessions/{session_id}/start").status_code == 200

with httpx.Client(base_url="http://localhost:8000/api", headers={"Authorization": "Bearer " + student_token}) as student:
    call = student.post(f"/sessions/{session_id}/calls/start").json()
    call_id = call["call_id"]

page_errors = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="ru-RU", timezone_id="Europe/Moscow")
    page = context.new_page()
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def sign_in(email, password):
        page.goto("http://localhost:5173")
        page.get_by_label("Логин", exact=True).fill(email)
        page.get_by_label("Пароль", exact=True).fill(password)
        page.get_by_role("button", name="ВОЙТИ", exact=True).click()

    sign_in("admin@example.local", "Admin123!")
    expect(page.get_by_role("heading", name="Панель администратора")).to_be_visible()
    page.get_by_role("button", name="Пользователи", exact=True).click()
    expect(page.get_by_role("heading", name="Пользователи и роли")).to_be_visible()
    page.get_by_label("Логин (email)", exact=True).fill(managed_email)
    page.get_by_label("Имя", exact=True).fill("QA пользователь интерфейса")
    page.get_by_label("Начальный пароль", exact=True).fill("QaInterface123!")
    page.get_by_role("button", name="Создать пользователя", exact=True).click()
    row = page.locator("tbody tr").filter(has_text=managed_email)
    expect(row).to_have_count(1)
    row.get_by_role("combobox").select_option("TEACHER")
    expect(row.get_by_role("combobox")).to_have_value("TEACHER")
    row.get_by_role("button", name="Заблокировать", exact=True).click()
    expect(row).to_contain_text("Заблокирован")
    page.get_by_role("button", name="Состояние системы", exact=True).click()
    expect(page.get_by_role("heading", name="Состояние локального комплекса")).to_be_visible()
    expect(page.get_by_text("Доступна", exact=True)).to_be_visible()
    page.screenshot(path=str(out / "admin-system.png"), full_page=True)

    page.get_by_role("button", name="Выйти", exact=True).click()
    sign_in("teacher@example.local", "Teacher123!")
    expect(page.get_by_role("heading", name="Панель преподавателя")).to_be_visible()
    page.get_by_label("Показать записи автоматических проверок", exact=True).check()
    page.get_by_label("Поиск", exact=True).fill(session_title)
    session_row = page.locator(".session-list li").filter(has_text=session_title)
    expect(session_row).to_have_count(1)
    page.once("dialog", lambda dialog: dialog.accept())
    session_row.get_by_role("button", name="Завершить досрочно", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("Закрыто активных карточек: 1")
    expect(session_row).to_contain_text("Завершено")
    page.screenshot(path=str(out / "force-finish.png"), full_page=True)
    assert not page_errors, page_errors
    browser.close()

with httpx.Client(base_url="http://localhost:8000/api", headers={"Authorization": "Bearer " + student_token}) as student:
    restored = student.get(f"/sessions/messages/{call_id}").json()
    assert restored["completed_at"] and restored["assessment"]

result = {
    "managed_user": managed_email,
    "session": session_title,
    "student_id": student_id,
    "call_id": call_id,
    "checks": [
        "admin created a user",
        "admin changed the role",
        "admin blocked the account",
        "admin opened system status",
        "teacher force-finished an active card",
        "forced card contains an assessment",
    ],
    "page_errors": page_errors,
}
(out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
