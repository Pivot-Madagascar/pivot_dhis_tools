"""Tests for create_period_range.py::create_period_range."""
import datetime as dt
import importlib

import pytest

from pivot_dhis_tools import create_period_range

# the package __init__ re-exports the function under the module's name, so fetch the module itself
mod = importlib.import_module("pivot_dhis_tools.create_period_range")


def test_end_is_exclusive():
    assert create_period_range(dt.date(2020, 1, 1), dt.date(2020, 4, 1)) == "pe:202001;202002;202003"


def test_months_are_zero_padded():
    assert create_period_range(dt.date(2020, 9, 1), dt.date(2020, 11, 1)) == "pe:202009;202010"


def test_year_rollover():
    assert create_period_range(dt.date(2025, 11, 1), dt.date(2026, 2, 1)) == "pe:202511;202512;202601"


def test_mid_month_start_and_end():
    # steps 03-15, 04-15; 05-15 is not before 05-10
    assert create_period_range(dt.date(2026, 3, 15), dt.date(2026, 5, 10)) == "pe:202603;202604"


@pytest.mark.parametrize("end", [dt.date(2026, 3, 1), dt.date(2026, 1, 1)])
def test_start_not_before_end_gives_no_periods(end):
    assert create_period_range(dt.date(2026, 3, 1), end) == "pe:"


def test_end_defaults_to_first_of_current_month(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 25)

    monkeypatch.setattr(mod, "date", FixedDate)
    # current month (202611) is excluded
    assert create_period_range(dt.date(2026, 8, 1)) == "pe:202608;202609;202610"
