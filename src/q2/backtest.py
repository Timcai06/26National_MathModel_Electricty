"""Walk-forward prediction first, truth scoring second; no economic claims."""
from datetime import timedelta
import numpy as np

from .forecast import history_as_of, midnight, predict_day, validate_days


def errors(predicted, actual):
    residual = np.asarray(predicted)-np.asarray(actual)
    return {'mae_kwh_per_slot': float(np.abs(residual).mean()),
            'rmse_kwh_per_slot': float(np.sqrt(np.mean(residual**2)))}


def walk_forward(days, *, start_day, end_day, metadata):
    records = validate_days(days)
    if midnight(start_day) > midnight(end_day):
        raise ValueError('Invalid evaluation date range')
    keys = ['input_kind','data_version','mapping_version','assumptions_version']
    if any(not isinstance(metadata.get(k),str) or not metadata[k].strip() for k in keys):
        raise ValueError('Explicit input provenance required')
    if metadata['input_kind'] not in {'synthetic','standardized'}:
        raise ValueError('Unsupported input kind')
    truth = {d.day:d for d in records}
    targets = [start_day+timedelta(days=i) for i in range((end_day-start_day).days+1)]
    if any(day not in truth for day in targets):
        raise ValueError('Missing evaluation truth; never silently skip dates')
    rows, residuals = [], {method: {'load': [], 'pv': []} for method in ['yesterday','last_week']}
    for day in targets:
        snapshot = history_as_of(records, midnight(day))
        for method in residuals:
            forecast = predict_day(snapshot, target_day=day, method=method)
            row = {'day':day.isoformat(), 'method':method, 'status':forecast.status,
                   'issue_time':forecast.issue_time.isoformat(), 'source_day':forecast.source_day.isoformat(),
                   'source_available_at':None if forecast.source_available_at is None else forecast.source_available_at.isoformat(),
                   'history_days_available':len(snapshot)}
            if forecast.status == 'ready':
                for field in ['load','pv']:
                    prediction = getattr(forecast, field+'_kwh')
                    observed = getattr(truth[day], field+'_kwh')
                    row[field+'_forecast_kwh'] = prediction.tolist()
                    row[field+'_actual_kwh'] = observed.tolist()
                    row[field+'_metrics'] = errors(prediction, observed)
                    residuals[method][field].append(prediction-observed)
            rows.append(row)
    summary = {}
    for method, fields in residuals.items():
        summary[method] = {'requested_days':len(targets), 'scored_days':len(fields['load']),
                           'unavailable_days':len(targets)-len(fields['load'])}
        for field, values in fields.items():
            summary[method][field] = errors(np.concatenate(values), 0) if values else None
    return {'status':'complete' if all(r['status']=='ready' for r in rows) else 'partial',
            'metadata':dict(metadata), 'scope':'forecast accuracy only; not realized dispatch cost or Gate 3 acceptance',
            'rows':rows, 'summary':summary}
