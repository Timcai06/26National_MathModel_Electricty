"""Verify the v4 candidate figure package without modifying it."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deliverables/candidate_figures/v4_advanced"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def check_png(path: Path, failures: list[str]) -> None:
    data = path.read_bytes()
    check(data[:8] == b"\x89PNG\r\n\x1a\n", f"invalid PNG signature: {path.name}", failures)
    if len(data) >= 24 and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        check(width >= 1000 and height >= 600,
              f"PNG resolution too small: {path.name} {width}x{height}", failures)


def main() -> int:
    failures: list[str] = []
    manifest_path = OUT / "manifest.json"
    check(manifest_path.exists(), "manifest.json missing", failures)
    if failures:
        print("FAIL")
        for failure in failures:
            print("-", failure)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check(manifest.get("status") == "candidate_only", "package is not candidate_only", failures)
    check(manifest.get("paper_inclusion") is False, "paper_inclusion is not false", failures)
    check(manifest.get("time_contract") == "interval-end-v1", "wrong time contract", failures)

    for relative, expected in manifest.get("source_sha256", {}).items():
        path = ROOT / relative
        check(path.exists(), f"source missing: {relative}", failures)
        if path.exists():
            check(sha256(path) == expected, f"source hash mismatch: {relative}", failures)

    for name, expected in manifest.get("outputs_sha256", {}).items():
        path = OUT / name
        check(path.exists(), f"output missing: {name}", failures)
        if path.exists():
            check(sha256(path) == expected, f"output hash mismatch: {name}", failures)

    for stem in ("fig01_prediction_consistency", "fig02_rolling_mpc_feedback", "fig03_economic_sensitivity"):
        for suffix in (".pdf", ".svg", ".png"):
            path = OUT / f"{stem}{suffix}"
            check(path.stat().st_size > 1024, f"empty output: {path.name}", failures)
            if suffix == ".pdf":
                check(path.read_bytes()[:5] == b"%PDF-", f"invalid PDF signature: {path.name}", failures)
            elif suffix == ".svg":
                text = path.read_text(encoding="utf-8", errors="replace")[:500]
                check("<svg" in text, f"invalid SVG header: {path.name}", failures)
            else:
                check_png(path, failures)

    fig1 = json.loads((OUT / "fig01_prediction_consistency_data.json").read_text(encoding="utf-8"))
    check(fig1["sankey"]["status"] == "not_implemented", "Figure 1 Sankey boundary missing", failures)
    check(fig1["sample_counts"]["load_yesterday"] == 358 * 144,
          "Figure 1 load sample count mismatch", failures)
    check(fig1["sample_counts"]["load_last_week"] == 358 * 144,
          "Figure 1 last-week sample count mismatch", failures)
    check(sum(fig1["published_pv_by_issue"]["06:00"]["state_share"].values()) > 0.999,
          "Figure 1 PV state shares incomplete", failures)

    fig2 = json.loads((OUT / "fig02_rolling_mpc_feedback_data.json").read_text(encoding="utf-8"))
    check(fig2["sample_day"] == "2025-06-21", "Figure 2 sample day changed", failures)
    check(fig2["strategy"] == "margin_fresh", "Figure 2 strategy changed", failures)
    check(fig2["is_contrast_not_mainline"] is True, "Figure 2 contrast boundary missing", failures)
    check(fig2["current_q3_mainline"] == "margin_zero", "Figure 2 mainline boundary missing", failures)
    check(fig2["updates"] == [6, 12, 18], "Figure 2 update times mismatch", failures)
    check(fig2["revision_count"] == 3, "Figure 2 revision count mismatch", failures)
    check(fig2["history_lock_passed"] is True, "Figure 2 history lock failed", failures)
    check(all(not item["future_actual_rendered"] for item in fig2["snapshots"]),
          "Figure 2 future actual was rendered", failures)

    fig3 = json.loads((OUT / "fig03_economic_sensitivity_data.json").read_text(encoding="utf-8"))
    check(fig3["grid_nodes"] == 81, "Figure 3 grid node count mismatch", failures)
    check(fig3["day_replays"] == 1377, "Figure 3 day replay count mismatch", failures)
    check(fig3["scoring_window_days"] == 17, "Figure 3 scoring window mismatch", failures)
    check(fig3["interpolation"] == "none; surface connects measured 9x9 nodes only",
          "Figure 3 interpolation boundary missing", failures)
    check(fig3["missing_panel"]["status"] == "data_insufficient",
          "Figure 3 missing-data panel boundary missing", failures)
    check(abs(fig3["global_min"]["total_yuan"] - 929199.2110005622) < 1e-6,
          "Figure 3 global minimum mismatch", failures)
    check(abs(fig3["original_frozen_candidate"]["total_yuan"] - 930672.1511948517) < 1e-6,
          "Figure 3 frozen candidate mismatch", failures)

    if failures:
        print("FAIL")
        for failure in failures:
            print("-", failure)
        return 1
    print(json.dumps({
        "status": "passed",
        "directory": str(OUT),
        "pdf_svg_png": "headers, size and PNG dimensions checked",
        "source_hashes": "passed",
        "data_boundaries": "passed",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
