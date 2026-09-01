import re

# Small seed keyword list for the rule-based fallback. In production, prefer
# extract_skills_llm() below, which asks Mistral to pull skills out of
# arbitrary resume/JD text far more robustly than keyword matching.
_SKILL_KEYWORDS = [
    "python", "java", "javascript", "typescript", "react", "node", "fastapi",
    "django", "flask", "postgresql", "mysql", "mongodb", "redis", "docker",
    "kubernetes", "aws", "gcp", "azure", "pytorch", "tensorflow", "sql",
    "git", "ci/cd", "microservices", "graphql", "rest", "websocket",
    "machine learning", "deep learning", "nlp", "computer vision",
    "data engineering", "spark", "airflow", "kafka", "linux", "bash",
]


def extract_skills(text: str) -> list[str]:
    """Cheap, dependency-free keyword match. Swap for extract_skills_llm
    once you've wired up the Mistral client — this is only here so the
    app runs before any API keys are configured."""
    text_lower = text.lower()
    found = []
    for kw in _SKILL_KEYWORDS:
        if kw in text_lower and kw not in found:
            found.append(kw)
    return found


def extract_projects(text: str) -> list[str]:
    """Very naive heuristic: pull lines under a 'Projects' heading.
    Replace with extract_projects_llm for real accuracy."""
    lines = text.splitlines()
    projects = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^(projects?|personal projects?)\s*:?$", stripped, re.I):
            capture = True
            continue
        if capture:
            if re.match(r"^[A-Z][a-zA-Z ]{2,30}:?$", stripped) and stripped.lower() not in (
                "projects", "project"
            ) and len(projects) > 0:
                # hit a new section heading, stop capturing
                if stripped.lower() in ("skills", "education", "experience", "certifications"):
                    break
            if stripped:
                projects.append(stripped)
    return projects[:10]


async def extract_skills_llm(text: str, llm_client) -> list[str]:
    """LLM-backed extraction — more robust than the keyword list above.
    Pass in an instance of app.services.llm_client.LLMClient."""
    prompt = (
        "Extract a flat JSON array of technical skills, tools, and "
        "technologies mentioned in the text below. Return ONLY the JSON "
        f"array, nothing else.\n\nTEXT:\n{text[:6000]}"
    )
    raw = await llm_client.complete(prompt)
    import json
    try:
        return json.loads(raw)
    except Exception:
        return extract_skills(text)


async def extract_projects_llm(text: str, llm_client) -> list[str]:
    prompt = (
        "Extract a flat JSON array of distinct project names/titles the "
        "candidate worked on, based on the resume text below. Return ONLY "
        f"the JSON array.\n\nTEXT:\n{text[:6000]}"
    )
    raw = await llm_client.complete(prompt)
    import json
    try:
        return json.loads(raw)
    except Exception:
        return extract_projects(text)
