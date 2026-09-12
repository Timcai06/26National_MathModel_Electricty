"""Build the v4 candidate composite figures from audited, real model evidence.

The script is intentionally independent from the paper build chain.  It reads
the current candidate evidence and writes only to
``deliverables/candidate_figures/v4_advanced``.  No optimization is rerun and
no paper source is modified.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import textwrap
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deliverables/candidate_figures/v4_advanced"
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.path import Path as MplPath
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, PathPatch
from matplotlib.ticker import FuncFormatter
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  # registers projection

from scripts.run_real_q2_forecast import load_rows, parse_days
from src.q2.forecast import midnight
from src.q3.pv import parse_forecasts


SEED = 20260912
np.random.seed(SEED)

NAVY = "#143B5D"
BLUE = "#4EA3C7"
PALE_BLUE = "#DCEAF2"
ORANGE = "#E9A34E"
CORAL = "#D96C5F"
INK = "#263238"
MUTED = "#667780"
LIGHT = "#F7FAFC"
GRID = "#D9E3E8"
GREEN = "#4E8B73"

ISSUE_HOURS = (0, 6, 12, 18)
ISSUE_LABELS = ("00:00", "06:00", "12:00", "18:00")


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_default(value):
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value)!r}")


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )


def configure_style() -> str:
    font_name = None
    for candidate in (
        "PingFang SC",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Heiti SC",
        "Arial Unicode MS",
    ):
        try:
            font_manager.findfont(candidate, fallback_to_default=False)
        except (ValueError, RuntimeError):
            continue
        font_name = candidate
        break

    plt.rcParams.update(
        {
            "font.family": [font_name] if font_name else ["DejaVu Sans"],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK,
            "axes.titlecolor": NAVY,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": INK,
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    return font_name or "DejaVu Sans"


def strip_spines(ax, grid_axis: str | None = None) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(0.8)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.55, alpha=0.55)
        ax.set_axisbelow(True)


def panel_label(ax, label: str, *, x: float = -0.08, y: float = 1.04) -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        fontsize=13,
        fontweight="bold",
        color=CORAL,
        ha="left",
        va="bottom",
        clip_on=False,
    )


def panel_label_3d(ax, label: str) -> None:
    ax.text2D(
        -0.08,
        1.04,
        label,
        transform=ax.transAxes,
        fontsize=13,
        fontweight="bold",
        color=CORAL,
        ha="left",
        va="bottom",
    )


def audited_csv(relative_path: str) -> tuple[list[dict[str, str]], str]:
    path = ROOT / relative_path
    audit_path = ROOT / "analysis/team_delivery/intake_audit.json"
    digest = sha256(path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    expected = audit.get("input_sha256", {}).get(relative_path)
    if expected and expected != digest:
        raise RuntimeError(f"Audited source changed: {relative_path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle)), digest


def read_context() -> dict:
    raw_rows, annual_path, annual_hash = load_rows()
    days = parse_days(raw_rows, delay_minutes=0)
    forecast_rows, forecast_hash = audited_csv("data/processed/team_delivery/pv_forecast.csv")
    published = parse_forecasts(forecast_rows)
    error_rows, error_hash = audited_csv("analysis/team_delivery/pv_forecast_error.csv")

    q2_forecast_path = ROOT / "analysis/real_q2_forecast_candidate/result.json"
    q2_margin_path = ROOT / "analysis/q2_margin_oracle_v1/result.json"
    q3_path = ROOT / "analysis/strict_q3_transfer_v1/result.json"
    q3_selected_path = ROOT / "analysis/strict_q3_transfer_v1/selected_days.json"
    q2_surface_path = ROOT / "analysis/q2_january_surface_v1/result.json"
    q2_surface_protocol_path = ROOT / "analysis/q2_january_surface_v1/protocol.json"
    q2_surface_validation_path = ROOT / "analysis/q2_january_surface_v1/validation.json"
    frozen_path = ROOT / "analysis/q2_margin_oracle_v1/frozen_selection.json"

    return {
        "raw_rows": raw_rows,
        "annual_path": annual_path,
        "annual_hash": annual_hash,
        "days": days,
        "published": published,
        "forecast_hash": forecast_hash,
        "pv_error_rows": error_rows,
        "pv_error_hash": error_hash,
        "q2_forecast": json.loads(q2_forecast_path.read_text(encoding="utf-8")),
        "q2_margin": json.loads(q2_margin_path.read_text(encoding="utf-8")),
        "q3": json.loads(q3_path.read_text(encoding="utf-8")),
        "q3_selected": json.loads(q3_selected_path.read_text(encoding="utf-8")),
        "q2_surface": json.loads(q2_surface_path.read_text(encoding="utf-8")),
        "q2_surface_protocol": json.loads(q2_surface_protocol_path.read_text(encoding="utf-8")),
        "q2_surface_validation": json.loads(q2_surface_validation_path.read_text(encoding="utf-8")),
        "frozen": json.loads(frozen_path.read_text(encoding="utf-8")),
        "source_paths": [
            annual_path,
            ROOT / "data/processed/team_delivery/pv_forecast.csv",
            ROOT / "analysis/team_delivery/pv_forecast_error.csv",
            ROOT / "analysis/team_delivery/intake_audit.json",
            q2_forecast_path,
            q2_margin_path,
            q3_path,
            q3_selected_path,
            q2_surface_path,
            q2_surface_protocol_path,
            q2_surface_validation_path,
            frozen_path,
            ROOT / "scripts/run_real_q2_forecast.py",
            ROOT / "scripts/run_strict_q3.py",
            ROOT / "src/q3/pv.py",
        ],
    }


def lag_errors(days: list, lag: int, field: str) -> np.ndarray:
    # Match the audited candidate evaluation range: 2025-01-08 through 2025-12-31.
    return np.concatenate(
        [
            np.asarray(getattr(days[index - lag], field + "_kwh"), dtype=float)
            - np.asarray(getattr(days[index], field + "_kwh"), dtype=float)
            for index in range(7, 365)
        ]
    )


def source_tolerance(values: np.ndarray) -> float:
    positive = np.asarray(values, dtype=float)
    positive = positive[np.isfinite(positive) & (positive > 0)]
    if not len(positive):
        return 1.0
    return float(max(1.0, 0.02 * np.median(positive)))


def state_share(error: np.ndarray, tolerance: float) -> dict[str, float]:
    error = np.asarray(error, dtype=float)
    n = len(error)
    return {
        "low": float(np.count_nonzero(error < -tolerance) / n),
        "near": float(np.count_nonzero(np.abs(error) <= tolerance) / n),
        "high": float(np.count_nonzero(error > tolerance) / n),
    }


def make_card(ax, x: float, y: float, w: float, h: float, title: str, body: str, accent: str) -> None:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=0.9,
        edgecolor=accent,
        facecolor=LIGHT,
        transform=ax.transAxes,
    )
    ax.add_patch(patch)
    ax.add_patch(
        FancyBboxPatch(
            (x, y + h - 0.012),
            w,
            0.012,
            boxstyle="round,pad=0,rounding_size=0.02",
            linewidth=0,
            facecolor=accent,
            transform=ax.transAxes,
        )
    )
    ax.text(x + 0.035, y + h - 0.055, title, transform=ax.transAxes,
            fontsize=9.6, fontweight="bold", color=NAVY, va="top")
    ax.text(
        x + 0.035,
        y + h - 0.115,
        textwrap.fill(body, width=26, break_long_words=False, break_on_hyphens=False),
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK,
        va="top",
        linespacing=1.45,
    )


def save_figure(fig: plt.Figure, stem: str) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [OUT / f"{stem}.pdf", OUT / f"{stem}.svg", OUT / f"{stem}.png"]
    fig.savefig(paths[0], bbox_inches="tight", facecolor="white")
    fig.savefig(paths[1], bbox_inches="tight", facecolor="white")
    fig.savefig(paths[2], dpi=360, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def build_prediction_consistency(context: dict) -> tuple[list[Path], Path]:
    days = context["days"]
    q2_summary = context["q2_forecast"]["scenarios"]["0"]["summary"]
    q2_margin = context["q2_margin"]["strategies"]["B2"]
    pv_rows = context["pv_error_rows"]

    load_yesterday = lag_errors(days, 1, "load")
    load_last_week = lag_errors(days, 7, "load")
    pv_by_issue: dict[str, np.ndarray] = {label: [] for label in ISSUE_LABELS}
    pv_actual_by_issue: dict[str, np.ndarray] = {label: [] for label in ISSUE_LABELS}
    for row in pv_rows:
        label = row["issue_time"].zfill(4) if len(row["issue_time"]) == 4 else row["issue_time"]
        # The audited file uses 0:00, 6:00, 12:00 and 18:00.
        hour = int(row["issue_time"].split(":")[0])
        label = f"{hour:02d}:00"
        pv_by_issue[label].append(float(row["error"]))
        pv_actual_by_issue[label].append(float(row["pv_actual_kw"]))
    pv_by_issue = {key: np.asarray(value, dtype=float) for key, value in pv_by_issue.items()}
    pv_actual_by_issue = {key: np.asarray(value, dtype=float) for key, value in pv_actual_by_issue.items()}

    load_values = np.concatenate([np.asarray(day.load_kwh, dtype=float) for day in days])
    pv_values = np.concatenate(list(pv_actual_by_issue.values()))
    load_tol = source_tolerance(load_values)
    pv_tol = source_tolerance(pv_values)

    fig = plt.figure(figsize=(17.2, 10.4))
    gs = fig.add_gridspec(2, 4, height_ratios=[1.18, 1.02], wspace=0.34, hspace=0.48)
    agrid = gs[0, :2].subgridspec(1, 2, wspace=0.34)
    ax_load = fig.add_subplot(agrid[0, 0])
    ax_pv = fig.add_subplot(agrid[0, 1])
    panel_label(ax_load, "A")
    ax_load.set_title("历史滞后基线", fontsize=10.5, loc="left", pad=10)
    ax_pv.set_title("发布式光伏预测", fontsize=10.5, loc="left", pad=10)

    for values, color, label in (
        (load_yesterday, CORAL, "前一日"),
        (load_last_week, NAVY, "前七日"),
    ):
        lo, hi = np.quantile(values, [0.01, 0.99])
        bins = np.linspace(lo, hi, 38)
        ax_load.hist(values, bins=bins, density=True, histtype="step", color=color,
                     linewidth=1.6, label=f"{label}  n={len(values):,}")
    ax_load.axvline(0, color=GRID, linewidth=0.8)
    ax_load.set_xlabel("负荷残差 / kWh per slot")
    ax_load.set_ylabel("样本密度")
    ax_load.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax_load.text(0.02, 0.02, "误差 = 预测 − 实际\n显示中央 98% 区间",
                 transform=ax_load.transAxes, fontsize=7.2, color=MUTED, va="bottom")
    strip_spines(ax_load, "y")

    pv_colors = [BLUE, NAVY, ORANGE, CORAL]
    for color, label in zip(pv_colors, ISSUE_LABELS):
        values = pv_by_issue[label]
        lo, hi = np.quantile(values, [0.01, 0.99])
        bins = np.linspace(lo, hi, 38)
        ax_pv.hist(values, bins=bins, density=True, histtype="step", color=color,
                   linewidth=1.35, label=f"{label}  n={len(values):,}")
    ax_pv.axvline(0, color=GRID, linewidth=0.8)
    ax_pv.set_xlabel("光伏残差 / kW")
    ax_pv.legend(frameon=False, fontsize=7.0, loc="upper left")
    ax_pv.text(0.02, 0.02, "真实发布记录；不构造流宽\n同样显示中央 98% 区间",
               transform=ax_pv.transAxes, fontsize=7.2, color=MUTED, va="bottom")
    strip_spines(ax_pv, "y")

    ax_state = fig.add_subplot(gs[0, 2:])
    panel_label(ax_state, "B")
    ax_state.set_title("误差状态比例：方向性证据", fontsize=10.5, loc="left", pad=10)
    sources = ["负荷\n前一日", "负荷\n前七日"] + [f"光伏\n{x}" for x in ISSUE_LABELS]
    errors = [load_yesterday, load_last_week] + [pv_by_issue[label] for label in ISSUE_LABELS]
    tolerances = [load_tol, load_tol] + [pv_tol] * 4
    shares = [state_share(err, tol) for err, tol in zip(errors, tolerances)]
    x = np.arange(len(sources))
    bottom = np.zeros(len(sources))
    for key, color, label in (
        ("low", BLUE, "低估"),
        ("near", PALE_BLUE, "近似（±2%中位正值）"),
        ("high", ORANGE, "高估"),
    ):
        values = np.array([share[key] for share in shares])
        ax_state.bar(x, values, bottom=bottom, width=0.66, color=color,
                     edgecolor="white", linewidth=0.55, label=label)
        bottom += values
    ax_state.set_ylim(0, 1.03)
    ax_state.set_ylabel("样本比例")
    ax_state.set_xticks(x, sources, fontsize=8)
    ax_state.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0%}"))
    ax_state.legend(frameon=False, fontsize=7.2, ncol=3, loc="upper center",
                    bbox_to_anchor=(0.5, 1.01))
    ax_state.text(0.99, 0.02, f"容差：负荷 {load_tol:.1f} kWh/slot；光伏 {pv_tol:.1f} kW",
                  transform=ax_state.transAxes, fontsize=7.2, color=MUTED,
                  ha="right", va="bottom")
    strip_spines(ax_state, "y")

    cgrid = gs[1, :2].subgridspec(1, 2, wspace=0.38)
    ax_metric = fig.add_subplot(cgrid[0, 0])
    ax_issue = fig.add_subplot(cgrid[0, 1])
    panel_label(ax_metric, "C")
    ax_metric.set_title("候选输入的 MAE / RMSE", fontsize=10.5, loc="left", pad=10)
    metric_labels = ["负荷\n前一日", "负荷\n前七日", "光伏\n前一日", "光伏\n前七日"]
    mae = [
        q2_summary["yesterday"]["load"]["mae_kwh_per_slot"],
        q2_summary["last_week"]["load"]["mae_kwh_per_slot"],
        q2_summary["yesterday"]["pv"]["mae_kwh_per_slot"],
        q2_summary["last_week"]["pv"]["mae_kwh_per_slot"],
    ]
    rmse = [
        q2_summary["yesterday"]["load"]["rmse_kwh_per_slot"],
        q2_summary["last_week"]["load"]["rmse_kwh_per_slot"],
        q2_summary["yesterday"]["pv"]["rmse_kwh_per_slot"],
        q2_summary["last_week"]["pv"]["rmse_kwh_per_slot"],
    ]
    mx = max(rmse) * 1.18
    ax_metric.bar(np.arange(4) - 0.18, mae, width=0.34, color=[CORAL, NAVY, CORAL, NAVY],
                  alpha=0.88, label="MAE")
    ax_metric.bar(np.arange(4) + 0.18, rmse, width=0.34, color=[ORANGE, BLUE, ORANGE, BLUE],
                  alpha=0.75, label="RMSE")
    ax_metric.set_ylim(0, mx)
    ax_metric.set_xticks(np.arange(4), metric_labels, fontsize=7.5)
    ax_metric.set_ylabel("kWh per slot")
    ax_metric.legend(frameon=False, fontsize=7.5, loc="upper right")
    ax_metric.text(0.01, 0.98, "358 天 × 144 槽；与候选报告同口径",
                   transform=ax_metric.transAxes, fontsize=7.1, color=MUTED, va="top")
    strip_spines(ax_metric, "y")

    ax_issue.set_title("发布时刻的光伏误差", fontsize=10.5, loc="left", pad=10)
    issue_mae = [float(np.abs(pv_by_issue[label]).mean()) for label in ISSUE_LABELS]
    issue_rmse = [float(np.sqrt(np.mean(pv_by_issue[label] ** 2))) for label in ISSUE_LABELS]
    issue_x = np.arange(4)
    ax_issue.plot(issue_x, issue_mae, color=BLUE, marker="o", linewidth=2.0, label="MAE")
    ax_issue.plot(issue_x, issue_rmse, color=ORANGE, marker="o", linewidth=1.6,
                  linestyle="--", label="RMSE")
    ax_issue.set_xticks(issue_x, ISSUE_LABELS)
    ax_issue.set_ylabel("kW")
    ax_issue.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax_issue.text(0.99, 0.02, "逐小时发布误差；非调度成本",
                  transform=ax_issue.transAxes, fontsize=7.1, color=MUTED,
                  ha="right", va="bottom")
    strip_spines(ax_issue, "y")

    ax_cards = fig.add_subplot(gs[1, 2:])
    panel_label(ax_cards, "D")
    ax_cards.axis("off")
    ax_cards.set_title("从信息质量到调度输入：证据卡片", fontsize=10.5, loc="left", pad=4)
    load_y_mae = q2_summary["yesterday"]["load"]["mae_kwh_per_slot"]
    load_w_mae = q2_summary["last_week"]["load"]["mae_kwh_per_slot"]
    pv_y_mae = q2_summary["yesterday"]["pv"]["mae_kwh_per_slot"]
    pv_w_mae = q2_summary["last_week"]["pv"]["mae_kwh_per_slot"]
    load_improvement = 100 * (load_y_mae - load_w_mae) / load_y_mae
    pv_change = 100 * (pv_w_mae - pv_y_mae) / pv_y_mae
    make_card(
        ax_cards,
        0.02,
        0.53,
        0.46,
        0.34,
        "当前 Q2 输入选择",
        "负荷：前七日；光伏：前一日。两者都完成 358/358 天评分；整日可用是候选假设。",
        BLUE,
    )
    make_card(
        ax_cards,
        0.52,
        0.53,
        0.46,
        0.34,
        "误差改善不是同向的",
        f"负荷 MAE {load_y_mae:.2f} → {load_w_mae:.2f}（{load_improvement:.1f}%↓）；光伏前七日比前一日 {pv_change:.1f}%↑。",
        ORANGE,
    )
    make_card(
        ax_cards,
        0.02,
        0.10,
        0.46,
        0.34,
        "真实调度落点",
        f"Q2 B2（2025-02—12）总费 ¥{q2_margin['costs']['total_yuan']:,.2f}；应急购电 ¥{q2_margin['costs']['emergency_yuan']:,.2f}。",
        GREEN,
    )
    make_card(
        ax_cards,
        0.52,
        0.10,
        0.46,
        0.34,
        "边界必须保留",
        "误差证据支持输入选择，不等于执行可行性证明；Oracle 仅作下界，Q4 价格提前可知仍是候选假设。",
        CORAL,
    )

    fig.suptitle("图 1｜多源预测一致性与调度输入可信度", x=0.055, y=0.965,
                 ha="left", fontsize=18, fontweight="bold", color=NAVY)
    fig.text(0.055, 0.932,
             "信息质量改善通过真实误差统计进入调度输入；原始记录没有状态转移标签，因此不绘制装饰性 Sankey。",
             fontsize=9.4, color=MUTED)
    fig.text(0.055, 0.018,
             "数据口径：interval-end-v1；误差均为预测 − 实际。图中不含未来观测、Oracle 方案或随机模拟数据。",
             fontsize=8, color=MUTED)
    fig.subplots_adjust(left=0.055, right=0.975, top=0.88, bottom=0.075)

    output_paths = save_figure(fig, "fig01_prediction_consistency")
    data_path = OUT / "fig01_prediction_consistency_data.json"
    write_json(
        data_path,
        {
            "figure": "fig01_prediction_consistency",
            "seed": SEED,
            "sankey": {
                "status": "not_implemented",
                "reason": "当前真实记录没有可回溯的状态转移/流量标签；改用真实误差分布。",
            },
            "error_definition": "forecast minus actual",
            "tolerance_rule": "每类信号使用正值实际样本中位数的 2%，最小 1 个单位；仅用于误差状态分箱。",
            "tolerance": {"load_kwh_per_slot": load_tol, "pv_kw": pv_tol},
            "sample_counts": {
                "load_yesterday": int(len(load_yesterday)),
                "load_last_week": int(len(load_last_week)),
                **{f"pv_{label}": int(len(pv_by_issue[label])) for label in ISSUE_LABELS},
            },
            "load_baselines": {
                "yesterday": {"mae_kwh_per_slot": q2_summary["yesterday"]["load"]["mae_kwh_per_slot"],
                              "rmse_kwh_per_slot": q2_summary["yesterday"]["load"]["rmse_kwh_per_slot"]},
                "last_week": {"mae_kwh_per_slot": q2_summary["last_week"]["load"]["mae_kwh_per_slot"],
                              "rmse_kwh_per_slot": q2_summary["last_week"]["load"]["rmse_kwh_per_slot"]},
            },
            "pv_baselines": {
                "yesterday": {"mae_kwh_per_slot": q2_summary["yesterday"]["pv"]["mae_kwh_per_slot"],
                              "rmse_kwh_per_slot": q2_summary["yesterday"]["pv"]["rmse_kwh_per_slot"]},
                "last_week": {"mae_kwh_per_slot": q2_summary["last_week"]["pv"]["mae_kwh_per_slot"],
                              "rmse_kwh_per_slot": q2_summary["last_week"]["pv"]["rmse_kwh_per_slot"]},
            },
            "published_pv_by_issue": {
                label: {
                    "n": len(pv_by_issue[label]),
                    "mae_kw": float(np.abs(pv_by_issue[label]).mean()),
                    "rmse_kw": float(np.sqrt(np.mean(pv_by_issue[label] ** 2))),
                    "state_share": state_share(pv_by_issue[label], pv_tol),
                }
                for label in ISSUE_LABELS
            },
            "current_dispatch_evidence": {
                "q2_B2_total_yuan": q2_margin["costs"]["total_yuan"],
                "q2_B2_emergency_yuan": q2_margin["costs"]["emergency_yuan"],
                "evaluation_days": q2_margin["days"],
            },
            "visual_boundary": "D 卡片只引用 current candidate evidence；Q4 price-known assumption is not promoted to a verified fact.",
        },
    )
    return output_paths, data_path


def snapshot_commitment(selected: dict, snapshot_slot: int) -> np.ndarray:
    commitment = np.asarray(selected["planned_G"], dtype=float).copy()
    for revision in selected["revisions"]:
        if int(revision["first_slot"]) <= snapshot_slot:
            start = int(revision["first_slot"])
            commitment[start:] = np.asarray(revision["new_remaining_kwh"], dtype=float)
    return commitment


def draw_feedback_loop(fig: plt.Figure) -> None:
    ax = fig.add_axes([0.075, 0.045, 0.86, 0.15])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.0, 0.94, "反馈闭环（严格 Q3 fresh-update 对照）", fontsize=10.5,
            color=NAVY, fontweight="bold", va="top")

    labels = ["实际观测值", "状态估计", "优化控制器", "控制输入", "新状态", "新观测值"]
    colors = [BLUE, BLUE, ORANGE, CORAL, GREEN, BLUE]
    xs = np.linspace(0.02, 0.78, len(labels))
    y, w, h = 0.34, 0.14, 0.31
    for x, label, color in zip(xs, labels, colors):
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.012,rounding_size=0.025",
                linewidth=1.0,
                edgecolor=color,
                facecolor="white",
            )
        )
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
                fontsize=9, color=INK, fontweight="bold")

    for left, right in zip(xs[:-1], xs[1:]):
        ax.annotate(
            "",
            xy=(right - 0.008, y + h / 2),
            xytext=(left + w + 0.008, y + h / 2),
            arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 1.0},
        )

    # A PathPatch makes the return edge explicit instead of implying a one-way pipeline.
    path = MplPath(
        [(xs[-1] + w / 2, y), (xs[-1] + w / 2, 0.10), (xs[0] + w / 2, 0.10),
         (xs[0] + w / 2, y)],
        [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4],
    )
    ax.add_patch(PathPatch(path, facecolor="none", edgecolor=MUTED, lw=1.0,
                           linestyle=(0, (4, 2))))
    ax.add_patch(FancyArrowPatch((xs[0] + w / 2, 0.19), (xs[0] + w / 2, y),
                                 arrowstyle="-|>", mutation_scale=12,
                                 linewidth=1.0, color=MUTED))
    ax.text(0.5, 0.02, "新观测值在下一个更新时刻回流；历史动作保持锁定，只有滚动窗口内的未来动作可变。",
            ha="center", va="bottom", fontsize=8, color=MUTED)


def build_rolling_mpc(context: dict) -> tuple[list[Path], Path]:
    selected = context["q3_selected"]["margin_fresh"]["2025-06-21"]
    days = context["days"]
    day_index = next(index for index, day in enumerate(days) if str(day.day) == "2025-06-21")
    actual = days[day_index]
    load_forecast = np.asarray(days[day_index - 7].load_kwh, dtype=float)
    correction = np.asarray(selected["margin"]["correction_kwh"], dtype=float)
    load_forecast = load_forecast + correction
    actual_net = np.asarray(actual.load_kwh, dtype=float) - np.asarray(actual.pv_kwh, dtype=float)
    published = context["published"]
    issue = midnight(actual.day)
    pv_forecast = {
        hour: published[issue + timedelta(hours=hour)].energy(
            decision_time=issue + timedelta(hours=hour), method="linear"
        )
        for hour in ISSUE_HOURS
    }
    final_g = np.asarray(selected["schedule"]["G"], dtype=float)
    x = (np.arange(144, dtype=float) + 1.0) / 6.0
    snapshot_hours = ISSUE_HOURS
    snapshot_slots = [hour * 6 for hour in snapshot_hours]

    fig = plt.figure(figsize=(17.2, 10.6))
    gs = fig.add_gridspec(1, 4, left=0.055, right=0.98, top=0.83, bottom=0.265,
                          wspace=0.28)
    axes = [fig.add_subplot(gs[0, i]) for i in range(4)]
    history_line = Line2D([0], [0], color=NAVY, linewidth=2.0, label="已执行实际净负荷")
    forecast_line = Line2D([0], [0], color=BLUE, linewidth=1.8, linestyle=(0, (4, 2)),
                           label="当前预测净负荷")
    plan_line = Line2D([0], [0], color=ORANGE, linewidth=1.8, label="当前优化购电")
    locked_line = Line2D([0], [0], color=MUTED, linewidth=1.3, label="历史购电（锁定）")

    for panel_index, (ax, hour, slot) in enumerate(zip(axes, snapshot_hours, snapshot_slots)):
        commitment = snapshot_commitment(selected, slot)
        forecast_net = load_forecast - np.asarray(pv_forecast[hour], dtype=float)
        history_n = slot
        ax.axvspan(0, hour, color=NAVY, alpha=0.045, linewidth=0)
        ax.axvspan(hour, 24, color=BLUE, alpha=0.065, linewidth=0)
        if history_n:
            ax.plot(x[:history_n], actual_net[:history_n], color=NAVY, linewidth=1.9,
                    solid_capstyle="round")
            ax.step(x[:history_n], final_g[:history_n], where="post", color=MUTED,
                    linewidth=1.25, alpha=0.95)
        ax.plot(x[history_n:], forecast_net[history_n:], color=BLUE, linewidth=1.65,
                linestyle=(0, (4, 2)))
        ax.step(x[history_n:], commitment[history_n:], where="post", color=ORANGE,
                linewidth=1.65)
        ax.axvline(hour, color=CORAL, linewidth=1.0, linestyle=(0, (2, 2)))
        ax.text(hour + 0.25, 0.97, f"{hour:02d}:00 更新", transform=ax.get_xaxis_transform(),
                fontsize=7.6, color=CORAL, va="top")
        ax.text(0.03, 0.04, "历史锁定" if hour else "尚未执行",
                transform=ax.transAxes, fontsize=7.5, color=MUTED, va="bottom")
        ax.text(0.97, 0.04, "滚动窗口",
                transform=ax.transAxes, fontsize=7.5, color=BLUE, va="bottom", ha="right")
        ax.set_xlim(0, 24)
        visible = np.concatenate([
            actual_net[:history_n],
            final_g[:history_n],
            forecast_net[history_n:],
            commitment[history_n:],
        ])
        lo, hi = float(np.min(visible)), float(np.max(visible))
        pad = max(30.0, 0.08 * (hi - lo))
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_xticks([0, 6, 12, 18, 24], ["0", "6", "12", "18", "24"])
        ax.set_title(f"t = {hour:02d}:00", fontsize=11, loc="left", pad=8)
        ax.set_xlabel("时刻 / h")
        if panel_index == 0:
            ax.set_ylabel("能量 / kWh per slot")
        strip_spines(ax, "y")
        ax.tick_params(labelsize=7.5)
        panel_label(ax, chr(ord("A") + panel_index), x=-0.12, y=1.04)

    fig.suptitle("图 2｜滚动优化窗口与状态反馈闭环", x=0.055, y=0.955,
                 ha="left", fontsize=18, fontweight="bold", color=NAVY)
    fig.text(0.055, 0.919,
             "同一真实日的四个决策快照：过去的实际动作保持不变，更新后的预测只影响当前滚动窗口。",
             fontsize=9.4, color=MUTED)
    fig.legend(handles=[history_line, forecast_line, plan_line, locked_line],
               frameon=False, fontsize=7.3, loc="upper left", ncol=4,
               bbox_to_anchor=(0.055, 0.895), handlelength=2.2, columnspacing=1.4)
    fig.text(0.055, 0.242,
             "样例：2025-06-21 · Q3 margin_fresh 严格滚动更新对照（3 次更新；当前 Q3 主候选为 margin_zero，故本图不是主方案声明）。",
             fontsize=8.2, color=CORAL)
    draw_feedback_loop(fig)

    output_paths = save_figure(fig, "fig02_rolling_mpc_feedback")
    data_path = OUT / "fig02_rolling_mpc_feedback_data.json"
    history_lock_passed = True
    snapshots = []
    for hour, slot in zip(snapshot_hours, snapshot_slots):
        commitment = snapshot_commitment(selected, slot)
        if not np.allclose(commitment[:slot], final_g[:slot], rtol=0, atol=1e-9):
            history_lock_passed = False
        snapshots.append(
            {
                "snapshot_hour": hour,
                "update_slot": slot,
                "history_slots_rendered": slot,
                "rolling_window_slots": 144 - slot,
                "forecast_issue_time": (issue + timedelta(hours=hour)).isoformat(),
                "forecast_source": "published PV forecast via src.q3.pv.PublishedPV.energy(linear) + last-week load + frozen Q2 margin correction",
                "future_actual_rendered": False,
                "current_commitment_future_sum_kwh": float(np.sum(commitment[slot:])),
            }
        )
    write_json(
        data_path,
        {
            "figure": "fig02_rolling_mpc_feedback",
            "seed": SEED,
            "sample_day": "2025-06-21",
            "strategy": "margin_fresh",
            "is_contrast_not_mainline": True,
            "current_q3_mainline": "margin_zero",
            "time_contract": "interval-end-v1",
            "updates": [6, 12, 18],
            "revision_count": len(selected["revisions"]),
            "physical_diagnostics_passed": bool(selected["diagnostics"]["passed"]),
            "history_lock_passed": history_lock_passed,
            "snapshots": snapshots,
            "revision_evidence": [
                {
                    "issue_time": revision["issue_time"],
                    "first_slot": revision["first_slot"],
                    "increase_kwh": revision["increase_kwh"],
                    "decrease_kwh": revision["decrease_kwh"],
                    "incremental_cost_yuan": revision["incremental_cost_yuan"],
                    "diagnostics_passed": revision["diagnostics"]["passed"],
                }
                for revision in selected["revisions"]
            ],
            "render_boundary": "每个快照只绘制历史实际观测和当时可用的预测；没有绘制该快照之后的实际值。",
        },
    )
    return output_paths, data_path


def build_economic_sensitivity(context: dict) -> tuple[list[Path], Path]:
    surface_result = context["q2_surface"]
    scores = [
        {key: float(row[key]) for key in ("tau", "scale", "planned_yuan", "emergency_yuan", "total_yuan")}
        for row in surface_result["scores"]
    ]
    taus = sorted({row["tau"] for row in scores})
    scales = sorted({row["scale"] for row in scores})
    z = np.array(
        [
            [next(row["total_yuan"] for row in scores
                  if math.isclose(row["tau"], tau) and math.isclose(row["scale"], scale))
             for tau in taus]
            for scale in scales
        ],
        dtype=float,
    )
    tau_profile = sorted(
        [row for row in scores if math.isclose(row["scale"], 1.0)],
        key=lambda row: row["tau"],
    )
    scale_profile = sorted(
        [row for row in scores if math.isclose(row["tau"], 0.8)],
        key=lambda row: row["scale"],
    )
    global_min = min(scores, key=lambda row: row["total_yuan"])
    original = next(row for row in scores
                    if math.isclose(row["tau"], 0.8) and math.isclose(row["scale"], 1.0))
    tau_profile_min = min(tau_profile, key=lambda row: row["total_yuan"])
    scale_profile_min = min(scale_profile, key=lambda row: row["total_yuan"])
    tau_span = float(max(row["total_yuan"] for row in tau_profile)
                      - min(row["total_yuan"] for row in tau_profile))
    scale_span = float(max(row["total_yuan"] for row in scale_profile)
                        - min(row["total_yuan"] for row in scale_profile))
    q2_b2 = context["q2_margin"]["strategies"]["B2"]

    fig = plt.figure(figsize=(17.2, 10.4))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.1, 0.9], height_ratios=[1.08, 0.92],
                          wspace=0.30, hspace=0.42)
    ax_surface = fig.add_subplot(gs[0, 0], projection="3d")
    panel_label_3d(ax_surface, "A")
    T, S = np.meshgrid(taus, scales)
    cmap = LinearSegmentedColormap.from_list("navy_orange", [PALE_BLUE, BLUE, NAVY, ORANGE])
    z_span = float(z.max() - z.min())
    z_offset = float(z.min() - max(1.0, 0.08 * z_span))
    ax_surface.plot_surface(T, S, z, cmap=cmap, edgecolor="white", linewidth=0.42,
                            antialiased=True, alpha=0.93, rcount=len(scales), ccount=len(taus))
    ax_surface.contour(T, S, z, zdir="z", offset=z_offset, levels=9,
                       colors=[NAVY, BLUE, ORANGE], linewidths=0.65, alpha=0.8)
    ax_surface.scatter([original["tau"]], [original["scale"]], [original["total_yuan"]],
                       s=140, marker="*", color=CORAL, edgecolor="white", linewidth=0.7,
                       depthshade=False)
    ax_surface.scatter([global_min["tau"]], [global_min["scale"]], [global_min["total_yuan"]],
                       s=95, marker="*", color=GREEN, edgecolor="white", linewidth=0.7,
                       depthshade=False)
    ax_surface.text(original["tau"], original["scale"], original["total_yuan"] + 0.04 * z_span,
                    "冻结候选", color=CORAL, fontsize=8)
    ax_surface.text(global_min["tau"], global_min["scale"], global_min["total_yuan"] - 0.08 * z_span,
                    "网格最低", color=GREEN, fontsize=8)
    ax_surface.set_xlabel("τ", labelpad=6)
    ax_surface.set_ylabel("scale", labelpad=6)
    ax_surface.set_zlabel("总费用 / 元", labelpad=7)
    ax_surface.set_zlim(z_offset, float(z.max() + 0.04 * z_span))
    ax_surface.view_init(elev=26, azim=50)
    try:
        ax_surface.set_box_aspect((1.15, 1.0, 0.72))
    except AttributeError:
        pass
    ax_surface.set_title("81 个真实节点；无平滑插值", fontsize=10.5, loc="left", pad=4)
    ax_surface.text2D(0.03, -0.10, "视角固定为凹面朝向读者；底部为等高线投影",
                      transform=ax_surface.transAxes, color=MUTED, fontsize=7.7)

    bgrid = gs[0, 1].subgridspec(2, 1, hspace=0.46)
    ax_tau = fig.add_subplot(bgrid[0, 0])
    ax_scale = fig.add_subplot(bgrid[1, 0])
    panel_label(ax_tau, "B")
    ax_tau.set_title("局部剖面：固定 scale = 1.00", fontsize=10.2, loc="left", pad=8)
    ax_tau.plot([row["tau"] for row in tau_profile], [row["total_yuan"] for row in tau_profile], color=NAVY,
                marker="o", linewidth=1.8, markersize=4.5)
    ax_tau.scatter([original["tau"]], [original["total_yuan"]], marker="*", s=100,
                   color=CORAL, edgecolor="white", zorder=3)
    ax_tau.scatter([tau_profile_min["tau"]], [tau_profile_min["total_yuan"]], marker="*", s=78,
                   color=GREEN, edgecolor="white", zorder=3)
    ax_tau.set_xlabel("τ")
    ax_tau.set_ylabel("总费用 / 元")
    ax_tau.text(0.98, 0.04, f"跨度 ¥{tau_span:,.0f}", transform=ax_tau.transAxes,
                ha="right", va="bottom", fontsize=7.6, color=MUTED)
    strip_spines(ax_tau, "y")

    ax_scale.set_title("局部剖面：固定 τ = 0.80", fontsize=10.2, loc="left", pad=8)
    ax_scale.plot([row["scale"] for row in scale_profile], [row["total_yuan"] for row in scale_profile], color=ORANGE,
                  marker="o", linewidth=1.8, markersize=4.5)
    ax_scale.scatter([original["scale"]], [original["total_yuan"]], marker="*", s=100,
                     color=CORAL, edgecolor="white", zorder=3)
    ax_scale.scatter([scale_profile_min["scale"]], [scale_profile_min["total_yuan"]], marker="*", s=78,
                     color=GREEN, edgecolor="white", zorder=3)
    ax_scale.set_xlabel("scale")
    ax_scale.set_ylabel("总费用 / 元")
    ax_scale.text(0.98, 0.04, f"跨度 ¥{scale_span:,.0f}", transform=ax_scale.transAxes,
                  ha="right", va="bottom", fontsize=7.6, color=MUTED)
    strip_spines(ax_scale, "y")

    ax_missing = fig.add_subplot(gs[1, 0])
    panel_label(ax_missing, "C")
    ax_missing.axis("off")
    ax_missing.add_patch(FancyBboxPatch(
        (0.015, 0.04), 0.97, 0.86, boxstyle="round,pad=0.02,rounding_size=0.018",
        transform=ax_missing.transAxes, facecolor=LIGHT, edgecolor=CORAL, linewidth=1.0,
    ))
    ax_missing.text(0.06, 0.78, "时间 × 参数热力图：数据不足 / 未实现",
                    transform=ax_missing.transAxes, fontsize=12, color=CORAL,
                    fontweight="bold", va="top")
    ax_missing.text(
        0.06,
        0.61,
        "当前真实实验只有同一段时间窗口的参数网格：\n"
        "81 节点 × 2025-01-15—01-31 总费用。\n\n"
        "缺少：同一 (τ, scale) 网格在全年或逐月的真实重算。\n"
        "因此不画伪造的时间×参数热力图，也不对 81 个节点做高密度插值。",
        transform=ax_missing.transAxes,
        fontsize=9.1,
        color=INK,
        va="top",
        linespacing=1.6,
    )
    ax_missing.text(0.06, 0.10, "这是数据边界，不是模型结论。",
                    transform=ax_missing.transAxes, fontsize=8.2, color=MUTED)

    ax_cards = fig.add_subplot(gs[1, 1])
    panel_label(ax_cards, "D")
    ax_cards.axis("off")
    ax_cards.set_title("经济解释与适用边界", fontsize=10.5, loc="left", pad=4)
    make_card(ax_cards, 0.02, 0.53, 0.46, 0.34, "最敏感参数（局部）",
              f"固定 scale=1.00 时 τ 剖面跨度 ¥{tau_span:,.2f}；固定 τ=0.80 时 scale 跨度 ¥{scale_span:,.2f}。局部网格内 τ 变化更大。",
              NAVY)
    make_card(ax_cards, 0.52, 0.53, 0.46, 0.34, "网格最低点",
              f"(τ, scale)=({global_min['tau']:.2f}, {global_min['scale']:.3g})；17 天总费 ¥{global_min['total_yuan']:,.2f}。这是观测网格最低，不是连续域证明。",
              GREEN)
    delta = float(global_min["total_yuan"] - original["total_yuan"])
    make_card(ax_cards, 0.02, 0.10, 0.46, 0.34, "冻结候选与局部拐点",
              f"冻结候选 (0.80, 1.00) 为 ¥{original['total_yuan']:,.2f}；网格最低差值 ¥{delta:,.2f}。单变量剖面最低点约 τ={tau_profile_min['tau']:.2f}、scale={scale_profile_min['scale']:.3g}。",
              ORANGE)
    make_card(ax_cards, 0.52, 0.10, 0.46, 0.34, "适用边界",
              f"参数网格仅用于 1 月开发窗口描述；Q2 B2 的 2025-02—12 总费为 ¥{q2_b2['costs']['total_yuan']:,.2f}，没有用全年结果回调网格。",
              CORAL)

    fig.suptitle("图 3｜经济调度敏感性与关键结论", x=0.055, y=0.965,
                 ha="left", fontsize=18, fontweight="bold", color=NAVY)
    fig.text(0.055, 0.932,
             "曲面只连接真实测量节点；等高线用于阅读，C 面明确保留当前实验的时间维度缺口。",
             fontsize=9.4, color=MUTED)
    fig.text(0.055, 0.018,
             "数据口径：q2_january_surface_v1 · 9×9 = 81 节点 · 17 天 × 1377 次回放；无随机补点。",
             fontsize=8, color=MUTED)

    output_paths = save_figure(fig, "fig03_economic_sensitivity")
    data_path = OUT / "fig03_economic_sensitivity_data.json"
    write_json(
        data_path,
        {
            "figure": "fig03_economic_sensitivity",
            "seed": SEED,
            "grid_nodes": len(scores),
            "day_replays": surface_result["days_replayed"],
            "scoring_window_days": 17,
            "interpolation": "none; surface connects measured 9x9 nodes only",
            "view": {"elev": 26, "azim": 50, "projection": "orthographic-like Matplotlib 3D"},
            "global_min": global_min,
            "original_frozen_candidate": original,
            "profiles": {
                "fixed_scale_1.0": tau_profile,
                "fixed_tau_0.8": scale_profile,
                "tau_span_yuan": tau_span,
                "scale_span_yuan": scale_span,
                "tau_profile_min": tau_profile_min,
                "scale_profile_min": scale_profile_min,
            },
            "grid": sorted(scores, key=lambda row: (row["scale"], row["tau"])),
            "missing_panel": {
                "status": "data_insufficient",
                "requested": "time x parameter heatmap",
                "reason": "没有同一参数网格在逐月/全年重算结果；现有网格只有 2025-01-15—01-31 总费用。",
            },
            "current_mainline_reference": {
                "q2_B2_total_yuan": q2_b2["costs"]["total_yuan"],
                "q2_B2_days": q2_b2["days"],
            },
        },
    )
    return output_paths, data_path


def build_montage(image_paths: list[Path]) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(17.2, 22.2))
    for ax, path, title in zip(
        axes,
        image_paths,
        ("图 1 预测一致性", "图 2 滚动 MPC", "图 3 经济敏感性"),
    ):
        image = plt.imread(path)
        ax.imshow(image)
        ax.axis("off")
        ax.set_title(title, loc="left", fontsize=12, color=NAVY, pad=8)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01, hspace=0.08)
    path = OUT / "advanced_figures_montage.png"
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def write_manifest(context: dict, output_paths: list[Path], data_paths: list[Path], montage: Path) -> Path:
    all_outputs = output_paths + data_paths + [montage]
    readme = OUT / "README.md"
    if readme.exists():
        all_outputs.append(readme)
    source_map = {rel(path): sha256(path) for path in context["source_paths"]}
    output_map = {path.name: sha256(path) for path in all_outputs}
    manifest_path = OUT / "manifest.json"
    write_json(
        manifest_path,
        {
            "package": "v4_advanced",
            "status": "candidate_only",
            "seed": SEED,
            "time_contract": "interval-end-v1",
            "paper_inclusion": False,
            "source_sha256": source_map,
            "outputs_sha256": output_map,
            "figures": {
                "fig01": "fig01_prediction_consistency",
                "fig02": "fig02_rolling_mpc_feedback",
                "fig03": "fig03_economic_sensitivity",
            },
            "reproducible_command": ".venv/bin/python scripts/paper/build_advanced_figures.py",
            "boundaries": [
                "当前 v4 只保留在 deliverables/candidate_figures/v4_advanced/，未写入 paper/。",
                "没有把 legacy_excel/ 或旧 outputs/ 纳入当前主线。",
                "Q4 价格提前可知仍为候选假设；Oracle 不作为可执行方案。",
            ],
        },
    )
    return manifest_path


def main() -> None:
    font_name = configure_style()
    OUT.mkdir(parents=True, exist_ok=True)
    context = read_context()
    source_before = {path: sha256(path) for path in context["source_paths"]}

    fig1_paths, fig1_data = build_prediction_consistency(context)
    fig2_paths, fig2_data = build_rolling_mpc(context)
    fig3_paths, fig3_data = build_economic_sensitivity(context)
    png_paths = [OUT / "fig01_prediction_consistency.png",
                 OUT / "fig02_rolling_mpc_feedback.png",
                 OUT / "fig03_economic_sensitivity.png"]
    montage = build_montage(png_paths)

    source_after = {path: sha256(path) for path in context["source_paths"]}
    if source_before != source_after:
        raise RuntimeError("An audited input changed during figure generation")
    manifest = write_manifest(
        context,
        fig1_paths + fig2_paths + fig3_paths,
        [fig1_data, fig2_data, fig3_data],
        montage,
    )
    print(json.dumps({
        "status": "built",
        "font": font_name,
        "directory": str(OUT),
        "figures": [path.name for path in fig1_paths + fig2_paths + fig3_paths],
        "data": [fig1_data.name, fig2_data.name, fig3_data.name],
        "montage": montage.name,
        "manifest": manifest.name,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
