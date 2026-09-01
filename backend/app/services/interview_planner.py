import uuid
import asyncio
from app.models.schemas import (
    ParsedResume, ParsedJD, InterviewPlan, QuestionPlanItem, InterviewStage,
)
from app.services.llm_client import llm_client
from app.core.config import settings


def build_plan(resume: ParsedResume, jd: ParsedJD) -> InterviewPlan:
    """Build a dynamic interview plan:
    Q0: INTRODUCTION (welcome + tell me about yourself)
    Q1-Q2: PROJECT (2 questions from resume)
    Q3-Q(N-1): JD_SKILL (one per skill from JD)
    QN: CLOSING (wrap up / thank you)
    """
    interview_id = str(uuid.uuid4())
    questions: list[QuestionPlanItem] = []

    projects = resume.projects or ["your most recent project"]
    jd_skills = jd.required_skills or ["a core requirement from the job description"]

    # Build dynamic stage skeleton
    skeleton: list[InterviewStage] = []

    # Q0: Introduction
    skeleton.append(InterviewStage.INTRODUCTION)

    # Q1-Q2: Project questions (always 2)
    for i in range(settings.project_questions):
        skeleton.append(InterviewStage.PROJECT)

    # Q3+: JD skill questions (one per skill)
    for _ in jd_skills:
        skeleton.append(InterviewStage.JD_SKILL)

    # Last: Closing
    skeleton.append(InterviewStage.CLOSING)

    # Build seed topics for each stage
    role_title = jd.role_title or "the role"
    for i, stage in enumerate(skeleton):
        seed = None
        if stage == InterviewStage.INTRODUCTION:
            seed = role_title
        elif stage == InterviewStage.PROJECT:
            proj_idx = i - 1  # offset by 1 (Q0 is INTRO)
            seed = projects[proj_idx] if proj_idx < len(projects) else projects[0]
        elif stage == InterviewStage.JD_SKILL:
            skill_idx = i - 1 - settings.project_questions  # offset by intro + projects
            seed = jd_skills[skill_idx] if skill_idx < len(jd_skills) else jd_skills[0]

        questions.append(
            QuestionPlanItem(
                index=i,
                stage=stage,
                seed_topic=seed,
            )
        )

    return InterviewPlan(
        interview_id=interview_id,
        total_questions=len(questions),
        questions=questions,
    )


_STAGE_INSTRUCTIONS = {
    InterviewStage.INTRODUCTION: (
        "Hello! I'm Sanjana, and I'll be taking your {role_title} interview today. "
        "We'll discuss your experience, projects, and technical skills based on your resume "
        "and the job description. So, let's get started. Could you tell me a little about "
        "yourself and your experience so far?"
    ),
    InterviewStage.PROJECT: (
        "Ask a deep, specific question about the architecture, role, or technical decisions "
        "in the project: {seed}. Keep it conversational and focused on their experience."
    ),
    InterviewStage.JD_SKILL: (
        "Ask a probing question testing the candidate's practical knowledge of: {seed}, "
        "which is a key requirement for this role. Focus on real-world application."
    ),
    InterviewStage.CLOSING: (
        "Thank you for your time. It was great speaking with you. "
        "That's all for today. All the best!"
    ),
}


async def generate_question_text(
    item: QuestionPlanItem,
    resume: ParsedResume,
    jd: ParsedJD,
    prior_answer: str | None,
) -> str:
    """Called right before a question is asked, so it can react to the
    candidate's previous answer instead of being fully pre-scripted."""
    role_title = item.seed_topic or "the role"
    instruction = _STAGE_INSTRUCTIONS[item.stage].format(
        seed=role_title, role_title=role_title
    )

    # INTRODUCTION and CLOSING: use the instruction AS-IS, no LLM rewriting
    # These are fixed phrases that should not be modified by the LLM
    if item.stage in (InterviewStage.INTRODUCTION, InterviewStage.CLOSING):
        return instruction

    # Other stages: LLM generates a question based on the instruction
    system = (
        "You are a professional, friendly technical interviewer conducting a "
        f"structured mock interview. Ask exactly ONE very short question: a single "
        f"sentence of at most {settings.question_word_limit} words. Keep it natural "
        "and spoken-language friendly — this will be converted to speech. Do not "
        "include numbering, headers, greeting, or filler."
    )
    prompt = (
        f"Interview instruction for this turn: {instruction}\n\n"
        f"Candidate resume summary skills: {', '.join(resume.skills) or 'n/a'}\n"
        f"Job requirements: {', '.join(jd.required_skills) or 'n/a'}\n"
        f"Candidate's previous answer: {prior_answer or '(this is the first question)'}\n\n"
        "Generate the next interview question now."
    )
    return await llm_client.complete(prompt, system=system)


async def generate_all_question_texts(
    plan: InterviewPlan,
    resume: ParsedResume,
    jd: ParsedJD,
) -> None:
    """Generate the text for all questions in the plan."""
    async def _gen(item: QuestionPlanItem) -> None:
        item.question_text = await generate_question_text(
            item, resume, jd, prior_answer=None
        )

    await asyncio.gather(*(_gen(item) for item in plan.questions))
    for item in plan.questions:
        if not item.question_text or not item.question_text.strip():
            item.question_text = "Could you tell me more about that?"


async def ensure_question_generated(
    item: QuestionPlanItem,
    resume: ParsedResume,
    jd: ParsedJD,
    prior_answer: str | None = None,
) -> None:
    """Ensure a single question has its text generated. Generates if not already present."""
    if item.question_text:
        return
    item.question_text = await generate_question_text(
        item, resume, jd, prior_answer=prior_answer
    )

