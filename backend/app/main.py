from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import upload, interview, voice_ws

app = FastAPI(title="AI Mock Interview System", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(interview.router)
app.include_router(voice_ws.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
