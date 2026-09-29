from abc import ABC, abstractmethod

class RtuAdapter(ABC):
    @abstractmethod
    async def emit_event(self, event_type: str, payload: dict) -> dict: ...

class MockRTUAdapter(RtuAdapter):
    async def emit_event(self, event_type: str, payload: dict) -> dict:
        return {"adapter":"mock", "event_type":event_type, "payload":payload, "accepted":True}
