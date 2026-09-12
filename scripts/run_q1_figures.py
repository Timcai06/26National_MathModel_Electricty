"""Render existing synthetic table evidence without re-solving or raw-data IO."""
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from src.core import BatteryParams
from src.core.solver import SolveResult
from src.q1.solve import prepare_q1_inputs
from src.q1.tables import TableTimeContract, extract_q1_tables

COLORS = {"no_storage": "#77828c", "rule": "#c47a26", "optimized": "#167d9a"}
LABELS = {"no_storage": "No storage", "rule": "Rule", "optimized": "Optimized"}


def validate_report(report, *, allow_candidate_time=False):
    inputs = dict(report["input"])
    if inputs["input_metadata"]["input_kind"] != "synthetic" and not allow_candidate_time:
        raise ValueError("This demonstration accepts synthetic evidence only")
    inputs["battery_params"] = BatteryParams(**inputs["battery_params"])
    model, price, _ = prepare_q1_inputs(**inputs)
    if report["comparison"]["status"] != "passed":
        raise ValueError("Comparison did not pass")
    for name in COLORS:
        recorded = report["tables"][name]
        contract = TableTimeContract(date.fromisoformat(recorded["day"]),
            tuple(datetime.fromisoformat(t) for t in recorded["physical_boundaries"]),
            recorded["metadata"]["mapping_version"], recorded["time_contract_status"])
        actual = extract_q1_tables(SolveResult(**report["comparison"]["strategies"][name]),
            model=model, price_yuan_per_kwh=price, time_contract=contract, strategy=name, allow_candidate_time=allow_candidate_time)
        # Full table equality ties every displayed total and interval to this schedule.
        for key in ("table1", "table2", "daily_totals", "metadata", "physical_boundaries"):
            if actual[key] != recorded[key]:
                raise ValueError("Table/schedule mismatch: " + name + "/" + key)
        if recorded["physical_boundaries"] != report["tables"]["optimized"]["physical_boundaries"]:
            raise ValueError("Strategies have different physical axes")
    return model, price


def draw_case(name, report, output, *, allow_candidate_time=False):
    model, price = validate_report(report, allow_candidate_time=allow_candidate_time)
    edges = np.arange(145) / 6
    strategies = report["comparison"]["strategies"]
    fig, axes = plt.subplots(5, 1, figsize=(12, 13), sharex=True, layout="constrained")
    scope = "REAL INPUT / CANDIDATE ASSUMPTIONS — not final submission" if report["input"]["input_metadata"]["input_kind"] == "standardized" else "SYNTHETIC VALIDATION ONLY — not competition results"
    fig.suptitle(f"Q1 | {name}\n{scope}", fontsize=15)
    axes[0].stairs(model.load, edges, baseline=None, label="Load", color="#313f50", linewidth=1.3)
    axes[0].stairs(model.pv, edges, baseline=None, label="PV forecast", color="#caab36", linewidth=1.3)
    axes[0].set_ylabel("Energy / slot (kWh)")
    axes[0].set_title("Inputs and grid purchases", loc="left")
    for strategy, result in strategies.items():
        s = result["schedule"]
        axes[1].stairs(s["G"], edges, baseline=None, color=COLORS[strategy], label=LABELS[strategy], linewidth=1.2)
        axes[3].plot(edges, s["E"], color=COLORS[strategy], label=LABELS[strategy], linewidth=1.4,
                     linestyle={"no_storage": ":", "rule": "--", "optimized": "-"}[strategy])
    axes[1].set_ylabel("Grid / slot (kWh)")
    s = strategies["optimized"]["schedule"]
    axes[2].stairs(s["C"], edges, fill=True, alpha=.7, color="#167d9a", label="Charge (+)")
    axes[2].stairs(-np.asarray(s["D"]), edges, fill=True, alpha=.7, color="#c47a26", label="Discharge (−)")
    dispatch_limit = max(1., float(np.max(np.abs(s["C"]))), float(np.max(np.abs(s["D"])))) * 1.25
    axes[2].set_ylim(-dispatch_limit, dispatch_limit)
    axes[2].axhline(0, color="#777777", linewidth=.6)
    axes[2].set_ylabel("Bus energy / slot (kWh)")
    axes[2].set_title("Optimized battery dispatch", loc="left")
    axes[3].axhline(model.battery.min_energy_kwh, color="#b95555", linestyle=":", label="Energy bounds")
    axes[3].axhline(model.battery.max_energy_kwh, color="#b95555", linestyle=":")
    axes[3].set_ylabel("Stored energy (kWh)")
    axes[4].stairs(price, edges, baseline=None, color="#8063a8", label="Price")
    axes[4].set_ylabel("Price (yuan/kWh)")
    axes[4].set_xlabel("Physical local hour (Asia/Shanghai); 24:00 = next midnight")
    for ax in axes:
        ax.grid(axis="y", alpha=.18)
        ax.legend(loc="upper left", ncol=4, fontsize=8, framealpha=.85)
        ax.set_xlim(0, 24)
        ax.set_xticks(np.arange(0, 25, 2))
        ax.spines[["top", "right"]].set_visible(False)
        ax.margins(y=.18)
    paths = []
    for extension in ("png", "svg"):
        path = output / f"{name}.{extension}"
        fig.savefig(path, dpi=160)
        paths.append(path)
    plt.close(fig)
    return paths


def draw_costs(reports, output):
    fig, axes = plt.subplots(1, len(reports), figsize=(13, 4.5), layout="constrained")
    fig.suptitle("Daily purchase cost | SYNTHETIC ONLY", fontsize=14)
    for ax, (name, report) in zip(np.atleast_1d(axes), reports.items()):
        costs = [report["tables"][s]["daily_totals"]["cost_yuan"] for s in COLORS]
        bars = ax.bar(list(LABELS.values()), costs, color=list(COLORS.values()), width=.6)
        ax.bar_label(bars, fmt="%.2f", padding=4, fontsize=9)
        ax.set_title(name, fontsize=11)
        ax.set_ylabel("Purchase cost (yuan)")
        ax.set_ylim(0, max(max(costs)*1.22, 1))
        ax.grid(axis="y", alpha=.18)
        ax.spines[["top", "right"]].set_visible(False)
    paths = []
    for extension in ("png", "svg"):
        path = output / f"strategy_costs.{extension}"
        fig.savefig(path, dpi=160)
        paths.append(path)
    plt.close(fig)
    return paths


def main():
    source = ROOT / "analysis/q1_tables/tables.json"
    raw = source.read_bytes()
    bundle = json.loads(raw)
    # Validate everything before writing any output.
    for report in bundle["reports"].values():
        validate_report(report)
    output = ROOT / "analysis/q1_figures"
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, report in bundle["reports"].items():
        paths += draw_case(name, report, output)
    paths += draw_costs(bundle["reports"], output)
    manifest = {"scope": "synthetic-only; no competition conclusions or Gate 2 acceptance",
        "source": str(source.relative_to(ROOT)), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "matplotlib": matplotlib.__version__, "numpy": np.__version__,
        "python": sys.version, "cases_validated": list(bundle["reports"]),
        "code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(), *sorted((ROOT / "src").rglob("*.py"))]},
        "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Validated {len(bundle['reports'])} cases; wrote {len(paths)} PNG/SVG artifacts")


if __name__ == "__main__":
    main()
