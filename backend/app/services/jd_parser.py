from pathlib import Path
import re
import pdfplumber
from app.models.schemas import ParsedJD
from app.services.skill_extractor import extract_skills


def _extract_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        text = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)
    elif ext == ".txt":
        return Path(path).read_text(errors="ignore")
    else:
        raise ValueError(f"Unsupported JD file type: {ext}")


def _extract_role_title(raw_text: str) -> str:
    """Extract job role/title from JD text by looking for common patterns."""
    lines = raw_text.strip().split("\n")

    # Pattern 1: Look for explicit role/title/position lines
    role_patterns = [
        r"(?:role|position|title|job\s*title|designation)\s*[:=]?\s*(.+)",
        r"(?:hiring\s+for|we(?:'re| are)\s+looking\s+for)\s+(.+?)(?:\s+to|\s+who|\s+with|$)",
    ]
    for line in lines[:15]:  # Check first 15 lines
        for pattern in role_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return match.group(1).strip().rstrip(".,")

    # Pattern 2: First non-empty, short line (often the job title)
    for line in lines[:5]:
        line = line.strip()
        if line and len(line) < 80 and not line.startswith(("#", "*", "-", "•")):
            # Skip lines that look like headers/metadata
            if not re.match(r"^(company|location|salary|experience|date|posted|about|description)", line, re.IGNORECASE):
                return line

    return ""


def parse_jd(path: str) -> ParsedJD:
    raw_text = _extract_text(path)
    skills = extract_skills(raw_text)
    role_title = _extract_role_title(raw_text)
    # naive split: first N skills = required, rest = nice-to-have.
    required = skills[: max(1, len(skills) // 2)] or skills
    nice = skills[len(required):]
    return ParsedJD(
        raw_text=raw_text,
        required_skills=required,
        nice_to_have_skills=nice,
        role_title=role_title,
    )
