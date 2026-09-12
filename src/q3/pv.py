"""Convert one published hourly forecast without consulting any actual values."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np

from src.core.model import vector
from src.q2.forecast import check_time


@dataclass(frozen=True)
class PublishedPV:
    issue_time: datetime
    hourly_kw: object

    def __post_init__(self):
        check_time(self.issue_time)
        if self.issue_time.hour not in (0, 6, 12, 18) or any((self.issue_time.minute, self.issue_time.second, self.issue_time.microsecond)):
            raise ValueError('Expected a 00/06/12/18 forecast issue')
        object.__setattr__(self, 'hourly_kw', vector(self.hourly_kw, 'hourly forecast', 24))

    def energy(self, *, decision_time, method='linear'):
        check_time(decision_time)
        if self.issue_time > decision_time:
            raise ValueError('Unpublished forecast is unavailable')
        if method == 'step':
            return np.repeat(self.hourly_kw, 6)/6
        if method != 'linear':
            raise ValueError('Unknown forecast conversion')
        # Instantaneous hourly power. h=0 equals the first published prediction.
        # Trapezoid is exact for this piecewise-linear curve on 10-minute slots.
        boundaries = np.interp(np.arange(145)/6, np.arange(25),
                               np.r_[self.hourly_kw[0], self.hourly_kw])
        return (boundaries[:-1]+boundaries[1:])/12


def parse_forecasts(rows):
    start = datetime.fromisoformat('2025-01-01T00:00:00+08:00')
    if len(rows) != 365*4*24:
        raise ValueError('Expected all 1460 complete published forecasts')
    result = {}
    for index in range(365*4):
        issue = start+timedelta(hours=6*index)
        block = rows[index*24:(index+1)*24]
        for horizon, row in enumerate(block, 1):
            target = issue+timedelta(hours=horizon)
            if (row['date'] != str(issue.date()) or row['issue_time'] != f'{issue.hour}:00'
                    or int(row['forecast_horizon']) != horizon
                    or row['target_date'] != str(target.date())
                    or row['target_time'] != target.strftime('%H:%M:%S')):
                raise ValueError('Published forecast date/horizon mismatch; no repair')
        result[issue] = PublishedPV(issue, [float(r['pv_forecast_kw']) for r in block])
    return result
