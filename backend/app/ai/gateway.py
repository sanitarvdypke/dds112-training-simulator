from app.ai.mock import MockAIProvider
from app.core.config import settings

def get_ai_provider():
    if not settings.ai_enabled or settings.ai_provider == "mock": return MockAIProvider()
    # Точка расширения для локальной модели/разрешённого провайдера. Внешний сетевой вызов здесь не выполняется.
    return MockAIProvider()
