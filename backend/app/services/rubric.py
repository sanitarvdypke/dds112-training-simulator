from app.services.scoring import ScoreResult

def evaluate_rubric(rubric, actions, started_at, ended_at):
    """Use first occurrence: repeating a status cannot erase an ordering/deadline error."""
    first, fields = {}, {}
    for action in actions:
        if action.action_type == "SELECT_STATUS": first.setdefault(action.payload["status"], action)
        elif action.action_type == "UPDATE_DDS": fields.update(action.payload["fields"])
    criteria, errors = [], []
    previous = None
    for index, step in enumerate(rubric["steps"]):
        action = first.get(step["status"])
        ordered = bool(action) and (index == 0 or previous is not None and action.sequence_no > previous.sequence_no)
        anchor = started_at if step["anchor"] == "RECEIVED" else previous.occurred_at if previous else None
        elapsed = (action.occurred_at - anchor).total_seconds() if action and anchor else None
        limit = step.get("within_sec")
        timely = elapsed is not None and elapsed >= 0 and (limit is None or elapsed <= limit)
        comment_ok = not step.get("require_comment") or bool(action and action.payload.get("comment", "").strip())
        passed = bool(action and ordered and timely and comment_ok)
        codes = []
        if not action: codes.append(("MISSING_STATUS", "Не выполнен статус: " + step["status"]))
        elif not ordered: codes.append(("STATUS_ORDER", "Нарушен порядок статуса: " + step["status"]))
        if action and elapsed is not None and limit is not None and elapsed > limit:
            codes.append(("STATUS_DEADLINE", f"{step['status']}: {elapsed} сек при нормативе {limit} сек"))
        if action and not comment_ok: codes.append(("STATUS_COMMENT", "Нет комментария к статусу: " + step["status"]))
        for code, message in codes:
            errors.append({"code":code,"message":message,"severity":"ERROR","action_id":str(action.id) if action else None})
        criteria.append({"label":step["status"],"passed":passed,"score":step["weight"] if passed else 0,"max_score":step["weight"],
                         "action_id":str(action.id) if action else None,"elapsed_sec":elapsed,"limit_sec":limit,"anchor":step["anchor"],
                         "deviation_sec":round(max(0,elapsed-limit),6) if elapsed is not None and limit is not None else None})
        previous = action
    if rubric.get("require_comment"):
        passed = any(a.action_type == "TEXT_INPUT" and a.payload.get("text", "").strip() for a in actions)
        criteria.append({"label":"Отдельный комментарий диспетчера","passed":passed,"score":int(passed),"max_score":1})
        if not passed: errors.append({"code":"MISSING_COMMENT","message":"Не добавлен комментарий диспетчера","severity":"ERROR"})
    for field in rubric.get("required_fields", []):
        passed = bool(fields.get(field, "").strip())
        label = {"unit":"Подразделение / бригада","responsible":"Ответственный","measures":"Принятые меры","outcome":"Результат работ"}[field]
        criteria.append({"label":label,"passed":passed,"score":int(passed),"max_score":1})
        if not passed: errors.append({"code":"MISSING_DDS_FIELD","message":"Не заполнено поле: " + label,"severity":"ERROR"})
    duration = max(0, (ended_at-started_at).total_seconds())
    over_time = duration > rubric["total_time_sec"]
    if over_time: errors.append({"code":"TIME_LIMIT_EXCEEDED","message":"Превышено общее время практики по карточке","severity":"ERROR"})
    return ScoreResult(sum(c["score"] for c in criteria),sum(c["max_score"] for c in criteria),over_time,
                       {"criteria":criteria,"errors":errors,"rubric":rubric,"total_limit_sec":rubric["total_time_sec"],
                        "total_deviation_sec":round(max(0,duration-rubric["total_time_sec"]),3),"actual_count":len(actions)})
