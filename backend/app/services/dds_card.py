"""Public DDS card state. Status order is recorded, not inferred from screenshots."""
DDS_STATUSES = ["ПРИНЯТО", "НЕ ПРИНЯТО", "НАЧАЛО РЕАГИРОВАНИЯ", "ПРИБЫТИЕ",
                "ПРОВЕДЕНИЕ РАБОТ", "ОТКАЗ ОТ ВЫПОЛНЕНИЯ РАБОТ", "РАБОТЫ ЗАВЕРШЕНЫ"]
DDS_FIELDS = {"unit": 200, "responsible": 200, "measures": 4000, "outcome": 4000}

def public_body(body):
    if body.get("mode") != "DDS_MESSAGE": return {k: v for k, v in body.items() if k != "routing"}
    return {k: body[k] for k in ("mode", "message", "address", "incident_type", "ekp_code", "facts", "source_features", "recipients") if k in body}

def action_state(actions):
    status, fields = "ПОЛУЧЕНА СЛУЖБОЙ", {}
    for action in actions:
        if action.action_type == "SELECT_STATUS": status = action.payload["status"]
        if action.action_type == "UPDATE_DDS": fields.update(action.payload["fields"])
    return status, fields
