from dataclasses import dataclass

@dataclass
class ScoreResult:
    score: float
    max_score: float
    over_time: bool
    details: dict

def _payload_matches(expected: dict, actual: dict) -> bool:
    for key, value in expected.items():
        if isinstance(value,list) and isinstance(actual.get(key),list):
            if set(actual[key]) != set(value): return False
        elif actual.get(key) != value:
            return False
    return True

def score_actions(expected_actions, actual_actions, duration_sec: int, time_limit_sec: int, status_history: bool = False) -> ScoreResult:
    # Grade the submitted card; retain the full action history in the database.
    latest = {}
    events = []
    for action in actual_actions:
        if status_history and action.action_type == "SELECT_STATUS": events.append(action)
        elif not (status_history and action.action_type == "UPDATE_DDS"): latest[action.action_type] = action
    actual_actions = events + list(latest.values())
    matched = 0.0
    max_score = sum(float(x.weight) for x in expected_actions)
    errors = []
    used = set()
    matches = []
    for exp in sorted(expected_actions, key=lambda x: x.order_no):
        found = None
        for idx, act in enumerate(actual_actions):
            if idx in used or act.action_type != exp.action_type:
                continue
            if act.action_type == "TEXT_INPUT" and not act.payload.get("text", "").strip():
                continue
            if _payload_matches(exp.payload or {}, act.payload or {}):
                found = (idx, act)
                break
        if found:
            used.add(found[0]); matched += float(exp.weight); matches.append({"expected": exp.action_type, "action_id": str(found[1].id), "weight": exp.weight})
        elif getattr(exp, "required", True):
            errors.append({"code":"MISSING_REQUIRED_ACTION", "message":f"Не выполнено обязательное действие: {exp.action_type}", "severity":"ERROR"})
    for idx, act in enumerate(actual_actions):
        if idx not in used and not (status_history and act.action_type == "SELECT_STATUS"):
            errors.append({"code":"UNEXPECTED_ACTION", "message":f"Непредусмотренное действие: {act.action_type}", "severity":"WARNING", "action_id":str(act.id)})
    over_time = duration_sec > time_limit_sec
    if over_time:
        errors.append({"code":"TIME_LIMIT_EXCEEDED", "message":"Превышено нормативное время заполнения карточки", "severity":"ERROR"})
    return ScoreResult(round(matched, 2), round(max_score, 2), over_time, {"matches":matches, "errors":errors, "expected_count":len(expected_actions), "actual_count":len(actual_actions)})
