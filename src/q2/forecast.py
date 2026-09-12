"""Daily persistence baselines with explicit publication cutoffs."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.core.model import vector

ZONE = ZoneInfo('Asia/Shanghai')


def midnight(day):
    if type(day) is not date:
        raise ValueError('Explicit calendar date required')
    return datetime.combine(day, datetime.min.time(), tzinfo=ZONE)


def check_time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(hours=8):
        raise ValueError('Explicit Shanghai local timestamp required')


@dataclass(frozen=True)
class ActualDay:
    day: date
    load_kwh: object
    pv_kwh: object
    available_at: datetime

    def __post_init__(self):
        end = midnight(self.day) + timedelta(days=1)
        check_time(self.available_at)
        if self.available_at < end:
            raise ValueError('Full-day actuals cannot be available before the day ends')
        object.__setattr__(self, 'load_kwh', vector(self.load_kwh, 'daily load', 144))
        object.__setattr__(self, 'pv_kwh', vector(self.pv_kwh, 'daily PV', 144))


def validate_days(days):
    records = tuple(days)
    if any(not isinstance(d, ActualDay) for d in records):
        raise ValueError('ActualDay records required')
    if any(a.day >= b.day for a, b in zip(records, records[1:])):
        raise ValueError('Dates must be unique and increasing; no automatic sorting')
    return records


def history_as_of(days, issue_time):
    """Return copies of published completed days only, never future truth."""
    check_time(issue_time)
    return tuple(ActualDay(d.day, d.load_kwh, d.pv_kwh, d.available_at)
                 for d in validate_days(days)
                 if midnight(d.day)+timedelta(days=1) <= issue_time and d.available_at <= issue_time)


@dataclass(frozen=True)
class ForecastDay:
    status: str
    method: str
    target_day: date
    issue_time: datetime
    source_day: date
    source_available_at: datetime | None
    load_kwh: object = None
    pv_kwh: object = None


def predict_day(history, *, target_day, method):
    lags = {'yesterday': 1, 'last_week': 7}
    if method not in lags:
        raise ValueError('Unknown persistence method')
    issue = midnight(target_day)
    records = validate_days(history)
    if any(d.day >= target_day or d.available_at > issue for d in records):
        raise ValueError('Forecast received unpublished or future actuals')
    source_day = target_day-timedelta(days=lags[method])
    source = next((d for d in records if d.day == source_day), None)
    if source is None:
        return ForecastDay('insufficient_history', method, target_day, issue, source_day, None)
    return ForecastDay('ready', method, target_day, issue, source_day, source.available_at,
                       vector(source.load_kwh, 'forecast load', 144), vector(source.pv_kwh, 'forecast PV', 144))
