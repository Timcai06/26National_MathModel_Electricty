"""As-of net-load residual bank and a small frozen safety-margin family."""
from dataclasses import asdict, dataclass
from datetime import timedelta
import numpy as np
from .forecast import midnight, validate_days
from src.core.model import vector


@dataclass(frozen=True)
class MarginConfig:
    tau: float
    scale: float
    window_days: int = 28
    bucket_slots: int = 24
    min_days: int = 7

    def __post_init__(self):
        if not (0 < self.tau < 1) or not np.isfinite(self.scale) or self.scale < 0:
            raise ValueError('Invalid quantile/scale')
        if (type(self.window_days) is not int or self.window_days < 1 or
            type(self.min_days) is not int or not 1 <= self.min_days <= self.window_days or
            type(self.bucket_slots) is not int or self.bucket_slots < 1 or 144 % self.bucket_slots):
            raise ValueError('Invalid residual window/buckets')


CANDIDATES = (MarginConfig(.8, 0.),) + tuple(MarginConfig(tau, scale)
    for tau in (.6, .7, .8, .9) for scale in (.5, 1.))


def safety_forecast(history, *, target_day, baseline_load, baseline_pv, config):
    """Receive only already-published whole days, never a target-day actual.

    Residuals use fixed lag7 load / lag1 PV. Pool 24 slots per 4h bucket,
    quantile the RAW residual once, then clip its safety margin at zero.
    """
    issue = midnight(target_day)
    records = validate_days(history)
    if any(d.day >= target_day or d.available_at > issue for d in records):
        raise ValueError('Residual bank received future/unpublished actuals')
    by_day = {d.day: d for d in records}
    bank, provenance = [], []
    for d in records:
        if d.day < target_day-timedelta(days=config.window_days):
            continue
        load_day = by_day.get(d.day-timedelta(days=7))
        pv_day = by_day.get(d.day-timedelta(days=1))
        if load_day is None or pv_day is None:
            continue
        if load_day.available_at > midnight(d.day) or pv_day.available_at > midnight(d.day):
            continue
        error = d.load_kwh-d.pv_kwh-(load_day.load_kwh-pv_day.pv_kwh)
        bank.append(error)
        provenance.append({'day': str(d.day), 'available_at': d.available_at.isoformat(),
            'load_source_day': str(load_day.day), 'pv_source_day': str(pv_day.day)})
    load = vector(baseline_load, 'baseline_load', 144)
    pv = vector(baseline_pv, 'baseline_pv', 144)
    correction = np.zeros(144)
    quantiles = []
    if len(bank) >= config.min_days:
        errors = np.stack(bank)
        for first in range(0, 144, config.bucket_slots):
            q = float(np.quantile(errors[:, first:first+config.bucket_slots], config.tau, method='linear'))
            quantiles.append(q)
            correction[first:first+config.bucket_slots] = config.scale*max(0., q)
    return {'load': load+correction, 'pv': pv}, {
        'available_at': issue.isoformat(), 'config': asdict(config), 'residual_days': provenance,
        'bucket_raw_quantiles_kwh': quantiles, 'correction_kwh': correction.tolist(),
        'fallback': 'zero_margin_insufficient_history' if len(bank) < config.min_days else None,
        'formula': 'scale * max(0, raw_residual_quantile); no additional bias term'}
