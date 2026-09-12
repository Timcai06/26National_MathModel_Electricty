"""Paired historical scenarios and one-step contract-update value estimates."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import math
import numpy as np
from src.q2.forecast import midnight,validate_days,check_time
from src.core.model import vector
from src.q3.planning import replan,adjustment_cost


@dataclass(frozen=True)
class GateConfig:
    threshold_yuan: float = 0.
    enabled: bool = True

    def __post_init__(self):
        if not math.isfinite(self.threshold_yuan) or self.threshold_yuan<0 or type(self.enabled) is not bool:
            raise ValueError('Invalid gate threshold/enabled flag')


CANDIDATES=(GateConfig(enabled=False),)+tuple(GateConfig(x) for x in (0.,100.,500.,1000.))


def joint_scenarios(history,forecasts_as_of,*,decision_time,baseline_load):
    check_time(decision_time)
    if decision_time.hour not in (6,12,18) or any((decision_time.minute,decision_time.second,decision_time.microsecond)):
        raise ValueError('Scenario decision must be at06/12/18')
    target=decision_time.date();start=midnight(target);slot=decision_time.hour*6
    days=validate_days(history)
    if any(d.day>=target or d.available_at>start for d in days):
        raise ValueError('Only completed days published by target midnight are permitted')
    if any(issue!=f.issue_time or issue>decision_time for issue,f in forecasts_as_of.items()):
        raise ValueError('Forecast map contains mismatched or unpublished information')
    current=forecasts_as_of[decision_time]
    current_pv=current.energy(decision_time=decision_time,method='linear')[:144-slot]
    load=vector(baseline_load,'baseline load',144)
    by_day={d.day:d for d in days};eligible=[]
    for d in days:
        if d.day<target-timedelta(days=28):continue
        source=by_day.get(d.day-timedelta(days=7))
        issue=midnight(d.day)+timedelta(hours=decision_time.hour)
        if source is None or source.available_at>midnight(d.day) or issue not in forecasts_as_of:continue
        eligible.append((d,source,issue))
    chosen=eligible[-20:]
    if len(chosen)<7:
        return None,{'reason':'insufficient_completed_residual_days','scenario_days':[],'scenario_count':len(chosen)}
    loads=[];pvs=[];provenance=[];clipped=0
    for d,source,issue in chosen:
        historical_pv=forecasts_as_of[issue].energy(decision_time=issue,method='linear')[:144-slot]
        scenario_load=load[slot:]+(d.load_kwh[slot:]-source.load_kwh[slot:])
        scenario_pv=current_pv+(d.pv_kwh[slot:]-historical_pv)
        clipped+=int((scenario_load<0).sum()+(scenario_pv<0).sum())
        loads.append(np.maximum(scenario_load,0.));pvs.append(np.maximum(scenario_pv,0.))
        provenance.append({'day':str(d.day),'available_at':d.available_at.isoformat(),
            'load_source_day':str(source.day),'pv_issue_time':issue.isoformat()})
    loads,pvs=np.asarray(loads),np.asarray(pvs)
    digest=hashlib.sha256(loads.tobytes()+pvs.tobytes()).hexdigest()
    return (loads,pvs),{'scenario_days':provenance,'scenario_count':len(chosen),
        'scenario_sha256':digest,'clipped_negative_points':clipped,
        'weight':'uniform recent20 joint-day residual paths within28days',
        'reference':'unmargined lag7 load and current-issue PV; no target-day actuals'}


def preview(executor):
    """Clone known state; no later contract updates, no future actuals supplied."""
    first=len(executor.records);clone=deepcopy(executor)
    for i in range(first,144):
        decision=clone.start+timedelta(minutes=10*i)
        clone.decide(decision)
        clone.settle(load_kwh=0.,pv_kwh=0.,available_at=decision+timedelta(minutes=10))
    result=clone.finish()
    return {k:np.asarray(result['schedule'][k][first:]) for k in ('G','C','D')}


def variable_cost(schedule,loads,pvs,price):
    emergency=np.maximum(loads+schedule['C']-schedule['G']-pvs-schedule['D'],0.)
    return emergency@(5*np.asarray(price))


def evaluate(executor,*,decision_time,published_as_of,history,baseline_load,config):
    slot=len(executor.records)
    if executor.pending is not None or slot not in (36,72,108) or decision_time!=executor.start+timedelta(minutes=10*slot):
        raise ValueError('Gate must run before the boundary command')
    paths,scenario_audit=joint_scenarios(history,published_as_of,decision_time=decision_time,baseline_load=baseline_load)
    audit={'decision_time':decision_time.isoformat(),'first_slot':slot,'scenario':scenario_audit,
           'threshold_yuan':config.threshold_yuan,'enabled':config.enabled,
           'continuation':'freeze each candidate contract and its control forecast until midnight; later gates not anticipated'}
    if paths is None:
        audit.update(accept=False,reason='insufficient_history')
        return None,audit,None
    new_pv=published_as_of[decision_time].energy(decision_time=decision_time,method='linear')[:144-slot]
    old=executor.g[slot:].copy()
    proposal=replan(load_kwh=executor.load[slot:],pv_kwh=new_pv,old_commitment=old,
        price=executor.price[slot:],initial_energy=executor.energy,battery=executor.battery,refund=True)
    new=executor.g.copy();new[slot:]=proposal['G']
    cost=adjustment_cost(old,new[slot:],executor.price[slot:],refund=True)
    candidate=deepcopy(executor)
    delta=candidate.revise(commitment=new,remaining_load=executor.load[slot:],remaining_pv=new_pv,
                          decision_time=decision_time,forecast_available_at=decision_time)
    keep,update=preview(executor),preview(candidate)
    keep_costs=variable_cost(keep,*paths,executor.price[slot:])
    update_costs=variable_cost(update,*paths,executor.price[slot:])+cost
    gain=float(keep_costs.mean()-update_costs.mean())
    accept=config.enabled and gain>config.threshold_yuan+1e-6
    audit.update(accept=accept,reason='positive_expected_net_benefit' if accept else 'keep_current_policy',
        predicted_keep_variable_yuan=float(keep_costs.mean()),predicted_update_variable_yuan=float(update_costs.mean()),
        adjustment_yuan=cost,predicted_gain_yuan=gain,keep_scenario_costs=keep_costs.tolist(),
        update_scenario_costs=update_costs.tolist())
    revision={'issue_time':decision_time.isoformat(),'first_slot':slot,'forecast_issue_time':decision_time.isoformat(),
        'initial_energy_kwh':executor.energy,'old_remaining_kwh':old.tolist(),'new_remaining_kwh':new[slot:].tolist(),
        'incremental_cost_yuan':cost,**delta,'diagnostics':proposal['diagnostics'],
        'objective_residual_yuan':proposal['objective_residual_yuan']}
    proposal_data={'commitment':new,'remaining_pv':new_pv,'revision':revision}
    return proposal_data,audit,(keep,update)
