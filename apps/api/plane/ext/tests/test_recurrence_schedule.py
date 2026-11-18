# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Recurrence schedule arithmetic (no database)."""

import datetime as dt

import pytest

from plane.ext.recurrence import ScheduleError, first_on_or_after, is_business_day, next_after, summary, validate

D = dt.date


def seq(schedule, start, count, anchor=None):
    out, d = [], start
    for _ in range(count):
        d = next_after(schedule, d, anchor or start)
        out.append(d)
    return out


def test_daily_and_skip_weekends():
    assert seq({"freq": "daily"}, D(2026, 11, 20), 3) == [D(2026, 11, 21), D(2026, 11, 22), D(2026, 11, 23)]
    assert seq({"freq": "daily", "skip_weekends": True}, D(2026, 11, 20), 2) == [D(2026, 11, 23), D(2026, 11, 24)]


def test_weekly_multiple_days_and_biweekly():
    assert seq({"freq": "weekly", "weekdays": [0, 3]}, D(2026, 11, 16), 3) == [
        D(2026, 11, 19),
        D(2026, 11, 23),
        D(2026, 11, 26),
    ]
    s = {"freq": "weekly", "interval": 2, "weekdays": [4]}
    assert seq(s, D(2026, 11, 20), 2) == [D(2026, 12, 4), D(2026, 12, 18)]


def test_monthly_same_day_clamps_and_returns():
    s = {"freq": "monthly", "mode": "same_day", "day": 31}
    assert seq(s, D(2027, 1, 31), 3) == [D(2027, 2, 28), D(2027, 3, 31), D(2027, 4, 30)]


def test_monthly_nth_weekday_first_last_day():
    fourth_sunday = {"freq": "monthly", "mode": "nth_weekday", "nth": 4, "weekday": 6}
    assert seq(fourth_sunday, D(2026, 11, 22), 2) == [D(2026, 12, 27), D(2027, 1, 24)]
    last_friday = {"freq": "monthly", "mode": "nth_weekday", "nth": -1, "weekday": 4}
    assert next_after(last_friday, D(2026, 11, 1)) == D(2026, 11, 27)
    assert next_after({"freq": "monthly", "mode": "first_day"}, D(2026, 11, 18)) == D(2026, 12, 1)
    assert next_after({"freq": "monthly", "mode": "last_day"}, D(2027, 2, 1)) == D(2027, 2, 28)


def test_fifth_weekday_skips_short_months():
    fifth_monday = {"freq": "monthly", "mode": "nth_weekday", "nth": 5, "weekday": 0}
    assert next_after(fifth_monday, D(2026, 11, 30)) == D(2027, 3, 29)


def test_business_day_skips_weekends_and_holidays():
    assert not is_business_day(D(2027, 1, 1)) and not is_business_day(D(2026, 7, 3))  # New Year; July 4 observed
    fifth_bd = {"freq": "monthly", "mode": "business_day", "nth": 5}
    # Jan 2027: 1st is a holiday, 2-3 weekend -> 4,5,6,7,8
    assert next_after(fifth_bd, D(2026, 12, 31)) == D(2027, 1, 8)
    # Sep 2027: Labor Day Mon 6th -> 1,2,3,7,8
    assert next_after(fifth_bd, D(2027, 8, 31)) == D(2027, 9, 8)


def test_semi_monthly_quarterly_yearly_days_after():
    semi = {"freq": "monthly", "mode": "days", "days": [1, 15]}
    assert seq(semi, D(2026, 11, 15), 3) == [D(2026, 12, 1), D(2026, 12, 15), D(2027, 1, 1)]
    quarterly = {"freq": "monthly", "interval": 3, "mode": "last_day"}
    assert seq(quarterly, D(2026, 12, 31), 2) == [D(2027, 3, 31), D(2027, 6, 30)]
    yearly = {"freq": "yearly", "month": 2, "day": 29}
    assert next_after(yearly, D(2027, 3, 1)) == D(2028, 2, 29)
    assert next_after({"freq": "days_after", "days": 7}, D(2026, 11, 18)) == D(2026, 11, 25)


def test_first_on_or_after_includes_the_day():
    assert first_on_or_after({"freq": "monthly", "mode": "first_day"}, D(2026, 12, 1)) == D(2026, 12, 1)


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"freq": "hourly"},
        {"freq": "weekly", "weekdays": []},
        {"freq": "monthly", "mode": "nth_weekday", "nth": 6, "weekday": 1},
        {"freq": "monthly", "mode": "same_day", "day": 0},
        {"freq": "yearly", "month": 13, "day": 1},
        {"freq": "days_after", "days": 0},
        {"freq": "daily", "interval": 0},
    ],
)
def test_validation(bad):
    with pytest.raises(ScheduleError):
        validate(bad)


def test_summaries():
    assert summary({"freq": "monthly", "mode": "nth_weekday", "nth": 4, "weekday": 6}) == "Monthly · 4th Sunday"
    assert summary({"freq": "monthly", "mode": "business_day", "nth": 5}) == "Monthly · 5th business day"
    assert summary({"freq": "weekly", "interval": 2, "weekdays": [4]}) == "Bi-weekly · Fri"
    assert summary({"freq": "monthly", "mode": "days", "days": [1, 15]}) == "Semi-monthly · 1st & 15th"
    assert summary({"freq": "monthly", "interval": 3, "mode": "last_day"}) == "Quarterly · last day"
    assert summary({"freq": "daily", "skip_weekends": True}) == "Daily · weekdays"
    assert summary({"freq": "days_after", "days": 3}) == "3 days after completion"
