import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.models.schemas import (
    StartInterviewRequest, StartInterviewResponse,
    SubmitAnswerRequest, NextQuestionResponse,
)
from app.models.state import store, InterviewSession
from app.services.interview_planner import (
    build_plan, generate_question_text, ensure_question_generated,
)
from app.services.jd_parser import parse_jd
from app.services.resume_parser import parse_resume
from app.services.tts_service import warmup_tts

router = APIRouter(prefix="/interview", tags=["interview"])


def _uploaded_file(file_id: str) -> Path | None:
    """Return the file for an upload ID, if it is still on disk.

    Upload metadata normally lives in the process-local store. In development,
    however, Uvicorn reloads (and multi-worker deployments) create a fresh
    store while the uploaded files remain. Validate the UUID before matching a
    filename so a request cannot use this lookup to traverse the filesystem.
    """
    try:
        normalized_id = str(uuid.UUID(file_id))
    except ValueError:
        return None

    upload_dir = Path(settings.upload_dir)
    return next(upload_dir.glob(f"{normalized_id}_*"), None)


def _restore_uploads(resume_id: str, jd_id: str):
    """Restore upload parsing after an app reload, when possible."""
    resume = store.get_resume(resume_id)
    if not resume:
        resume_path = _uploaded_file(resume_id)
        if resume_path:
            resume = parse_resume(str(resume_path))
            store.save_resume(resume_id, resume)

    jd = store.get_jd(jd_id)
    if not jd:
        jd_path = _uploaded_file(jd_id)
        if jd_path:
            jd = parse_jd(str(jd_path))
            store.save_jd(jd_id, jd)

    return resume, jd


@router.post("/start", response_model=StartInterviewResponse)
async def start_interview(req: StartInterviewRequest):
    resume, jd = _restore_uploads(req.resume_id, req.jd_id)
    if not resume or not jd:
        raise HTTPException(404, "resume_id or jd_id not found — upload them first")

    # Upload starts the warm-up in the background. Await it here only if it is
    # still running, so TTS is ready before the frontend opens the voice socket.
    await warmup_tts()

    plan = build_plan(resume, jd)
    session = InterviewSession(plan.interview_id, resume, jd, plan)
    store.create_session(session)

    # INTRODUCTION is a fixed phrase (no LLM call) — return instantly
    first_item = session.current_question_item()
    await ensure_question_generated(first_item, resume, jd)

    return StartInterviewResponse(
        interview_id=session.interview_id,
        first_question=first_item.question_text,
        question_number=1,
        total_questions=len(plan.questions),
        jd_skills=jd.required_skills or [],
    )


@router.post("/answer", response_model=NextQuestionResponse)
async def submit_answer(req: SubmitAnswerRequest):
    session = store.get_session(req.interview_id)
    if not session:
        raise HTTPException(404, "interview_id not found")

    session.record("candidate", req.answer_text)
    session.advance()

    if session.is_complete:
        return NextQuestionResponse(
            interview_id=session.interview_id,
            question_text=None,
            question_number=len(session.plan.questions),
            total_questions=len(session.plan.questions),
            is_complete=True,
        )

    item = session.current_question_item()
    question_text = await generate_question_text(
        item, session.resume, session.jd, prior_answer=req.answer_text
    )
    item.question_text = question_text
    session.record("ai", question_text)

    return NextQuestionResponse(
        interview_id=session.interview_id,
        question_text=question_text,
        question_number=session.current_index + 1,
        total_questions=len(session.plan.questions),
        is_complete=False,
    )


@router.get("/{interview_id}/transcript")
async def get_transcript(interview_id: str):
    session = store.get_session(interview_id)
    if not session:
        raise HTTPException(404, "interview_id not found")
    return {"interview_id": interview_id, "transcript": session.transcript}
