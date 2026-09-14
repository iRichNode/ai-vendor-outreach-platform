"""Unit tests for the pacing engine (no DB required)."""
from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.models.campaign import Campaign
from app.services.pacing import (
    compute_pacing_sequence,
    in_sending_window,
    jitter_delay_seconds,
    next_window_start,
)

TZ = ZoneInfo("America/New_York")


def make_campaign(**overrides) -> Campaign:
    defaults = dict(
        id="c1",
        name="Test",
        timezone="America/New_York",
        sending_start_time=time(9, 0),
        sending_end_time=time(17, 0),
        sending_days="1,2,3,4,5",
        batch_size=5,
        daily_max=50,
        min_delay_minutes=2,
        max_delay_minutes=5,
    )
    defaults.update(overrides)
    return Campaign(**defaults)


def local(camp: Campaign) -> ZoneInfo:
    return ZoneInfo(camp.timezone or "UTC")


class TestNextWindowStart:
    def test_mid_window_unchanged(self):
        camp = make_campaign()
        dt = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)  # Mon 10:00 EDT
        assert next_window_start(dt, camp) == dt

    def test_before_window_shifted_to_open(self):
        camp = make_campaign()
        dt = datetime(2026, 9, 14, 11, 0, tzinfo=UTC)  # Mon 07:00 EDT
        out = next_window_start(dt, camp)
        assert out.astimezone(local(camp)) == datetime(2026, 9, 14, 9, 0, tzinfo=TZ)

    def test_weekend_rolls_to_monday(self):
        camp = make_campaign()
        dt = datetime(2026, 9, 12, 20, 0, tzinfo=UTC)  # Sat
        out = next_window_start(dt, camp)
        assert out.astimezone(local(camp)).isoweekday() == 1

    def test_after_end_shifts_to_next_day(self):
        camp = make_campaign()
        dt = datetime(2026, 9, 14, 22, 0, tzinfo=UTC)  # Mon 18:00 EDT (> 17:00)
        out = next_window_start(dt, camp)
        assert out.astimezone(local(camp)).isoweekday() == 2


class TestInSendingWindow:
    def test_inside(self):
        camp = make_campaign()
        assert in_sending_window(datetime(2026, 9, 14, 14, 0, tzinfo=UTC), camp)

    def test_weekend_outside(self):
        camp = make_campaign()
        assert not in_sending_window(datetime(2026, 9, 12, 14, 0, tzinfo=UTC), camp)

    def test_night_inside_when_no_window_set(self):
        camp = make_campaign(sending_start_time=None, sending_end_time=None)
        assert in_sending_window(datetime(2026, 9, 15, 3, 0, tzinfo=UTC), camp)


class TestJitter:
    def test_bounds(self):
        for _ in range(50):
            d = jitter_delay_seconds(2, 5)
            assert 120 <= d <= 300

    def test_inverted_bounds_uses_min(self):
        assert jitter_delay_seconds(10, 3) == 600


class TestPacingSequence:
    def test_count_and_monotonic(self):
        camp = make_campaign()
        start = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
        slots = compute_pacing_sequence(camp, 10, start)
        assert len(slots) == 10
        times = [s.timestamp() for s in slots]
        assert times == sorted(times)

    def test_daily_max_capped_and_shifted(self):
        camp = make_campaign(daily_max=3, batch_size=10, min_delay_minutes=0, max_delay_minutes=0)
        start = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
        slots = compute_pacing_sequence(camp, 7, start)
        assert len(slots) == 7
        days = [s.astimezone(local(camp)).date() for s in slots]
        assert days[:3] == [date(2026, 9, 14)] * 3
        assert days[3] == date(2026, 9, 15)

    def test_zero_vendors(self):
        camp = make_campaign()
        assert compute_pacing_sequence(camp, 0, datetime.now(UTC)) == []

    def test_slots_respect_window_when_past_start(self):
        camp = make_campaign(daily_max=2, batch_size=1,
                             min_delay_minutes=30, max_delay_minutes=30)
        start = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)  # 08:00 EDT
        slots = compute_pacing_sequence(camp, 6, start)
        for s in slots:
            assert s.astimezone(local(camp)).time() >= time(9, 0)