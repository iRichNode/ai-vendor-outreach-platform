"""Polite web research: fetch a company page and extract readable text.

Used to enrich vendors (RESEARCHED status) before outreach. Always adds a
Cache-Control-style politeness delay and a configurable User-Agent.
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger("app.services.research")

_TEXT_TAGS = re.compile(r"^(p|h1|h2|h3|h4|h5|li|span|a|td|th|blockquote)$", re.I)
_WHITESPACE = re.compile(r"\s+")


async def fetch_company_summary(url: str, *, use_https: bool = True) -> dict[str, str]:
    """Fetch and summarize a company URL. Returns {url, title, summary}.
    Never follows internal site navigation and stays polite (single request).
    """
    settings = get_settings()
    target = url if url.startswith(("http://", "https://")) else f"{'https' if use_https else 'http'}://{url}"
    parsed = urlparse(target)
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    headers = {
        "User-Agent": settings.RESEARCH_USER_AGENT or "AI-Vendor-Research/1.0 (+https://example.com/bot)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.RESEARCH_TIMEOUT_SECONDS, headers=headers, follow_redirects=True
        ) as client:
            resp = await client.get(target)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("research_fetch_error url=%s detail=%s", target, str(exc))
        return {"url": target, "title": "", "summary": f"Could not fetch page: {exc}"}
    finally:
        await asyncio.sleep(settings.RESEARCH_POLITENESS_SECONDS)

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "aside"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    lines: list[str] = []
    for tag in soup.find_all(_TEXT_TAGS):
        text = _WHITESPACE.sub(" ", tag.get_text(" ", strip=True))
        if text and text not in lines:
            lines.append(text)
    # Prefer the first N non-title paragraphs for a compact summary.
    body = lines[:8] if lines else []
    summary = (" ".join(body))[:1000] or "No readable content extracted."
    logger.info("research_ok url=%s title_chars=%d summary_chars=%d", target, len(title), len(summary))
    return {"url": target, "title": title, "summary": summary}