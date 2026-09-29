from app.simulators.call import MockCallProvider
from app.simulators.rtu import MockRTUAdapter
from app.core.config import settings

call_provider = MockCallProvider() if settings.call_provider == "mock" else MockCallProvider()
rtu_adapter = MockRTUAdapter() if settings.rtu_provider == "mock" else MockRTUAdapter()
