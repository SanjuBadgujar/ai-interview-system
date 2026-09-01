from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class InterviewStage(str, Enum):
    INTRODUCTION = "introduction"
    PROJECT = "project"
    RESUME_SKILL = "resume_skill"
    JD_SKILL = "jd_skill"
    TECHNICAL = "technical"
    SCENARIO = "scenario"
    PROJECT_JD_LINK = "project_jd_link"
    CODING = "coding"
    BEHAVIORAL = "behavioral"
    CLOSING = "closing"


class ParsedResume(BaseModel):
    raw_text: str
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    experience_years: Optional[float] = None
    summary: Optional[str] = None


class ParsedJD(BaseModel):
    raw_text: str
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    role_title: Optional[str] = None


class QuestionPlanItem(BaseModel):
    index: int
    stage: InterviewStage
    seed_topic: Optional[str] = None  # skill/project this question should target
    question_text: Optional[str] = None  # filled in lazily by the LLM


class InterviewPlan(BaseModel):
    interview_id: str
    total_questions: int
    questions: list[QuestionPlanItem]


class StartInterviewRequest(BaseModel):
    resume_id: str
    jd_id: str


class StartInterviewResponse(BaseModel):
    interview_id: str
    first_question: str
    question_number: int
    total_questions: int
    jd_skills: list[str] = Field(default_factory=list)


class SubmitAnswerRequest(BaseModel):
    interview_id: str
    answer_text: str


class NextQuestionResponse(BaseModel):
    interview_id: str
    question_text: Optional[str]
    question_number: int
    total_questions: int
    is_complete: bool
    feedback_on_previous: Optional[str] = None


class UploadResponse(BaseModel):
    file_id: str
    filename: str
