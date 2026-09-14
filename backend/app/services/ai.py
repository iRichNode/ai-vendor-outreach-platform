"""AI service abstraction (OpenRouter / any OpenAI-compatible endpoint).

The LLM produces a *decision* (structured JSON). The backend validates every field
and decides whether the action is allowed. The LLM never executes anything directly.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings
from app.services.optout import detect_opt_out

logger = logging.getLogger("app.services.ai")


class AIServiceError(Exception):
    pass


@dataclass
class AIDecision:
    intent: str = "other"
    qualification_status: str = "UNQUALIFIED"
    needs_human: bool = False
    needs_meeting: bool = False
    response: str | None = None
    reason: str = ""
    raw: dict = field(default_factory=dict)

    def model_dump(self) -> dict:
        return {
            "intent": self.intent,
            "qualification_status": self.qualification_status,
            "needs_human": self.needs_human,
            "needs_meeting": self.needs_meeting,
            "response": self.response,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Backend guardrails (authoritative, not advisory)
# ---------------------------------------------------------------------------

# The AI must never invent these. If a candidate reply contains a *confirming*
# assertion about them, the sentence is removed and the reply flagged for review.
_FORBIDDEN_TOPIC_PATTERNS = [
    re.compile(r"\b(prices?|pricing|quote)\b.{0,80}\b(\$|per |cost|fees?)", re.I),
    re.compile(r"\b(payment terms?|payment plan)\b", re.I),
    re.compile(r"\b(contract|agreement)(s?)\b", re.I),
    re.compile(r"\bguarantee(d)?\b|\bwarrant(y|ies)\b", re.I),
    re.compile(r"\b(discount|deal|offer) of?\b.{0,40}\d+%?", re.I),
    re.compile(r"\btimeline of\b.{0,60}\d+\s+(day|week|month)s?", re.I),
    re.compile(r"\bsavings? of\b|\bROI of\b", re.I),
]

_SENSITIVE_FINANCIAL = re.compile(
    r"\b(credit card|bank account|routing number|social security|tax id|ein number|"
    r"passport number|payment details)\b",
    re.I,
)


def guardrail_check(text: str | None) -> tuple[str | None, bool]:
    """Strip sentences that assert forbidden claims.

    Returns (safe_text, flagged). When flagged, the reply is shortened and the
    conversation should be reviewed by a human before sending.
    """
    if not text:
        return text, False
    flagged = False
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        if any(p.search(sentence) for p in _FORBIDDEN_TOPIC_PATTERNS) or _SENSITIVE_FINANCIAL.search(sentence):
            flagged = True
            continue
        kept.append(sentence)
    cleaned = " ".join(kept).strip()
    if not cleaned:
        cleaned = "I'd need to confirm some details with our team before I can answer that precisely."
    return cleaned, flagged


ALLOWED_INTENTS = {"interested", "not_interested", "opt_out", "ask_question",
                   "request_human", "request_meeting", "needs_more_info", "other"}
ALLOWED_QUALIFICATIONS = {"UNQUALIFIED", "QUALIFYING", "QUALIFIED", "NOT_QUALIFIED"}


class LLMClient:
    """OpenAI-compatible chat completions client (OpenRouter by default)."""

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key = self.settings.OPENROUTER_API_KEY
        self.base_url = self.settings.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1"
        self.model = self.settings.LLM_MODEL
        self.temperature = self.settings.LLM_TEMPERATURE
        self.max_tokens = self.settings.LLM_MAX_TOKENS

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def complete(self, system: str, user: str) -> str:
        if not self.enabled:
            raise AIServiceError("LLM provider is not configured (no API key)")
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            if resp.status_code >= 400:
                raise AIServiceError(f"LLM provider error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:  # noqa: PERF203
            raise AIServiceError(f"Unexpected LLM response shape: {str(data)[:300]}") from exc

    def parse_decision(self, content: str) -> AIDecision:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # tolerate markdown fences
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                raise AIServiceError("LLM returned no JSON")
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise AIServiceError(f"LLM returned invalid JSON: {content[:200]}") from exc
        if not isinstance(data, dict):
            raise AIServiceError("LLM JSON is not an object")
        intent = str(data.get("intent", "other")).lower()
        if intent not in ALLOWED_INTENTS:
            intent = "other"
        qualification = str(data.get("qualification_status", "UNQUALIFIED")).upper()
        if qualification not in ALLOWED_QUALIFICATIONS:
            qualification = "UNQUALIFIED"
        response = data.get("response")
        if response is not None and not isinstance(response, str):
            response = str(response)
        return AIDecision(
            intent=intent,
            qualification_status=qualification,
            needs_human=bool(data.get("needs_human")),
            needs_meeting=bool(data.get("needs_meeting")),
            response=response,
            reason=str(data.get("reason", ""))[:1000],
            raw=data,
        )

    async def decide(self, system: str, user: str) -> AIDecision:
        """Call the LLM, parse+validate the decision, retry once on malformed output."""
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                content = await self.complete(system, user)
                return self.parse_decision(content)
            except AIServiceError as exc:
                last_error = exc
                if attempt == 0:
                    user = f"{user}\n\nYour previous output could not be parsed. Respond ONLY with valid JSON."
                continue
        raise AIServiceError(f"AI decision failed: {last_error}")


class RuleBasedLLM:
    """Deterministic fallback used for demo mode and when no API key is configured.

    Makes the pipeline fully testable without external calls and clearly flags
    that it is demo-grade.
    """

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return True

    name = "rule-based (demo)"

    def decide(self, system: str, user: str) -> AIDecision:  # noqa: ARG002
        text = user
        subject = _extract_subject(text)
        body = _extract_body(text)
        if detect_opt_out(subject, body):
            return AIDecision(
                intent="opt_out",
                qualification_status="NOT_QUALIFIED",
                needs_human=False,
                needs_meeting=False,
                response=None,
                reason="Opt-out language detected by backend rules.",
            )
        lowered = f"{subject} {body}".lower()
        if any(w in lowered for w in ("meeting", "call", "schedule", "free next week", "very interested", "definitely interested")):
            return AIDecision(
                intent="interested",
                qualification_status="QUALIFYING",
                needs_human=True,
                needs_meeting=True,
                response=("Great to hear you're interested! I'll set up a call with our team "
                          "— someone will send you a meeting link shortly."),
                reason="Rule-based demo: interest keywords detected + meeting requested.",
            )
        if any(w in lowered for w in ("not interested", "no thanks", "no thank you", "pass", "don't need", "stop contacting")):
            return AIDecision(
                intent="not_interested",
                qualification_status="NOT_QUALIFIED",
                needs_human=False,
                needs_meeting=False,
                response="No problem — thanks for letting us know! We'll leave you alone.",
                reason="Rule-based demo: not-interested keywords detected.",
            )
        if "human" in lowered or "representative" in lowered or "actual person" in lowered:
            return AIDecision(
                intent="request_human",
                qualification_status="UNQUALIFIED",
                needs_human=True,
                needs_meeting=False,
                response="Of course — I've asked our team to reach out to you directly.",
                reason="Rule-based demo: human requested.",
            )
        return AIDecision(
            intent="ask_question",
            qualification_status="UNQUALIFIED",
            needs_human=False,
            needs_meeting=False,
            response=("Thanks for your message! Could you tell me a bit more about your needs "
                      "so I can point you to the right information?"),
            reason="Rule-based demo: generic reply.",
        )


def _extract_subject(blob: str) -> str | None:
    match = re.search(r"^Subject:\s*(.+)$", blob, re.M | re.I)
    return match.group(1).strip() if match else None


def _extract_body(blob: str) -> str:
    match = re.search(r"^Body:\s*(.+)$", blob, re.S | re.I)
    return match.group(1).strip() if match else blob


def build_llm(
    system_prompt: str | None = None, settings: Any | None = None
) -> LLMClient | RuleBasedLLM:
    """Pick the real client when a key exists, otherwise the demo rule engine.

    ``settings`` may be a runtime copy with the panel-stored API key merged in.
    """
    settings = settings or get_settings()
    if settings.OPENROUTER_API_KEY:
        return LLMClient(settings=settings)
    return RuleBasedLLM(settings=settings)