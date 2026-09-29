"""Opt-in Chromium UI regression. Run inside backend with Playwright installed.
Creates only QA-prefixed data. Does not receive/complete the demo student's cards.
TEST_API_URL=http://localhost:8000/api python /tmp/stage5_browser_check.py
"""
import sys, os, json, uuid, threading
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import httpx
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0, '/app/tests')
sys.path.insert(0, '/app')
from test_dds_workflow import new_student
from test_workflow import login

class Proxy(BaseHTTPRequestHandler):
    def do_GET(self):
        response = httpx.get('http://frontend:5173' + self.path, headers={'Host':'localhost:5173'})
        self.send_response(response.status_code)
        self.send_header('Content-Type', response.headers.get('content-type', 'application/octet-stream'))
        self.end_headers()
        self.wfile.write(response.content)
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 5173), Proxy)
threading.Thread(target=server.serve_forever, daemon=True).start()
out = Path('/tmp/stage5'); out.mkdir(exist_ok=True)
uid, token = new_student()
title = 'QA браузер этап 5 ' + str(uuid.uuid4())[:8]
def checked(response):
    assert response.status_code == 200, response.text
    return response.json()
with login('teacher') as teacher:
    email = next(s['email'] for s in checked(teacher.get('/dds/students')) if s['id'] == uid)


errors = []; checks = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    context = browser.new_context(viewport={'width':1440,'height':1000}, locale='ru-RU', timezone_id='Europe/Moscow', accept_downloads=True)
    page = context.new_page(); page.on('pageerror', lambda e: errors.append(str(e)))
    def sign_in(email, password):
        page.goto('http://localhost:5173')
        page.get_by_label('Логин', exact=True).fill(email)
        page.get_by_label('Пароль', exact=True).fill(password)
        page.get_by_role('button', name='ВОЙТИ', exact=True).click()
    def button(name): return page.get_by_role('button', name=name, exact=True)
    sign_in('teacher@example.local','Teacher123!')
    expect(page.get_by_role('heading',name='Панель преподавателя')).to_be_visible()
    button('Обучающиеся и службы').click()
    page.get_by_label('Показать технические учётные записи').check()
    profile=page.locator('.dds-profile').filter(has_text=email)
    profile.get_by_label('Служба обучающегося').select_option('d6acee4b10902259')
    expect(page.get_by_role('status')).to_contain_text('Назначена служба: Полиция')
    button('ЕКП и подготовка карточек').click()
    versions=page.get_by_label('Загруженные версии')
    import_id='e0e407e4-524e-4250-bd4c-8f6392f682c5'
    for _ in range(30):
        if versions.locator('option[value="'+import_id+'"]').count(): break
        button('Следующие версии').click()
        expect(button('Следующие версии')).to_be_enabled()
    versions.select_option(import_id)
    page.get_by_label('Код или название',exact=True).fill('2010000')
    button('Найти').click()
    row=page.locator('.classifier tbody tr').filter(has_text='ДТП без пострадавших').filter(has_text='строка 277')
    row.get_by_role('button',name='Открыть',exact=True).click()
    composer=page.locator('.classifier-detail > .card')
    composer.get_by_label('Название',exact=True).fill(title)
    composer.get_by_label('Адрес',exact=True).fill('Учебная улица, дом 5')
    composer.get_by_label('Описание происшествия',exact=True).fill('Учебное ДТП без пострадавших. Два автомобиля перекрывают одну полосу. Требуется организация движения.')
    composer.get_by_label('Норматив, секунд',exact=True).fill('600')
    composer.get_by_role('button',name='Рассчитать получателей',exact=True).click()
    expect(composer.get_by_role('heading',name='Получатели карточки')).to_be_visible()
    for checkbox in composer.get_by_role('checkbox').all(): checkbox.uncheck()
    composer.get_by_role('checkbox',name='Полиция (МВД)',exact=True).check()
    composer.get_by_label('Пояснение решения по неоднозначным правилам / изменению получателей',exact=True).fill('Учебная проверка интерфейса службы полиции')
    composer.get_by_role('button',name='Сохранить сценарий карточки',exact=True).click()
    expect(composer.get_by_role('status')).to_contain_text('Черновик карточки сохранён')
    with login('teacher') as teacher:
        scenario=next(s for s in checked(teacher.get('/scenarios')) if s['title']==title)
    checks.append('teacher: assign DDS profile; EKP search, routing preview, create card in UI')
    button('Сценарии и эталоны').click()
    page.get_by_label('Показать записи автоматических проверок',exact=True).check()
    page.get_by_label('Поиск',exact=True).fill(title)
    page.get_by_text('Эталон и нормативы: '+title,exact=True).click()
    button('Сохранить и утвердить эталон').click()
    expect(page.get_by_text('Эталон утверждён. Теперь опубликуйте сценарий.',exact=True)).to_be_visible()
    button('Опубликовать').click()
    expect(page.locator('.scenario-list')).to_contain_text('Опубликован')
    checks.append('teacher: approve rubric and publish')
    button('Занятия').click()
    page.get_by_role('textbox',name='Название',exact=True).fill(title)
    page.get_by_label('Сценарий').select_option(scenario['id'])
    button('Создать занятие').click()
    page.get_by_label('Поиск',exact=True).fill(title)
    expect(page.locator('.session-list li')).to_have_count(1)
    button('Запустить').click()
    expect(page.locator('.session-list')).to_contain_text('Идёт занятие')
    checks.append('teacher: create and start session')
    button('Выйти').click()
    sign_in(email,'Qa123!')
    expect(page.get_by_role('heading',name='Поиск происшествий')).to_be_visible()
    page.get_by_label('Номер, тип происшествия, адрес или занятие',exact=True).fill(title)
    expect(button('Получить')).to_have_count(1)
    button('Получить').click()
    expect(page.locator('.incident-address')).to_have_text('Учебная улица, дом 5')
    expect(page.locator('.incident-timer')).to_contain_text('норматив 600 сек')
    page.screenshot(path=str(out/'card.png'),full_page=True)
    checks.append('student: search and receive immutable 112 card; timer')
    for status in ['ПРИНЯТО','НАЧАЛО РЕАГИРОВАНИЯ','РАБОТЫ ЗАВЕРШЕНЫ']:
        button('Изменить статус').click()
        if status == 'ПРИНЯТО':
            page.keyboard.press('Escape')
            expect(page.get_by_role('dialog',name='Изменить статус службы',exact=True)).not_to_be_visible()
            button('Изменить статус').click()
        page.get_by_label('Новый статус').select_option(status)
        page.get_by_role('textbox',name='Комментарий к статусу',exact=True).fill('Учебная фиксация: '+status)
        if status == 'ПРИНЯТО': page.screenshot(path=str(out/'status.png'),full_page=True)
        button('Зафиксировать статус').click()
        expect(page.get_by_role('dialog',name='История службы',exact=True)).to_contain_text(status)
        if status == 'ПРИНЯТО': page.screenshot(path=str(out/'history.png'),full_page=True)
        button('Закрыть историю').click()
    button('Обработка ДДС').click()
    page.get_by_role('textbox',name='Подразделение / бригада',exact=True).fill('Учебный экипаж № 5')
    page.get_by_role('textbox',name='Ответственный',exact=True).fill('Диспетчер учебной службы')
    page.get_by_role('textbox',name='Принятые меры',exact=True).fill('Организовано безопасное движение транспорта.')
    page.get_by_role('textbox',name='Результат работ',exact=True).fill('Проезжая часть освобождена.')
    page.once('dialog',lambda d:d.dismiss())
    button('Выйти').click()
    expect(page.get_by_role('textbox',name='Результат работ',exact=True)).to_have_value('Проезжая часть освобождена.')
    expect(button('Завершить практику')).to_be_disabled()
    button('Сохранить сведения ДДС').click()
    expect(button('Сохранить сведения ДДС')).to_be_disabled()
    page.get_by_role('textbox',name='Новая запись',exact=True).fill('Учебное происшествие отработано. Пострадавших нет.')
    button('Добавить комментарий').click()
    expect(page.get_by_role('textbox',name='Новая запись',exact=True)).to_have_value('')
    page.screenshot(path=str(out/'work.png'),full_page=True)
    page.reload()
    expect(page.locator('.incident-address')).to_be_visible()
    button('Обработка ДДС').click()
    expect(page.get_by_role('textbox',name='Принятые меры',exact=True)).to_have_value('Организовано безопасное движение транспорта.')
    checks.append('student: status history, DDS fields, comment, dirty guard, reload persistence')
    page.set_viewport_size({'width':390,'height':844})
    button('Карточка 112').click()
    page.screenshot(path=str(out/'mobile-card.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflows horizontally'
    page.set_viewport_size({'width':1440,'height':1000})
    button('Завершить практику').click()
    expect(page.get_by_role('heading',name='Результат практики')).to_be_visible()
    expect(page.locator('.score')).to_have_text('9 / 9')
    expect(page.get_by_text('Ошибок нет.',exact=True)).to_be_visible()
    page.screenshot(path=str(out/'result.png'),full_page=True)
    button('Карточка 112').click()
    expect(button('Изменить статус')).to_be_disabled()
    button('← К списку').click()
    page.get_by_label('Показать').select_option('COMPLETED')
    expect(button('Просмотреть')).to_have_count(1)
    button('Просмотреть').click()
    button('Результат').click()
    expect(page.locator('.score')).to_have_text('9 / 9')
    checks.append('student: mobile layout, completion 9/9, immutable archive')
    button('Выйти').click()
    sign_in('teacher@example.local','Teacher123!')
    button('Отчёты').click()
    page.get_by_label('Показать записи автоматических проверок',exact=True).check()
    page.get_by_label('Поиск',exact=True).fill(title)
    button('Подробный отчёт').click()
    expect(page.get_by_role('heading',name='Оценка по критериям')).to_be_visible()
    expect(page.get_by_role('heading',name='Журнал действий')).to_be_visible()
    for ext in ['CSV','PDF']:
        with page.expect_download() as download:
            button(ext).click()
        target=out/('report.'+ext.lower()); download.value.save_as(target)
        assert target.stat().st_size>100
        if ext=='PDF': assert target.read_bytes().startswith(b'%PDF')
    page.screenshot(path=str(out/'report.png'),full_page=True)
    button('Занятия').click();page.get_by_label('Поиск',exact=True).fill(title)
    button('Завершить занятие').click()
    expect(page.locator('.session-list')).to_contain_text('Завершено')
    checks.append('teacher: detailed report, real CSV/PDF downloads, finish session')
    button('Выйти').click();sign_in('admin@example.local','Admin123!')
    expect(page.get_by_role('heading',name='Панель администратора')).to_be_visible()
    checks.append('admin: login')
    assert not errors, errors
    browser.close()
result={'title':title,'student_id':uid,'scenario_id':scenario['id'],'checks':checks,'page_errors':errors}
(out/'browser-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
