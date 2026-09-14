"""Backend-enforced opt-out detection.

Opt-out must be enforced by backend rules, not merely by AI instructions. This module
implements deterministic content rules; the AI pipeline also flags opt-outs, but the
final authority is this function.
"""
from __future__ import annotations

import re

# Phrases that clearly indicate the recipient does not want further contact.
_OPT_OUT_PATTERNS = [
    re.compile(r"\bunsubscribe\b", re.I),
    re.compile(r"\bremove me\b", re.I),
    re.compile(r"\bdo not contact me\b", re.I),
    re.compile(r"\bno more (emails?|messages|contact)\b", re.I),
    re.compile(r"\bplease (stop|don'?t (email|write|contact))\b", re.I),
    re.compile(r"\bopt[\s-]?out\b", re.I),
    re.compile(r"\bstop (contacting|emailing|sending)\b", re.I),
    re.compile(r"\btake me off\b", re.I),
]

# Anti-false-positive: phrases that contain the word "stop"/"unsubscribe" but do not
# mean the recipient is opting out.
_OPT_OUT_EXCEPTIONS = [
    re.compile(r"\bdo not stop\b", re.I),
    re.compile(r"\bstop (by|in|at)\b", re.I),
    re.compile(r"\bunsubscribe rate\b", re.I),
    re.compile(r"\bhow (to|do i|can i) unsubscribe\b", re.I),
]


def _subject_is_headers_only(subject: str | None, body: str) -> bool:
    """Gmail auto-replies put the subject in the body: 'Unsubscribe: ...'."""
    return bool(subject and subject.lower() in {"unsubscribe", "stop"} and body.count("\n") < 2)


def detect_opt_out(subject: str | None, body: str) -> bool:
    """Return True when the message clearly asks to stop future contact."""
    text = f"{subject or ''}\n{body}"
    if _subject_is_headers_only(subject, body):
        return True
    if any(p.search(subject or "") for p in _OPT_OUT_PATTERNS if not any(e.search(subject or "") for e in _OPT_OUT_EXCEPTIONS)):
        return True
    found = [p.search(text) for p in _OPT_OUT_PATTERNS]
    if not any(found):
        return False
    # A pattern matched; confirm it is not negated/coincidental.
    if any(e.search(text) for e in _OPT_OUT_EXCEPTIONS):
        return False
    return True