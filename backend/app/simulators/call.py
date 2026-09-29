from abc import ABC, abstractmethod
import uuid
from datetime import datetime, timezone

class CallProvider(ABC):
    @abstractmethod
    async def start_call(self, metadata: dict) -> dict: ...
    @abstractmethod
    async def answer_call(self, call_id: str) -> dict: ...
    @abstractmethod
    async def end_call(self, call_id: str) -> dict: ...

class MockCallProvider(CallProvider):
    def __init__(self): self.calls = {}
    async def start_call(self, metadata: dict) -> dict:
        call_id = str(uuid.uuid4()); self.calls[call_id] = {"status":"RINGING", "metadata":metadata, "started_at":datetime.now(timezone.utc).isoformat()}; return {"call_id":call_id, "status":"RINGING"}
    async def answer_call(self, call_id: str) -> dict:
        self.calls[call_id]["status"]="ACTIVE"; self.calls[call_id]["answered_at"]=datetime.now(timezone.utc).isoformat(); return self.calls[call_id]
    async def end_call(self, call_id: str) -> dict:
        self.calls.setdefault(call_id,{})
        self.calls[call_id]["status"]="ENDED"; self.calls[call_id]["completed_at"]=datetime.now(timezone.utc).isoformat(); return self.calls[call_id]
