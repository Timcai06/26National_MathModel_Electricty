"""Compare strategies on one identical, already-standardized Q1 day."""

from .baselines import RuleConfig, no_storage_baseline, rule_baseline
from .solve import prepare_q1_inputs, solve_q1


def compare_q1_strategies(*, rule_config=RuleConfig(), mode="auto",
                          time_limit_seconds=30, **inputs):
    model, price, metadata = prepare_q1_inputs(**inputs)
    strategies = {
        "no_storage": no_storage_baseline(model, price_yuan_per_kwh=price),
        "rule": rule_baseline(model, price_yuan_per_kwh=price, config=rule_config),
        "optimized": solve_q1(**inputs, mode=mode, time_limit_seconds=time_limit_seconds),
    }
    for result in strategies.values():
        result.metadata.update(metadata)
    failure = next((name for name, r in strategies.items()
                    if r.status != ("optimal" if name == "optimized" else "feasible")
                    or not r.diagnostics.get("passed")), None)
    report = {"status": "passed", "metadata": metadata,
              "strategies": strategies, "summary": [], "scope": "Q1 strategy comparison, not Gate 2 acceptance"}
    if failure is not None:
        report.update(status="comparison_failed", failed_strategy=failure)
        return report
    base = strategies["no_storage"].objective_yuan
    optimized = strategies["optimized"].objective_yuan
    if any(optimized > strategies[name].objective_yuan + 1e-6 for name in ["no_storage", "rule"]):
        report.update(status="comparison_failed", failed_strategy="optimized_cost_above_feasible_baseline")
        return report
    for name, result in strategies.items():
        s, cost = result.schedule, result.objective_yuan
        report["summary"].append({
            "strategy": name, "status": result.status, "cost_yuan": cost,
            "purchase_kwh": float(s["G"].sum()), "charge_bus_kwh": float(s["C"].sum()),
            "discharge_bus_kwh": float(s["D"].sum()), "surplus_kwh": float(s["W"].sum()),
            "initial_energy_kwh": float(s["E"][0]), "terminal_energy_kwh": float(s["E"][-1]),
            "minimum_energy_kwh": float(s["E"].min()), "maximum_energy_kwh": float(s["E"].max()),
            "saving_vs_no_storage_yuan": base - cost,
            "saving_fraction_vs_no_storage": None if base == 0 else (base - cost) / base,
        })
    return report
