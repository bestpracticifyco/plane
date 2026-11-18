# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Recurrence schedules: pure date arithmetic, no database.

A schedule is a small JSON object (stored on ExtRecurrenceRule.schedule):

    {"freq": "daily",   "interval": 1, "skip_weekends": true}
    {"freq": "weekly",  "interval": 2, "weekdays": [0, 3]}             # Mon=0 .. Sun=6
    {"freq": "monthly", "interval": 1, "mode": "same_day", "day": 31}  # clamped to month length
    {"freq": "monthly", "mode": "nth_weekday", "nth": 4, "weekday": 6} # 4th Sunday; nth -1 = last
    {"freq": "monthly", "mode": "first_day" | "last_day"}
    {"freq": "monthly", "mode": "business_day", "nth": 5}              # 5th US business day
    {"freq": "monthly", "mode": "days", "days": [1, 15]}               # semi-monthly
    {"freq": "yearly",  "interval": 1, "month": 1, "day": 31}
    {"freq": "days_after", "days": 7}                                  # N days after completion

`anchor` (ISO date) fixes which weeks/months/years count for intervals > 1; it is the series' first due date.
"""

import calendar
import datetime as dt
from functools import lru_cache

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_LONG_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", -1: "last"}
FREQS = {"daily", "weekly", "monthly", "yearly", "days_after"}
MONTHLY_MODES = {"same_day", "nth_weekday", "first_day", "last_day", "business_day", "days"}
_HORIZON_DAYS = 3 * 366 + 31  # enough for "every 3 years"; longer is rejected by validate()


class ScheduleError(ValueError):
    pass


def _ordinal(n):
    return _ORDINAL.get(n, f"{n}th")


# ---------------------------------------------------------------------------------------------
# US federal holidays (observed), for business-day schedules
# ---------------------------------------------------------------------------------------------
def _nth_weekday(year, month, weekday, nth):
    days = [
        d for d in range(1, calendar.monthrange(year, month)[1] + 1) if dt.date(year, month, d).weekday() == weekday
    ]
    return dt.date(year, month, days[nth - 1] if nth > 0 else days[nth])


def _observed(d):
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


@lru_cache(maxsize=64)
def us_federal_holidays(year):
    return frozenset(
        {
            _observed(dt.date(year, 1, 1)),
            _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
            _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
            _nth_weekday(year, 5, 0, -1),  # Memorial Day
            _observed(dt.date(year, 6, 19)),
            _observed(dt.date(year, 7, 4)),
            _nth_weekday(year, 9, 0, 1),  # Labor Day
            _nth_weekday(year, 10, 0, 2),  # Columbus Day
            _observed(dt.date(year, 11, 11)),
            _nth_weekday(year, 11, 3, 4),  # Thanksgiving
            _observed(dt.date(year, 12, 25)),
        }
        # New Year's Day of next year observed on Dec 31 belongs here too
        | ({dt.date(year, 12, 31)} if dt.date(year + 1, 1, 1).weekday() == 5 else set())
    )


def is_business_day(d):
    return d.weekday() < 5 and d not in us_federal_holidays(d.year)


def nth_business_day(year, month, nth):
    days = [
        dt.date(year, month, x)
        for x in range(1, calendar.monthrange(year, month)[1] + 1)
        if is_business_day(dt.date(year, month, x))
    ]
    return days[min(nth, len(days)) - 1]


# ---------------------------------------------------------------------------------------------
# Validation, matching, next occurrence
# ---------------------------------------------------------------------------------------------
def validate(schedule):
    """Return a normalised copy of `schedule` or raise ScheduleError."""
    if not isinstance(schedule, dict) or schedule.get("freq") not in FREQS:
        raise ScheduleError("freq must be one of: " + ", ".join(sorted(FREQS)))
    s = dict(schedule)
    s["interval"] = int(s["interval"]) if s.get("interval") is not None else 1
    if not 1 <= s["interval"] <= 36:
        raise ScheduleError("interval must be between 1 and 36")
    f = s["freq"]
    if f == "yearly" and s["interval"] > 3:
        raise ScheduleError("yearly interval must be at most 3")
    if f == "days_after":
        s["days"] = int(s.get("days") or 0)
        if not 1 <= s["days"] <= 365:
            raise ScheduleError("days must be between 1 and 365")
    if f == "weekly":
        s["weekdays"] = sorted({int(w) for w in s.get("weekdays") or []})
        if not s["weekdays"] or any(w not in range(7) for w in s["weekdays"]):
            raise ScheduleError("weekly needs one or more weekdays (0=Mon .. 6=Sun)")
    if f == "monthly":
        mode = s.setdefault("mode", "same_day")
        if mode not in MONTHLY_MODES:
            raise ScheduleError("monthly mode must be one of: " + ", ".join(sorted(MONTHLY_MODES)))
        if mode == "same_day" and not 1 <= int(s.get("day") or 0) <= 31:
            raise ScheduleError("day must be between 1 and 31")
        if mode == "nth_weekday" and (
            int(s.get("nth") or 0) not in (1, 2, 3, 4, 5, -1) or int(s.get("weekday", -1)) not in range(7)
        ):
            raise ScheduleError("nth_weekday needs nth (1-5 or -1) and weekday (0-6)")
        if mode == "business_day" and not 1 <= int(s.get("nth") or 0) <= 23:
            raise ScheduleError("business_day needs nth between 1 and 23")
        if mode == "days":
            s["days"] = sorted({int(x) for x in s.get("days") or []})
            if not s["days"] or any(not 1 <= x <= 31 for x in s["days"]):
                raise ScheduleError("days needs day numbers between 1 and 31")
    if f == "yearly" and not (1 <= int(s.get("month") or 0) <= 12 and 1 <= int(s.get("day") or 0) <= 31):
        raise ScheduleError("yearly needs month (1-12) and day (1-31)")
    return s


def _clamp(year, month, day):
    return min(day, calendar.monthrange(year, month)[1])


def _month_index(d):
    return d.year * 12 + d.month


def matches(s, d, anchor):
    f, n = s["freq"], s.get("interval", 1)
    if f == "daily":
        return (d - anchor).days % n == 0 and not (s.get("skip_weekends") and d.weekday() >= 5)
    if f == "weekly":
        week = (d - dt.timedelta(days=d.weekday()) - (anchor - dt.timedelta(days=anchor.weekday()))).days // 7
        return d.weekday() in s["weekdays"] and week % n == 0
    if f == "monthly":
        if (_month_index(d) - _month_index(anchor)) % n:
            return False
        mode = s["mode"]
        last = calendar.monthrange(d.year, d.month)[1]
        if mode == "same_day":
            return d.day == _clamp(d.year, d.month, int(s["day"]))
        if mode == "first_day":
            return d.day == 1
        if mode == "last_day":
            return d.day == last
        if mode == "nth_weekday":
            nth = int(s["nth"])
            try:
                return d == _nth_weekday(d.year, d.month, int(s["weekday"]), nth)
            except IndexError:  # no 5th such weekday this month: skip the month
                return False
        if mode == "business_day":
            return d == nth_business_day(d.year, d.month, int(s["nth"]))
        if mode == "days":
            return d.day in {_clamp(d.year, d.month, x) for x in s["days"]}
    if f == "yearly":
        return (
            (d.year - anchor.year) % n == 0
            and d.month == int(s["month"])
            and d.day == _clamp(d.year, d.month, int(s["day"]))
        )
    return False


def next_after(schedule, after, anchor=None):
    """First due date strictly after `after` (a date). days_after schedules: `after` is the completion date."""
    s = validate(schedule)
    if s["freq"] == "days_after":
        return after + dt.timedelta(days=s["days"])
    anchor = anchor or after
    d = after + dt.timedelta(days=1)
    for _ in range(_HORIZON_DAYS):
        if matches(s, d, anchor):
            return d
        d += dt.timedelta(days=1)
    raise ScheduleError("no occurrence within three years")


def first_on_or_after(schedule, day, anchor=None):
    return next_after(schedule, day - dt.timedelta(days=1), anchor or day)


def summary(schedule):
    """Short human label, e.g. 'Monthly · 4th Sunday' (the 'Repeats' column)."""
    s = validate(schedule)
    f, n = s["freq"], s["interval"]
    every = lambda unit, plural: unit if n == 1 else f"Every {n} {plural}"  # noqa: E731
    if f == "daily":
        base = every("Daily", "days")
        return base + (" · weekdays" if s.get("skip_weekends") else "")
    if f == "weekly":
        base = "Bi-weekly" if n == 2 else every("Weekly", "weeks")
        return f"{base} · " + ", ".join(WEEKDAY_NAMES[w] for w in s["weekdays"])
    if f == "monthly":
        base = "Quarterly" if n == 3 else every("Monthly", "months")
        mode = s["mode"]
        detail = {
            "same_day": lambda: f"day {s['day']}",
            "first_day": lambda: "first day",
            "last_day": lambda: "last day",
            "nth_weekday": lambda: f"{_ordinal(int(s['nth']))} {_LONG_DAYS[int(s['weekday'])]}",
            "business_day": lambda: f"{_ordinal(int(s['nth']))} business day",
            "days": lambda: "days " + " & ".join(str(x) for x in s["days"]),
        }[mode]()
        if mode == "days" and s["days"] == [1, 15] and n == 1:
            return "Semi-monthly · 1st & 15th"
        return f"{base} · {detail}"
    if f == "yearly":
        return every("Yearly", "years") + f" · {calendar.month_abbr[int(s['month'])]} {s['day']}"
    return f"{s['days']} days after completion"
