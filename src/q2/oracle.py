"""Perfect-information diagnostics, explicitly not deployable controllers."""
import numpy as np
from src.core.model import build_microgrid_constraints
from src.core.solver import solve_model


def solve_oracle_day(*, actual_load, actual_pv, price, battery, fixed_commitment=None):
    model = build_microgrid_constraints(load_kwh=actual_load, pv_kwh=actual_pv,
        battery_params=battery, initial_energy_kwh=6000., terminal_energy_kwh=6000.,
        emergency_enabled=True, fixed_purchase_kwh=fixed_commitment)
    solution = solve_model(model, price_yuan_per_kwh=price, emergency_price_yuan_per_kwh=5*np.asarray(price))
    if solution.status != 'optimal':
        raise RuntimeError('Oracle did not attain a validated optimum: '+solution.status)
    s = solution.schedule
    costs = {'planned_yuan': float(np.asarray(price) @ s['G']), 'adjustment_yuan': 0.,
             'emergency_yuan': float(5*np.asarray(price) @ s['U'])}
    costs['total_yuan'] = sum(costs.values())
    return {'schedule': {k: v.tolist() for k, v in s.items()}, 'costs': costs,
        'planned_G': s['G'].tolist(), 'revisions': [], 'forecast_sources': {},
        'initial_energy_kwh': 6000., 'terminal_energy_kwh': float(s['E'][-1]),
        'diagnostics': solution.diagnostics, 'backend': solution.backend,
        'policy': 'perfect_information_diagnostic_not_causal',
        'fixed_commitment': fixed_commitment is not None,
        'relaxation': 'future actuals known; all battery and settlement constraints unchanged'}
