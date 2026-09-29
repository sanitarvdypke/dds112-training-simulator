import re
from app.ai.base import AIProvider

class MockAIProvider(AIProvider):
    async def generate_scenario(self, context: dict) -> dict:
        category = context.get("category", "Прочие происшествия")
        return {
            "title": f"Учебный сценарий: {category}",
            "category": category,
            "participant_role": "Заявитель",
            "incident_payload": {"message":"Учебный входящий вызов", "tags": ["место", "что произошло", "есть ли пострадавшие"]},
            "expected_state": {"statuses":["ПРИНЯТО"], "services":[]},
            "requires_teacher_approval": True,
        }
    async def analyze_text(self, text: str, expected: str | None = None) -> dict:
        words = re.findall(r"[А-Яа-яA-Za-zЁё0-9-]+", text or "")
        issues = []
        if not text.strip(): issues.append("Пустой комментарий")
        if text and text.strip()[-1:] not in ".!?": issues.append("Рекомендуется завершить фразу знаком препинания")
        if len(words) < 3: issues.append("Слишком короткая формулировка для учебной обратной связи")
        return {"provider":"mock", "grammar_issues":issues, "semantic_similarity": None, "note":"AI-обратная связь не влияет на детерминированный балл"}
