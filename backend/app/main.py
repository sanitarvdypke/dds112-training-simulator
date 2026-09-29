from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import admin, auth, scenarios, sessions, reports, imports, dds, groups, inbox

app=FastAPI(title="DDS-112 Training Simulator",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",")],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(auth.router,prefix="/api")
app.include_router(scenarios.router,prefix="/api")
app.include_router(sessions.router,prefix="/api")
app.include_router(inbox.router,prefix="/api")
app.include_router(reports.router,prefix="/api")
app.include_router(imports.router,prefix="/api")
app.include_router(dds.router,prefix="/api")
app.include_router(groups.router,prefix="/api")
app.include_router(admin.router,prefix="/api")

@app.get("/health")
async def health(): return {"status":"ok","mode":"LOCAL_TRAINING_ONLY","real_calls":False}
