# API

`POST /api/auth/login` — JWT.
`GET /api/auth/me` — текущий пользователь.
`GET /api/admin/users` — список пользователей для администратора.
`POST /api/admin/users` — создание пользователя с ролью и начальным паролем.
`PUT /api/admin/users/{id}` — изменение роли, блокировка или разблокировка.
`GET /api/admin/system` — состояние приложения, БД и ресурсов контейнера.
`GET /api/groups` — учебные группы и их участники.
`POST /api/groups` — создание группы.
`PUT /api/groups/{id}` — изменение названия и состава группы.
`DELETE /api/groups/{id}` — удаление группы, если она ещё не использована в занятии.
`GET /api/scenarios` — список сценариев.
`POST /api/scenarios` — создание сценария преподавателем/администратором.
`POST /api/scenarios/generate` — генерация AI-кандидата; публикация выполняется отдельно преподавателем.
`POST /api/scenarios/{id}/publish` — подтверждение/публикация.
`POST /api/sessions` — создание занятия.
`GET /api/sessions` — список занятий.
`POST /api/sessions/{id}/start` — старт занятия.
`POST /api/sessions/{id}/finish` — завершение занятия.
`POST /api/sessions/{id}/calls/start` — старт учебного вызова студентом.
`POST /api/sessions/calls/{call_id}/actions` — журнал действия студента.
`POST /api/sessions/calls/{call_id}/complete` — завершение карточки и deterministic scoring + AI feedback.
`GET /api/reports/assessment/{id}.csv` — CSV.
`GET /api/reports/assessment/{id}.pdf` — PDF.
`GET /api/reports/summary` — сводка и динамика результатов обучающихся.
`POST /api/imports/classifier/preview` — preview XLSX.
`POST /api/imports/classifier/stage` — staging.
`POST /api/imports/classifier/{id}/commit` — commit после validation.
`WS /api/sessions/ws/{session_id}` — канал учебных событий.


## Уточнения после проверки

- GET /api/reports/assessments — результаты с id, call_session_id, student, session, score, max_score, duration_sec, over_time, details.
- GET /api/scenarios — только преподаватель/администратор (содержит эталон).
- calls/start возвращает активную карточку повторно с тем же call_id, started_at и actions. После завершения переходит к следующему сценарию; когда все пройдены — 409.
- POST сценария создаёт карточку и эталон оценки; time_limit_sec задаётся при создании (1–3600, по умолчанию 120).
- Действия: SELECT_INCIDENT/category, SELECT_STATUS/status, SELECT_SERVICES/services[], SELECT_TAGS/tags[], TEXT_INPUT/text.
- Поздние действия запрещены. Итоговая оценка использует последние значения полей.
- Обычное завершение занятия при активных карточках — 409. `POST /sessions/{id}/finish?force=true` досрочно закрывает активные карточки, рассчитывает результат по уже выполненным действиям и завершает занятие. Повторный запуск — 409.
- Преподаватель управляет своими занятиями и видит свои отчёты; администратор — все. `POST /api/sessions` принимает `group_id`, и групповое занятие доступно только его участникам.
- WebSocket: первый JSON-пакет должен содержать token с JWT, затем доступны ACK. Это канал подтверждений, не готовый мониторинг.
- Импорт XLSX хранит исходные строки; автоматическое подключение к вариантам полей карточки не реализовано.


## Классификатор ЕКП после этапа 1

- POST /api/imports/classifier/preview — разбор без сохранения, формат, статистика, первые строки, структура шапки, ошибки, замечания.
- POST /api/imports/classifier/stage — сохранение проверенного черновика с SHA-256 и исходными ячейками.
- POST /api/imports/classifier/{id}/commit — атомарное создание нормализованных записей; повторное подтверждение идемпотентно. Только автор/администратор.
- GET /api/imports/classifier?offset=0&limit=30 — версии источника.
- GET /api/imports/classifier/{id} — структура, каталог служб, статистика, диагностика.
- GET /api/imports/classifier/{id}/entries?q=ДТП&service_key=...&review_only=false&offset=0&limit=25 — поиск в сохранённой версии.
- GET /api/imports/classifier/{id}/entries/{entry_id} — все исходные ячейки, признаки и правила одного происшествия.

Чтение и импорт доступны ADMIN/TEACHER, STUDENT получает 403. Служебные справочники являются общей библиотекой преподавателей.
Новый обычный XLSX сохраняется как format=generic без создания записей ЕКП. Старые format=legacy импорты не мигрируются автоматически из усечённых данных; для нормализации нужен исходник.
Замечания разрешают сохранение источника, но не означают утверждение неоднозначного правила. Автоматическая выдача карточек на основе ЕКП — следующий этап.


## Этап 2: ДДС
- GET `/api/dds/services`, GET `/api/dds/students` — справочник служб и профили учеников (преподаватель/администратор).
- PUT `/api/dds/students/{id}/profile` — `{service_key}`; активная карточка блокирует смену.
- POST `/api/dds/routing/preview` — `{entry_id, facts}`; возвращает получателей, неопределённые ячейки и основания.
- POST `/api/dds/scenarios` — `{entry_id, facts, title, address, message, recipients, review_reason, time_limit_sec}`. Получатели — ключи служб; при неоднозначности или ручном изменении обязателен review_reason. Черновик публикуется обычным endpoint scenarios.
- GET `/api/sessions?messages_only=true` — занятия с карточками ЕКП, с учётом профиля ученика.
- POST `/api/sessions/{id}/messages/receive` — получить/восстановить адресованную карточку.
- POST `/api/sessions/messages/{id}/actions`, POST `/api/sessions/messages/{id}/complete` — действия и завершение.
Совместимые URL calls сохранены; телефонный провайдер не вызывается.

## Этап 3: список и история
- GET `/api/sessions/inbox` — ученик: адресованные новые карточки и собственные попытки, состояния NEW/ACTIVE/COMPLETED. Чтение не запускает таймер.
- POST `/api/sessions/{session_id}/messages/receive?scenario_id={uuid}` — получить выбранную карточку; другая активная карточка того же занятия даёт 409.
- GET `/api/sessions/messages/{call_id}` — собственная активная или завершённая карточка, timeline, dds_fields, service_status, assessment.
- Действие SELECT_STATUS принимает `{status, comment?}`; добавлены ПРИБЫТИЕ и ПРОВЕДЕНИЕ РАБОТ.
- UPDATE_DDS принимает `{fields:{unit?,responsible?,measures?,outcome?}}`: частичное обновление, неизвестные поля запрещены; длина unit/responsible до 200, measures/outcome до 4000.
- TEXT_INPUT для DDS_MESSAGE принимает непустой text до 4000 символов. Время действия выставляет сервер.
- actions включают id, sequence_no, occurred_at, actor и service; timeline дополнительно содержит события добавления, получения и завершения. Завершённая карточка доступна только для чтения.

## Этап 4: эталон и отчёт
- PUT `/api/scenarios/{id}/rubric` — владелец-преподаватель/администратор, только черновик DDS_MESSAGE. Тело: steps (status, weight 1–20, within_sec 1–3600 либо null, anchor RECEIVED/PREVIOUS, require_comment), total_time_sec 1–3600, require_comment, required_fields из unit/responsible/measures/outcome. Сохранение одновременно утверждает эталон.
- POST `/api/scenarios/{id}/clone` — отдельный черновик, утверждение не переносится.
- GET `/api/reports/assessment/{id}` — подробный результат для преподавателя-владельца занятия/администратора. CSV/PDF по прежним адресам, с критериями и историей.
- Полученная карточка возвращает norms (status, within_sec, from_status); снимок самого эталона хранится внутри попытки. После завершения details содержит criteria, history, summary, rubric_approval, dds_fields и отклонения времени.
- Старые карточки без снимка нового эталона оцениваются по прежним правилам.
