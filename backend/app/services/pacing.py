"""Email pacing, sending windows and daily-limit calculations.

The goal is controlled, compliant scheduling (batch size, min/max delay per email,
daily maximum, sending hours/days) — never evasion of provider safeguards.
All scheduling math operates in the campaign's declared time zone; timestamps are
converted to/from UTC at the boundaries (DB stores UTC only).
"""
from __future__ import annotations

import random
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.campaign import Campaign


def parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None
    try:
        hour, minute = (int(p) for p in value.split(":", 1))
        return time(hour=hour, minute=minute)
    except (ValueError, TypeError):
        return None


def tz_of(campaign: Campaign) -> ZoneInfo:
    try:
        return ZoneInfo(campaign.timezone or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def jitter_delay_seconds(min_minutes: int, max_minutes: int) -> int:
    min_s = min_minutes * 60
    max_s = max_minutes * 60
    if max_s <= min_s:
        return min_s
    return random.randint(min_s, max_s)


def in_sending_window(dt: datetime, campaign: Campaign) -> bool:
    """True if `dt` (aware UTC) falls inside the campaign sending window/days."""
    tz = tz_of(campaign)
    local = dt.astimezone(tz)
    days = campaign.sending_days
    # campaign.sending_days is "1,2,3,4,5" or None -> fall back to weekdays
    allowed = {int(d) for d in (days.split(",") if days else "1,2,3,4,5".split(",")) if d.strip()}
    if local.isoweekday() not in allowed:
        return False
    start = campaign.sending_start_time
    end = campaign.sending_end_time
    if start and end:
        if not (start <= local.time() < end):
            return False
    return True


def next_window_start(dt: datetime, campaign: Campaign) -> datetime:
    """Next datetime (aware UTC) at/after dt inside the sending window."""
    tz = tz_of(campaign)
    candidate = dt.astimezone(tz)
    allowed = {int(d) for d in (campaign.sending_days.split(",") if campaign.sending_days else "1,2,3,4,5".split(",")) if d.strip()}
    start = campaign.sending_start_time or time(0, 0)
    for _ in range(14):  # look ahead at most 2 weeks
        if candidate.isoweekday() in allowed:
            if candidate.time() < start:
                candidate = datetime.combine(candidate.date(), start, tzinfo=tz)
            if campaign.sending_end_time and candidate.time() >= campaign.sending_end_time:
                candidate = datetime.combine(candidate.date() + timedelta(days=1), start, tzinfo=tz)
                continue
            return candidate.astimezone(UTC)
        candidate = datetime.combine(candidate.date() + timedelta(days=1), start, tzinfo=tz)
    return dt + timedelta(days=14)


def seconds_left_in_today(dt: datetime, campaign: Campaign) -> int:
    """Seconds remaining in today's sending window from dt (0 if outside window)."""
    if not in_sending_window(dt, campaign):
        return 0
    tz = tz_of(campaign)
    local = dt.astimezone(tz)
    end = campaign.sending_end_time
    if not end:
        return int(timedelta(days=1).total_seconds() - (local.hour * 3600 + local.minute * 60 + local.second))
    end_dt = datetime.combine(local.date(), end, tzinfo=tz)
    return max(0, int((end_dt - local).total_seconds()))


def compute_pacing_sequence(campaign: Campaign, vendor_count: int, start_at: datetime) -> list[datetime]:
    """Compute run_after timestamps for `vendor_count` initial emails.

    - No more than `batch_size` emails per batch tick.
    - Between batches, a random jitter delay in [min_delay, max_delay] minutes.
    - Never sends outside the configured window/days (shifted to the next window).
    - Respects the daily maximum by refusing to schedule beyond today's quota slots;
      remaining emails are scheduled for the next sending day(s).
    """
    tz = tz_of(campaign)
    cursor = next_window_start(start_at, campaign)
    slots: list[datetime] = []
    sent_today = 0
    local_today = cursor.astimezone(tz).date()

    for _ in range(vendor_count):
        # day rollover control
        cur_local = cursor.astimezone(tz)
        if cur_local.date() != local_today:
            local_today = cur_local.date()
            sent_today = 0
        if sent_today >= campaign.daily_max:
            # wait for next sending day
            next_day = datetime.combine(local_today + timedelta(days=1), time(0, 0), tzinfo=tz)
            cursor = next_window_start(next_day.astimezone(UTC), campaign)
            cur_local = cursor.astimezone(tz)
            local_today = cur_local.date()
            sent_today = 0
        if len(slots) % max(1, campaign.batch_size) == 0 and slots:
            delay = jitter_delay_seconds(campaign.min_delay_minutes, campaign.max_delay_minutes)
            cursor = cursor + timedelta(seconds=delay)
            cursor = next_window_start(cursor, campaign)
            cur_local = cursor.astimezone(tz)
            if cur_local.date() != local_today:
                local_today = cur_local.date()
                sent_today = 0
        slots.append(cursor)
        sent_today += 1

    # If a batch is larger than the daily max, cap at daily max per day.
    capped: list[datetime] = []
    day_bucket: dict[date, int] = {}
    for slot in slots:
        d = slot.astimezone(tz).date()
        if day_bucket.get(d, 0) >= campaign.daily_max:
            next_day = datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=tz)
            slot = next_window_start(next_day.astimezone(UTC), campaign)
            d = slot.astimezone(tz).date()
        day_bucket[d] = day_bucket.get(d, 0) + 1
        capped.append(slot)
    return capped


def ai_reply_delay_seconds(campaign: Campaign) -> int:
    mode = getattr(campaign, "ai_reply_mode", "delayed")
    min_m = getattr(campaign, "ai_reply_min_delay_minutes", 3)
    max_m = getattr(campaign, "ai_reply_max_delay_minutes", 10)
    if mode == "immediate":
        return 0
    return jitter_delay_seconds(min_m, max_m)