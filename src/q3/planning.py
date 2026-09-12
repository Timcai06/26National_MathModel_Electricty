"""Convex incremental contract costs with physical LP/MILP verification."""
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import hstack, vstack, eye, csc_matrix

from src.core.model import build_microgrid_constraints, vector
from src.core.validation import validate_solution


def adjustment_cost(old, new, price, *, refund=True):
    old = vector(old, 'old commitment')
    new, price = vector(new, 'new commitment', len(old)), vector(price, 'price', len(old))
    up, down = np.maximum(new-old, 0), np.maximum(old-new, 0)
    return float(price @ (1.5*up + (-.5 if refund else .5)*down))


def replan(*, load_kwh, pv_kwh, old_commitment, price, initial_energy, battery, refund=True):
    n = len(load_kwh)
    old, price = vector(old_commitment, 'commitment', n), vector(price, 'price', n)
    for mutual in (False, True):
        model = build_microgrid_constraints(load_kwh=load_kwh, pv_kwh=pv_kwh,
            battery_params=battery, initial_energy_kwh=initial_energy,
            terminal_energy_kwh=6000, mutual_exclusion=mutual)
        m = len(model.lower)
        # t >= G-old, t >= 0. Slopes of incremental cost are .5p/1.5p
        # with refund and -.5p/1.5p without refund; both convex.
        aeq = hstack([model.a_eq, csc_matrix((2*n, n))], format='csc')
        grow = csc_matrix((np.ones(n), (np.arange(n), np.arange(n))), shape=(n, m))
        aub = vstack([hstack([model.a_ub, csc_matrix((model.a_ub.shape[0], n))]),
                      hstack([grow, -eye(n)])], format='csc')
        bub = np.r_[model.b_ub, old]
        objective = np.zeros(m+n)
        objective[model.layout['G']] = (.5 if refund else -.5)*price
        objective[m:] = (1 if refund else 2)*price
        lower, upper = np.r_[model.lower, np.zeros(n)], np.r_[model.upper, np.full(n, np.inf)]
        if mutual:
            raw = milp(objective, integrality=np.r_[model.integrality, np.zeros(n)],
                bounds=Bounds(lower, upper), constraints=[LinearConstraint(aeq, model.b_eq, model.b_eq),
                LinearConstraint(aub, -np.inf, bub)], options={'time_limit': 30, 'mip_rel_gap': 0.0})
        else:
            raw = linprog(objective, A_eq=aeq, b_eq=model.b_eq, A_ub=aub, b_ub=bub,
                bounds=list(zip(lower, upper)), method='highs', options={'time_limit': 30})
        if raw.status != 0 or raw.x is None:
            raise RuntimeError(f'Rolling solve failed: {raw.status} {raw.message}')
        check = validate_solution(model, raw.x[:m])
        if not mutual and check['physical_passed'] and check['simultaneous_slots']:
            continue
        if not check['passed']:
            raise RuntimeError('Rolling physical validation failed')
        g = raw.x[model.layout['G']].copy()
        value = adjustment_cost(old, g, price, refund=refund)
        offset = float((-.5 if refund else .5)*price @ old)
        residual = abs(value-float(raw.fun)-offset)
        if residual > 1e-6:
            raise RuntimeError('Rolling objective settlement mismatch')
        return {'G': g, 'incremental_cost_yuan': value,
                'diagnostics': check, 'objective_residual_yuan': residual,
                'backend': 'highs_milp' if mutual else 'highs_lp'}
    raise RuntimeError('No validated rolling solution')
