"""Connect a midnight forecast to the shared deterministic planning kernel."""
from src.core.model import build_microgrid_constraints
from src.core.solver import solve_model
from .forecast import check_time, midnight


def plan_from_forecast(forecast, *, price_yuan_per_kwh, price_available_at,
                       battery_params, initial_energy_kwh, terminal_energy_kwh):
    if forecast.status != 'ready':
        raise ValueError('No dispatch from an unavailable forecast')
    check_time(price_available_at)
    if (forecast.issue_time != midnight(forecast.target_day)
            or price_available_at > forecast.issue_time
            or forecast.source_day >= forecast.target_day
            or forecast.source_available_at is None
            or forecast.source_available_at > forecast.issue_time):
        raise ValueError('Invalid forecast/price information cutoff')
    if len(forecast.load_kwh) != 144 or len(forecast.pv_kwh) != 144:
        raise ValueError('Full-day forecasts required')
    model = build_microgrid_constraints(load_kwh=forecast.load_kwh, pv_kwh=forecast.pv_kwh,
        battery_params=battery_params, initial_energy_kwh=initial_energy_kwh,
        terminal_energy_kwh=terminal_energy_kwh)
    result = solve_model(model, price_yuan_per_kwh=price_yuan_per_kwh)
    result.metadata.update(scope='forecast-based plan only; no realized execution or emergency settlement',
        method=forecast.method, issue_time=forecast.issue_time.isoformat(),
        source_day=forecast.source_day.isoformat(), price_available_at=price_available_at.isoformat(),
        initial_energy_kwh=initial_energy_kwh, terminal_energy_kwh=terminal_energy_kwh)
    return result
