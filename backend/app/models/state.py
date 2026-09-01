"""
MVP state store. Swap this for a Postgres-backed repository once the
project outgrows a single-process demo — the interface (get/save/list)
is what matters, so callers don't need to change.
"""
from typing import Optional
from app.models.schemas import ParsedResume, ParsedJD, InterviewPlan


class InterviewSession:
    def __init__(self, interview_id: str, resume: ParsedResume, jd: ParsedJD, plan: InterviewPlan):
        self.interview_id = interview_id
        self.resume = resume
        self.jd = jd
        self.plan = plan
        self.current_index = 0
        self.transcript: list[dict] = []  # [{"role": "ai"|"candidate", "text": str}]
        # /interview/start generates + returns question #1 as text over REST,
        # before any WebSocket exists to stream audio for it. This flag lets
        # the voice WS speak that first question once, the moment it connects,
        # instead of leaving it silent forever.
        self.first_question_voiced = False

    def current_question_item(self):
        if self.current_index >= len(self.plan.questions):
            return None
        return self.plan.questions[self.current_index]

    def record(self, role: str, text: str):
        self.transcript.append({"role": role, "text": text})

    def advance(self):
        self.current_index += 1

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.plan.questions)


class SessionStore:
    """Process-local store. Replace with Redis/Postgres for multi-worker deploys."""

    def __init__(self):
        self._sessions: dict[str, InterviewSession] = {}
        self._resumes: dict[str, ParsedResume] = {}
        self._jds: dict[str, ParsedJD] = {}

    # resumes / JDs
    def save_resume(self, file_id: str, resume: ParsedResume):
        self._resumes[file_id] = resume

    def get_resume(self, file_id: str) -> Optional[ParsedResume]:
        return self._resumes.get(file_id)

    def save_jd(self, file_id: str, jd: ParsedJD):
        self._jds[file_id] = jd

    def get_jd(self, file_id: str) -> Optional[ParsedJD]:
        return self._jds.get(file_id)

    # interviews
    def create_session(self, session: InterviewSession):
        self._sessions[session.interview_id] = session

    def get_session(self, interview_id: str) -> Optional[InterviewSession]:
        return self._sessions.get(interview_id)


store = SessionStore()
