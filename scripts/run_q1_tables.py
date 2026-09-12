"""Reproducible synthetic-only paper tables; no original workbook access."""
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_q1_comparison import cases, encode
from src.core import BatteryParams
from src.q1.compare import compare_q1_strategies
from src.q1.solve import prepare_q1_inputs
from src.q1.tables import TableTimeContract, ZONE, extract_q1_tables, render_q1_tables_markdown


def main():
    start = datetime(2025, 12, 31, tzinfo=ZONE)
    contract = TableTimeContract(date(2025, 12, 31),
        tuple(start+timedelta(minutes=10*i) for i in range(145)), "synthetic-144-v1", "synthetic")
    reports, markdown = {}, ["# Q1 合成论文表格", "", "以下全部是合成验证数据，不是赛题计算结果。日期仅用于测试跨年边界。", ""]
    for name, load, pv, price in cases():
        inputs = dict(load_kwh=load, pv_forecast_kwh=pv, price_yuan_per_kwh=price,
            initial_energy_kwh=6000, battery_params=BatteryParams(.9, .9, "bus"),
            slot_ids=list(range(144)), input_metadata=dict(input_kind="synthetic",
                data_version=name+"-v1", mapping_version="synthetic-144-v1", assumptions_version="0.9-bus-neutral-v1"))
        model, _, _ = prepare_q1_inputs(**inputs)
        comparison = compare_q1_strategies(**inputs)
        if comparison["status"] != "passed":
            raise RuntimeError(name + " comparison failed")
        tables = {strategy: extract_q1_tables(result, model=model, price_yuan_per_kwh=price,
                  time_contract=contract, strategy=strategy)
                  for strategy, result in comparison["strategies"].items()}
        reports[name] = {"input": inputs, "comparison": comparison, "tables": tables}
        markdown += ["## " + name, ""] + [render_q1_tables_markdown(t) for t in tables.values()]
    output = ROOT / "analysis/q1_tables"
    output.mkdir(parents=True, exist_ok=True)
    bundle = {"scope": "synthetic-only; not competition results or Gate 2 acceptance", "reports": reports,
              "code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted((ROOT / "src").rglob("*.py")) + [Path(__file__).resolve()]}}
    (output / "tables.json").write_text(json.dumps(bundle, default=encode, ensure_ascii=False, indent=2)+"\n")
    (output / "tables.md").write_text("\n".join(markdown)+"\n")
    print("SYNTHETIC ONLY: 3 cases x 3 strategies; analysis/q1_tables/tables.{json,md}")


if __name__ == "__main__":
    main()
