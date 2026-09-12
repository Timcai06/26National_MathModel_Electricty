"""Lossless within-day emergency interval grouping for official outputs."""
import numpy as np


def time_label(slot):
    minutes = slot*10
    return f'{minutes//60}:{minutes%60:02d}'


def emergency_intervals(values):
    values = np.asarray(values, dtype=float)
    if values.shape != (144,) or not np.isfinite(values).all() or values.min() < -1e-6:
        raise ValueError('Expected validated 144-slot emergency purchases')
    rows, i = [], 0
    while i < 144:
        if values[i] <= 1e-8:
            i += 1
            continue
        start = i
        while i < 144 and values[i] > 1e-8:
            i += 1
        rows.append({'start_slot': start, 'end_slot_exclusive': i,
                     'interval': f'{time_label(start)}-{time_label(i)}',
                     'purchase_kwh': float(values[start:i].sum())})
    if abs(sum(r['purchase_kwh'] for r in rows)-values.sum()) > 1e-6:
        raise ValueError('Emergency grouping lost energy')
    return rows
