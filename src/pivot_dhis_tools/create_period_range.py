from datetime import date
from dateutil.relativedelta import relativedelta

def create_period_range(start: date, end: date | None = None) -> str:
    """Build a monthly period dimension for a DHIS2 analytics query.

    Steps forward one month at a time from `start` and adds each month while
    it is still before `end`, so `end` itself is excluded.

    Args:
        start: First month of the range. The day is kept while stepping, so
            ``date(2026, 1, 15)`` steps through the 15th of each month.
        end: Upper bound of the range (exclusive). Defaults to the first day
            of the current month, so the range runs through last month.

    Returns:
        The periods as a DHIS2 dimension string, e.g.
        ``"pe:202001;202002;202003"``. If `start` is not before `end` the
        result is ``"pe:"`` with no periods.
    """

    if end is None:
        today = date.today()
        end = today.replace(day=1)

    periods = []

    while(start<end):
        periods.append(f"{start.year}{str(start.month).zfill(2)}")
        start = start +relativedelta(months = 1)

    period_string = f"pe:{';'.join(periods)}"

    return period_string
