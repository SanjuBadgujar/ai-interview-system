import uuid
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException

from app.core.config import settings
from app.models.schemas import UploadResponse
from app.models.state import store
from app.services.resume_parser import parse_resume
from app.services.jd_parser import parse_jd
from app.services.tts_service import warmup_tts

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/resume", response_model=UploadResponse)
async def upload_resume(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if Path(file.filename).suffix.lower() not in (".pdf", ".docx", ".doc", ".txt"):
        raise HTTPException(400, "Unsupported resume file type")

    file_id = str(uuid.uuid4())
    dest = Path(settings.upload_dir) / f"{file_id}_{file.filename}"
    dest.write_bytes(await file.read())

    parsed = parse_resume(str(dest))
    store.save_resume(file_id, parsed)
    background_tasks.add_task(warmup_tts)

    return UploadResponse(file_id=file_id, filename=file.filename)


@router.post("/jd", response_model=UploadResponse)
async def upload_jd(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if Path(file.filename).suffix.lower() not in (".pdf", ".txt"):
        raise HTTPException(400, "Unsupported JD file type")

    file_id = str(uuid.uuid4())
    dest = Path(settings.upload_dir) / f"{file_id}_{file.filename}"
    dest.write_bytes(await file.read())

    parsed = parse_jd(str(dest))
    store.save_jd(file_id, parsed)
    background_tasks.add_task(warmup_tts)

    return UploadResponse(file_id=file_id, filename=file.filename)
