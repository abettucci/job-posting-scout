from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from anthropic import Anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

_VALID_STAGES = {"applied", "phone", "technical", "onsite", "offer", "accepted", "rejected", "withdrawn"}

_FOLLOWUP_SYSTEM = """You draft a short, professional follow-up message for a job application that has gone quiet.
You receive the tracked application's company, role, current stage, scheduled date (if any), and free-text notes.

STRICT RULES:
- Only reference facts given to you (company, role, stage, notes, scheduled date). Never invent details about
  what was discussed, who the contact is, or outcomes that aren't in the notes.
- This is a DRAFT ONLY — it will never be sent automatically. Write it as if the candidate will review and send it.
- Keep it short (under 120 words), warm but professional, no generic filler.

Return ONLY valid JSON, no markdown fences:
{"subject": "...", "body": "..."}
"""

def _draft_followup_with_claude(client: Anthropic, interview: dict) -> dict:
    context = (
        f"Company: {interview.get('company', '')}\n"
        f"Role: {interview.get('role', '')}\n"
        f"Current stage: {interview.get('stage', '')}\n"
        f"Scheduled at: {interview.get('scheduled_at') or 'not scheduled'}\n"
        f"Notes: {interview.get('notes') or 'none'}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_FOLLOWUP_SYSTEM,
        messages=[{"role": "user", "content": context}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"subject": f"Following up — {interview.get('role', '')} at {interview.get('company', '')}",
                "body": "Could not draft a message automatically — try again."}


class InterviewCreate(BaseModel):
    company: str
    role: str
    stage: str = "applied"
    scheduled_at: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = ""
    job_id: Optional[str] = None
    job_score: Optional[int] = None
    job_url: Optional[str] = None

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: str) -> str:
        if v not in _VALID_STAGES:
            raise ValueError(f"stage must be one of: {', '.join(sorted(_VALID_STAGES))}")
        return v


class InterviewPatch(BaseModel):
    stage: Optional[str] = None
    scheduled_at: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_STAGES:
            raise ValueError(f"stage must be one of: {', '.join(sorted(_VALID_STAGES))}")
        return v


def make_router(db: Any, cfg: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/interviews", tags=["interviews"])
    _anthropic = Anthropic(api_key=cfg.anthropic_api_key)

    @router.get("")
    def list_interviews(user=Depends(get_current_user)):
        return db.get_user_interviews(user["user_id"])

    @router.post("")
    def create_interview(body: InterviewCreate, user=Depends(get_current_user)):
        now = datetime.utcnow().isoformat()
        interview = {
            "user_id": user["user_id"],
            "interview_id": str(uuid.uuid4()),
            "company": body.company.strip(),
            "role": body.role.strip(),
            "stage": body.stage,
            "scheduled_at": body.scheduled_at,
            "location": body.location,
            "notes": body.notes or "",
            "job_id": body.job_id,
            "job_score": body.job_score,
            "job_url": body.job_url,
            "created_at": now,
            "updated_at": now,
        }
        if not db.create_interview(interview):
            raise HTTPException(500, "Error creating interview")
        return interview

    @router.patch("/{interview_id}")
    def patch_interview(interview_id: str, body: InterviewPatch, user=Depends(get_current_user)):
        updates = body.model_dump(exclude_none=True)
        updates["updated_at"] = datetime.utcnow().isoformat()
        if not db.update_interview(user["user_id"], interview_id, updates):
            raise HTTPException(500, "Error updating interview")
        return {"interview_id": interview_id, **updates}

    @router.delete("/{interview_id}")
    def delete_interview(interview_id: str, user=Depends(get_current_user)):
        if not db.delete_interview(user["user_id"], interview_id):
            raise HTTPException(500, "Error deleting interview")
        return {"deleted": interview_id}

    @router.post("/{interview_id}/followup")
    def draft_followup(interview_id: str, user=Depends(get_current_user)):
        interview = db.get_interview(user["user_id"], interview_id)
        if not interview:
            raise HTTPException(404, "Interview not found")
        return _draft_followup_with_claude(_anthropic, interview)

    return router
