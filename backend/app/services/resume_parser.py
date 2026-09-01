import pdfplumber
import docx
from pathlib import Path
from app.models.schemas import ParsedResume
from app.services.skill_extractor import extract_skills, extract_projects


def _extract_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        text = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)
    elif ext in (".docx", ".doc"):
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs)
    elif ext == ".txt":
        return Path(path).read_text(errors="ignore")
    else:
        raise ValueError(f"Unsupported resume file type: {ext}")


def parse_resume(path: str) -> ParsedResume:
    raw_text = _extract_text(path)
    skills = extract_skills(raw_text)
    projects = extract_projects(raw_text)
    return ParsedResume(
        raw_text=raw_text,
        skills=skills,
        projects=projects,
    )
