"""Extract paper tables from revalidated schedules and explicit physical time."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from src.core.model import vector
from src.core.validation import TOLERANCE, validate_solution

ZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class TableTimeContract:
    day: date
    boundaries: tuple[datetime, ...]
    mapping_version: str
    status: str  # synthetic or accepted; acceptance is an upstream attestation

    def validate(self, metadata, *, allow_candidate_time=False):
        expected_status = {"synthetic": "synthetic", "standardized": "accepted"}.get(metadata.get("input_kind"))
        candidate = allow_candidate_time and metadata.get("input_kind") == "standardized" and self.status == "candidate"
        if not candidate and (expected_status is None or self.status != expected_status):
            raise ValueError("Physical time contract must be synthetic or explicitly accepted for real data")
        if not self.mapping_version or self.mapping_version != metadata.get("mapping_version"):
            raise ValueError("Time mapping version mismatch")
        start = datetime.combine(self.day, datetime.min.time(), tzinfo=ZONE)
        if len(self.boundaries) != 145:
            raise ValueError("145 physical boundaries required")
        for i, boundary in enumerate(self.boundaries):
            if (not isinstance(boundary, datetime) or boundary.tzinfo is None
                    or boundary.utcoffset() != timedelta(hours=8)
                    or boundary != start + timedelta(minutes=10*i)):
                raise ValueError("Physical day must span local midnight to midnight in ordered 10-minute slots")


def extract_q1_tables(result, *, model, price_yuan_per_kwh, time_contract, strategy, allow_candidate_time=False):
    """No raw files, label repair, rounding, or inferred time alignment."""
    expected_status = {"optimized": "optimal", "rule": "feasible", "no_storage": "feasible"}
    if strategy not in expected_status or result.status != expected_status[strategy] or result.schedule is None:
        raise ValueError("A successful Q1 strategy result is required")
    if (model.horizon != 144 or model.dt_hours != 1/6 or model.emergency_enabled
            or model.fixed_purchase is not None or model.mutual_exclusion
            or model.terminal_energy != model.initial_energy):
        raise ValueError("Pass the continuous daily-neutral Q1 validation model")
    required = ("input_kind", "data_version", "mapping_version", "assumptions_version")
    if any(not isinstance(result.metadata.get(k), str) or not result.metadata[k].strip() for k in required):
        raise ValueError("Complete input provenance required")
    time_contract.validate(result.metadata, allow_candidate_time=allow_candidate_time)
    price = vector(price_yuan_per_kwh, "price", 144)
    x = np.zeros_like(model.lower)
    schedule = {}
    for key in ("G", "C", "D", "U", "W", "E"):
        values = np.asarray(result.schedule.get(key), dtype=float)
        if values.shape != (145 if key == "E" else 144,) or not np.isfinite(values).all():
            raise ValueError("Invalid schedule array: " + key)
        schedule[key] = values.copy()
        x[model.layout[key]] = values
    diagnostics = validate_solution(model, x)
    if not diagnostics["passed"]:
        raise ValueError("Schedule failed independent physical validation")
    cost = float(price @ schedule["G"])
    if (result.objective_yuan is None or not np.isfinite(result.objective_yuan)
            or abs(cost - result.objective_yuan) >= TOLERANCE):
        raise ValueError("Reported cost does not match schedule and prices")
    boundaries = time_contract.boundaries

    def interval(a, b):
        return {"start": boundaries[a].isoformat(), "end": boundaries[b].isoformat(),
                "slot_start": a, "slot_stop": b}

    table1 = [{**interval(h*6, h*6+1), "purchase_kwh": float(schedule["G"][h*6])}
              for h in (10, 12, 14, 16, 18, 20)]
    table2 = [{**interval(a, a+24), "charge_bus_kwh": float(schedule["C"][a:a+24].sum()),
               "discharge_bus_kwh": float(schedule["D"][a:a+24].sum())}
              for a in range(0, 144, 24)]
    totals = {"purchase_kwh": float(schedule["G"].sum()), "cost_yuan": cost,
              "charge_bus_kwh": float(schedule["C"].sum()),
              "discharge_bus_kwh": float(schedule["D"].sum()),
              "initial_energy_kwh": float(schedule["E"][0]),
              "terminal_energy_kwh": float(schedule["E"][-1])}
    return {"strategy": strategy, "metadata": {k: result.metadata[k] for k in required},
            "day": time_contract.day.isoformat(), "time_contract_status": time_contract.status,
            "physical_boundaries": [b.isoformat() for b in boundaries],
            "table1": table1, "table2": table2, "daily_totals": totals,
            "validation": diagnostics}


def render_q1_tables_markdown(tables):
    """Round only the human-readable view; JSON retains full precision."""
    label = "合成验证，不能作为赛题结果" if tables["metadata"]["input_kind"] == "synthetic" else "标准化输入结果，仍需论文验收"
    if tables["time_contract_status"] == "candidate":
        label = "真实附件候选结果：时间映射和模型假设未最终验收；日期仅作代表日锚点"
    lines = [f"### {tables['strategy']} / {tables['day']}", "", label, "",
             "表1：指定物理时段购电量", "", "| 时段 | 购电量（kWh） |", "| --- | ---: |"]
    def span(row):
        end = "24:00" if row["slot_stop"] == 144 else row["end"][11:16]
        return row["start"][11:16] + "–" + end
    for row in tables["table1"]:
        lines.append(f"| {span(row)} | {row['purchase_kwh']:.6f} |")
    totals = tables["daily_totals"]
    lines += ["", f"全天购电量：{totals['purchase_kwh']:.6f} kWh；全天费用：{totals['cost_yuan']:.6f} 元。", "",
              "表2：四小时段充放电量（母线侧）", "",
              "| 时段 | 充电量（kWh） | 放电量（kWh） |", "| --- | ---: | ---: |"]
    for row in tables["table2"]:
        lines.append(f"| {span(row)} | {row['charge_bus_kwh']:.6f} | {row['discharge_bus_kwh']:.6f} |")
    lines += ["", f"起始储电量：{totals['initial_energy_kwh']:.6f} kWh；结束储电量：{totals['terminal_energy_kwh']:.6f} kWh。", ""]
    return "\n".join(lines)
