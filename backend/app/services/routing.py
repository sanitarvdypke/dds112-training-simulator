"""Conservative evaluation: missing facts and ambiguous headers are never guessed."""
def matches(condition, facts):
    if condition.get("review_required"): return None
    kind = condition.get("kind")
    if kind == "always": return True
    if kind == "flag":
        value = facts.get(condition["feature"])
        return None if value is None else value == condition["value"]
    if kind == "all_false":
        values = [facts.get(f) for f in condition.get("features", [])]
        if True in values: return False
        return None if not values or None in values else True
    return None

def route(entry, facts):
    recipients, pending, evidence = {}, [], []
    for rule in entry.get("rules", []):
        match = matches(rule.get("condition", {}), facts)
        evidence.append({**rule, "match": match})
        if match is None: pending.append(rule["source_cell"])
        elif match and rule.get("effect") != "NO_RESPONSE":
            recipients[rule["service_key"]] = rule["service_name"]
    return {"recipients": [{"key": k, "name": v} for k, v in recipients.items()],
            "pending_cells": pending, "evidence": evidence,
            "review_required": bool(pending or entry.get("review_required"))}
