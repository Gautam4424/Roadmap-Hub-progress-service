from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import progress
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Progress Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(progress.router, prefix="/api/v1/progress")

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": settings.SERVICE_NAME}
