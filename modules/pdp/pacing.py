from __future__ import annotations

import datetime as dt
import random
import time
from dataclasses import dataclass
from typing import Callable
from zoneinfo import ZoneInfo


def _default_status(message: str) -> None:
    print(message, flush=True)


@dataclass
class HumanPacingConfig:
    min_delay_seconds: float = 30.0
    max_delay_seconds: float = 90.0
    break_interval_seconds: float = 3600.0
    break_duration_seconds: float = 900.0
    max_active_seconds_per_day: float = 8 * 3600.0
    workday_start: dt.time = dt.time(8, 0)
    workday_end: dt.time = dt.time(20, 0)
    timezone: str = "Europe/Helsinki"


class HumanPacingController:
    """Throttle fetches to mimic a human analyst reviewing PDPs."""

    def __init__(
        self,
        *,
        config: HumanPacingConfig | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._config = config or HumanPacingConfig()
        self._tz = ZoneInfo(self._config.timezone)
        self._status = status_callback or _default_status
        self._current_day: dt.date | None = None
        self._active_seconds = 0.0
        self._seconds_since_break = 0.0

    def wait_before_request(self) -> None:
        """Sleep as needed before issuing the next HTTP request."""

        while True:
            now = self._now()
            self._reset_if_new_day(now)
            if self._maybe_sleep_until_work_window(now):
                continue
            if self._active_seconds >= self._config.max_active_seconds_per_day:
                self._sleep_until(self._next_workday_start(now + dt.timedelta(days=1)), "daily limit reached")
                self._reset_if_new_day(self._now())
                continue
            if self._seconds_since_break >= self._config.break_interval_seconds:
                self._sleep(self._config.break_duration_seconds, "scheduled break")
                self._seconds_since_break = 0.0
                continue
            break

        delay = random.uniform(self._config.min_delay_seconds, self._config.max_delay_seconds)
        self._sleep(delay, "reading PDP", announce=False)
        self._active_seconds += delay
        self._seconds_since_break += delay

    def _now(self) -> dt.datetime:
        return dt.datetime.now(self._tz)

    def _reset_if_new_day(self, now: dt.datetime) -> None:
        if self._current_day != now.date():
            self._current_day = now.date()
            self._active_seconds = 0.0
            self._seconds_since_break = 0.0

    def _workday_window(self, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
        start = dt.datetime.combine(day, self._config.workday_start, tzinfo=self._tz)
        end = dt.datetime.combine(day, self._config.workday_end, tzinfo=self._tz)
        return start, end

    def _next_workday_start(self, current: dt.datetime) -> dt.datetime:
        day = current.date()
        while True:
            start = dt.datetime.combine(day, self._config.workday_start, tzinfo=self._tz)
            if start <= current or self._is_weekend(day):
                day += dt.timedelta(days=1)
                continue
            return start

    def _maybe_sleep_until_work_window(self, now: dt.datetime) -> bool:
        if self._is_weekend(now.date()):
            self._sleep_until(self._next_workday_start(now), "weekend")
            return True
        start, end = self._workday_window(now.date())
        if now < start:
            self._sleep_until(start, "waiting for work hours")
            return True
        if now >= end:
            self._sleep_until(self._next_workday_start(now + dt.timedelta(days=1)), "outside work hours")
            return True
        return False

    def _sleep(self, seconds: float, reason: str, *, announce: bool = True) -> None:
        if seconds <= 0:
            return
        minutes = seconds / 60.0
        if announce and minutes >= 1:
            self._status(f"[pacing] {reason} ({minutes:.1f} min pause)")
        time.sleep(seconds)

    def _sleep_until(self, target: dt.datetime, reason: str) -> None:
        delta = (target - self._now()).total_seconds()
        if delta > 0:
            self._sleep(delta, reason)

    @staticmethod
    def _is_weekend(day: dt.date) -> bool:
        return day.weekday() >= 5


__all__ = ["HumanPacingController", "HumanPacingConfig"]
