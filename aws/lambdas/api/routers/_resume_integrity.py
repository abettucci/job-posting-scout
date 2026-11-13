"""Pure validation helpers that keep AI resume rewrites from losing content."""
from __future__ import annotations

import json
import re
from typing import Any, List, Mapping, Optional


_IDENTITY_FIELDS = ("name", "email", "phone", "location", "linkedin", "github", "website")
_LIST_SECTIONS = ("experience", "education", "projects", "certifications")

# Technology names eligible for the optional hidden ATS keyword line.
_TECH_TERMS = (
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "Rust", "C#", "C++", "Ruby", "PHP", "Scala",
    "Kotlin", "Swift", "SQL", "Bash", "Node.js", "React", "Next.js", "Angular", "Vue", "Svelte", "Django", "Flask",
    "FastAPI", "Spring", "Express", "NestJS", ".NET", "Terraform", "Ansible", "Docker", "Kubernetes", "Helm",
    "AWS", "Azure", "GCP", "Lambda", "EC2", "S3", "DynamoDB", "CloudFormation", "CDK", "API Gateway",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka", "RabbitMQ", "Elasticsearch", "Snowflake", "Spark",
    "Airflow", "dbt", "GraphQL", "REST", "gRPC", "Microservices", "CI/CD", "GitHub Actions", "Jenkins", "GitLab",
    "Linux", "Git", "Prometheus", "Grafana", "Datadog", "OpenTelemetry", "Celery", "Pandas", "PyTorch",
    "TensorFlow", "LangChain", "OpenAI", "Machine Learning", "Terragrunt", "Serverless", "Agile", "Scrum",
)
_MAX_HIDDEN_KEYWORDS = 25


def _term_pattern(term: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#])", re.IGNORECASE)


def select_hidden_keywords(original: Mapping[str, Any], tailored: Mapping[str, Any], job_description: str) -> List[str]:
    """Technologies named in the posting that the original resume supports but the visible CV omits.

    Only terms already present in the candidate's original resume are eligible, so the hidden line never
    adds a skill the candidate did not list.
    """
    original_text = json.dumps(original, ensure_ascii=False)
    visible_text = json.dumps({k: v for k, v in tailored.items() if k != "hidden_keywords"}, ensure_ascii=False)
    selected: List[str] = []
    for term in _TECH_TERMS:
        if len(selected) >= _MAX_HIDDEN_KEYWORDS:
            break
        pattern = _term_pattern(term)
        if pattern.search(job_description) and pattern.search(original_text) and not pattern.search(visible_text):
            selected.append(term)
    return selected


def _has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return bool(value)


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and any(_has_content(item) for item in value)


def resume_has_renderable_content(resume: Mapping[str, Any]) -> bool:
    """Return whether a resume contains actual professional content, not just a name."""
    if str(resume.get("summary") or "").strip():
        return True
    if any(_non_empty_list(resume.get(section)) for section in _LIST_SECTIONS):
        return True
    skills = resume.get("skills")
    return isinstance(skills, Mapping) and any(_non_empty_list(items) for items in skills.values())


def incomplete_tailored_payload_reason(original: Mapping[str, Any], candidate: Any) -> Optional[str]:
    """Explain why an AI output cannot safely replace ``original``.

    Pydantic gives ResumeData fields defaults, so validating a model *after*
    parsing silently accepts a response such as ``{"name": "…"}``.  Validate
    the raw JSON first, while missing fields are still observable.
    """
    if not isinstance(candidate, Mapping):
        return "The AI response was not a resume object."

    for field in _IDENTITY_FIELDS:
        original_value = str(original.get(field) or "")
        if original_value and candidate.get(field) != original_value:
            return f"The AI response changed or omitted {field}."

    if str(original.get("summary") or "").strip() and not str(candidate.get("summary") or "").strip():
        return "The AI response omitted the professional summary."

    for section in _LIST_SECTIONS:
        if _non_empty_list(original.get(section)) and not _non_empty_list(candidate.get(section)):
            return f"The AI response omitted the {section} section."

    original_skills = original.get("skills")
    candidate_skills = candidate.get("skills")
    if isinstance(original_skills, Mapping) and any(_non_empty_list(items) for items in original_skills.values()):
        if not isinstance(candidate_skills, Mapping) or not any(_non_empty_list(items) for items in candidate_skills.values()):
            return "The AI response omitted the skills section."

    if not resume_has_renderable_content(candidate):
        return "The AI response did not contain professional resume content."
    return None
