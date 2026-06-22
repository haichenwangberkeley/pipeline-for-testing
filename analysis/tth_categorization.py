from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.common import ensure_dir, utcnow_iso, write_json
from analysis.top_categorization import CATEGORY_ORDER


CATEGORIES = [*CATEGORY_ORDER, "unassigned"]
SIGNAL_PROCESSES = {"ttH", "tH"}
RESONANT_BACKGROUND_PROCESSES = {"ggH", "VBF", "WH", "ZH", "ggZH"}
COMPONENT_ORDER = ["topH_signal", "resonant_higgs_background", "NTI_continuum_proxy"]
COMPONENT_LABELS = {
    "topH_signal": "ttH+tH signal",
    "resonant_higgs_background": "resonant Higgs background",
    "NTI_continuum_proxy": "NTI continuum proxy",
}
COMPONENT_COLORS = {
    "topH_signal": "#005f73",
    "resonant_higgs_background": "#0a9396",
    "NTI_continuum_proxy": "#ca6702",
}
MASS_BINS = np.linspace(105.0, 160.0, 56)
SCORE_BINS = np.linspace(0.0, 1.0, 41)
MIN_CATEGORY_BACKGROUND_YIELD_36FB = 0.8


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _as_float_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").astype(float)


def _sumw2(weights: pd.Series | np.ndarray) -> float:
    values = np.asarray(weights, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.sum(values * values))


def _effective_events(sumw: float, sumw2: float) -> float:
    if sumw2 <= 0.0:
        return 0.0
    return float(sumw * sumw / sumw2)


def _asimov_z(signal: float, background: float) -> float:
    signal = float(signal)
    background = float(background)
    if signal <= 0.0 or background <= 0.0:
        return 0.0
    value = 2.0 * ((signal + background) * math.log1p(signal / background) - signal)
    return math.sqrt(max(value, 0.0))


def _component_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    process = frame["process"].astype(str)
    is_data = process == "data"
    is_ti = _bool_series(frame["is_ti_diphoton"])
    is_nti = _bool_series(frame["is_nti_diphoton"])
    in_signal_window = _bool_series(frame["in_mgg_123_127"])
    in_sideband = _bool_series(frame["in_mgg_sideband_105_120_130_160"])
    in_visible_mass = _bool_series(frame["in_mgg_105_160"]) if "in_mgg_105_160" in frame else frame["m_gammagamma"].between(105.0, 160.0)

    return {
        "topH_signal": process.isin(SIGNAL_PROCESSES) & is_ti & in_signal_window,
        "resonant_higgs_background": process.isin(RESONANT_BACKGROUND_PROCESSES) & is_ti & in_signal_window,
        "NTI_continuum_proxy": is_data & is_nti & in_sideband,
        "topH_signal_control_shape": process.isin(SIGNAL_PROCESSES) & is_ti & in_visible_mass,
        "resonant_higgs_background_control_shape": process.isin(RESONANT_BACKGROUND_PROCESSES) & is_ti & in_visible_mass,
        "NTI_continuum_proxy_control_shape": is_data & is_nti & in_visible_mass,
        "observed_ti_data_sideband": is_data & is_ti & in_sideband,
        "observed_ti_data_visible_mass": is_data & is_ti & in_visible_mass,
    }


def _component_weight(frame: pd.DataFrame, component: str) -> pd.Series:
    if component in {"topH_signal", "resonant_higgs_background"}:
        return _as_float_series(frame, "mc_event_weight_36fb")
    if component == "NTI_continuum_proxy":
        return _as_float_series(frame, "nti_continuum_proxy_weight")
    raise KeyError(component)


def _component_yield(frame: pd.DataFrame, mask: pd.Series, component: str) -> dict[str, Any]:
    subset = frame.loc[mask]
    weights = _component_weight(subset, component) if len(subset) else pd.Series(dtype=float)
    sumw = float(weights.sum()) if len(weights) else 0.0
    sumw2 = _sumw2(weights) if len(weights) else 0.0
    return {
        "raw_count": int(len(subset)),
        "yield_36fb": sumw,
        "stat_uncertainty_36fb": math.sqrt(sumw2),
        "sumw2": sumw2,
        "effective_events": _effective_events(sumw, sumw2),
    }


def _build_category_summary(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    masks = _component_masks(frame)
    records: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for category in CATEGORIES:
        category_mask = frame["assigned_category"].astype(str) == category
        component_payload: dict[str, Any] = {}
        for component in COMPONENT_ORDER:
            component_payload[component] = _component_yield(frame, category_mask & masks[component], component)
        observed_sideband = frame.loc[category_mask & masks["observed_ti_data_sideband"]]
        signal_yield = float(component_payload["topH_signal"]["yield_36fb"])
        resonant_yield = float(component_payload["resonant_higgs_background"]["yield_36fb"])
        continuum_yield = float(component_payload["NTI_continuum_proxy"]["yield_36fb"])
        background_yield = resonant_yield + continuum_yield
        total_model_yield = signal_yield + background_yield
        asimov_z = _asimov_z(signal_yield, background_yield)
        record = {
            "category": category,
            "raw_selected_events": int(category_mask.sum()),
            "signal_yield_36fb": signal_yield,
            "resonant_higgs_background_yield_36fb": resonant_yield,
            "nti_continuum_proxy_yield_36fb": continuum_yield,
            "total_background_yield_36fb": background_yield,
            "total_model_yield_36fb": total_model_yield,
            "s_over_b": signal_yield / background_yield if background_yield > 0.0 else 0.0,
            "s_over_sqrt_b": signal_yield / math.sqrt(background_yield) if background_yield > 0.0 else 0.0,
            "asimov_z": asimov_z,
            "observed_ti_data_signal_window_count": None,
            "observed_ti_data_signal_window_blinded": True,
            "observed_ti_data_sideband_count": int(len(observed_sideband)),
        }
        records.append(record)
        details[category] = {
            **record,
            "components": component_payload,
        }
    summary = pd.DataFrame.from_records(records)
    return summary, details


def _apply_min_background_requirement(
    frame: pd.DataFrame,
    *,
    min_background_yield_36fb: float = MIN_CATEGORY_BACKGROUND_YIELD_36FB,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    initial_summary, _ = _build_category_summary(frame)
    initial_summary = initial_summary.sort_values(
        "category",
        key=lambda values: values.map({category: index for index, category in enumerate(CATEGORIES)}),
    )
    candidate_categories = initial_summary[initial_summary["category"] != "unassigned"].copy()
    removed = candidate_categories[
        candidate_categories["total_background_yield_36fb"] < float(min_background_yield_36fb)
    ].copy()
    kept = candidate_categories[
        candidate_categories["total_background_yield_36fb"] >= float(min_background_yield_36fb)
    ].copy()
    removed_categories = [str(value) for value in removed["category"].tolist()]
    kept_categories = [str(value) for value in kept["category"].tolist()]

    updated = frame.copy()
    updated["category_before_min_background_requirement"] = updated["assigned_category"].astype(str)
    updated["category_removed_by_min_background_requirement"] = updated[
        "category_before_min_background_requirement"
    ].isin(removed_categories)
    if removed_categories:
        updated.loc[updated["category_removed_by_min_background_requirement"], "assigned_category"] = "unassigned"

    pre_retention = {
        str(row.category): {
            "raw_selected_events": int(row.raw_selected_events),
            "signal_yield_36fb": float(row.signal_yield_36fb),
            "resonant_higgs_background_yield_36fb": float(row.resonant_higgs_background_yield_36fb),
            "nti_continuum_proxy_yield_36fb": float(row.nti_continuum_proxy_yield_36fb),
            "total_background_yield_36fb": float(row.total_background_yield_36fb),
            "asimov_z": float(row.asimov_z),
        }
        for row in initial_summary.itertuples(index=False)
    }
    retention = {
        "minimum_total_background_yield_36fb": float(min_background_yield_36fb),
        "yield_definition": "resonant_higgs_background_yield_36fb + nti_continuum_proxy_yield_36fb in 125 +/- 2 GeV",
        "action": "non-unassigned categories below the minimum background yield are merged into unassigned before final yields, significances, and plots are written",
        "kept_categories": kept_categories,
        "removed_categories": removed_categories,
        "pre_retention": pre_retention,
    }
    return updated, initial_summary, retention


def _combined_significance(summary: pd.DataFrame) -> float:
    total = 0.0
    for row in summary.itertuples(index=False):
        signal = float(row.signal_yield_36fb)
        background = float(row.total_background_yield_36fb)
        if signal <= 0.0 or background <= 0.0:
            continue
        total += (signal + background) * math.log1p(signal / background) - signal
    return math.sqrt(max(2.0 * total, 0.0))


def _write_table(frame: pd.DataFrame, path: Path) -> Path:
    ensure_dir(path.parent)
    frame.to_csv(path, index=False)
    return path


def _category_yields_36fb_payload(summary: pd.DataFrame) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for row in summary.itertuples(index=False):
        category = str(row.category)
        payload[category] = {
            "raw_count": int(row.raw_selected_events),
            "weight_column": "significance_model_weight_36fb",
            "weighted_yield": float(row.total_model_yield_36fb),
            "signal_yield_36fb": float(row.signal_yield_36fb),
            "resonant_higgs_background_yield_36fb": float(row.resonant_higgs_background_yield_36fb),
            "nti_continuum_proxy_yield_36fb": float(row.nti_continuum_proxy_yield_36fb),
            "total_background_yield_36fb": float(row.total_background_yield_36fb),
            "category_kept_for_analysis": bool(row.category_kept_for_analysis),
            "category_retention_status": str(row.category_retention_status),
            "pre_retention_total_background_yield_36fb": float(row.pre_retention_total_background_yield_36fb),
            "min_background_requirement_yield_36fb": float(row.min_background_requirement_yield_36fb),
        }
    return payload


def _save_figure(fig: plt.Figure, base: Path) -> list[str]:
    ensure_dir(base.parent)
    paths = []
    for suffix in [".png", ".pdf"]:
        output = base.with_suffix(suffix)
        fig.savefig(output, dpi=140 if suffix == ".png" else None)
        paths.append(str(output))
    plt.close(fig)
    return paths


def _plot_category_yields(summary: pd.DataFrame, details: dict[str, Any], plot_dir: Path) -> list[str]:
    ordered = summary.set_index("category").loc[CATEGORIES]
    x = np.arange(len(ordered))
    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    bottom = np.zeros(len(ordered), dtype=float)
    for component, column in [
        ("NTI_continuum_proxy", "nti_continuum_proxy_yield_36fb"),
        ("resonant_higgs_background", "resonant_higgs_background_yield_36fb"),
        ("topH_signal", "signal_yield_36fb"),
    ]:
        values = ordered[column].to_numpy(dtype=float)
        ax.bar(
            x,
            values,
            bottom=bottom,
            label=COMPONENT_LABELS[component],
            color=COMPONENT_COLORS[component],
            linewidth=0.5,
            edgecolor="black",
        )
        bottom += values
    total_unc = np.asarray(
        [
            math.sqrt(
                sum(
                    float(details[category]["components"][component]["sumw2"])
                    for component in COMPONENT_ORDER
                )
            )
            for category in ordered.index
        ],
        dtype=float,
    )
    ax.errorbar(
        x,
        bottom,
        yerr=total_unc,
        fmt="none",
        ecolor="black",
        elinewidth=1.0,
        capsize=2.0,
        label="model stat. unc.",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(ordered.index, rotation=45, ha="right")
    ax.set_ylabel("Expected events / category at 36 fb^-1")
    ax.set_xlabel("Assigned category")
    ax.text(0.02, 0.96, "L = 36 fb^-1", transform=ax.transAxes, va="top", ha="left")
    ax.legend(loc="upper right", frameon=False)
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    return _save_figure(fig, plot_dir / "category_expected_yields_36fb_v1")


def _plot_category_significance(summary: pd.DataFrame, plot_dir: Path) -> list[str]:
    ordered = summary.set_index("category").loc[CATEGORIES]
    x = np.arange(len(ordered))
    fig, ax = plt.subplots(figsize=(10.8, 4.8))
    ax.bar(x, ordered["asimov_z"].to_numpy(dtype=float), color="#005f73", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(ordered.index, rotation=45, ha="right")
    ax.set_ylabel("Expected counting Z")
    ax.set_xlabel("Assigned category")
    ax.text(0.02, 0.96, "L = 36 fb^-1", transform=ax.transAxes, va="top", ha="left")
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    return _save_figure(fig, plot_dir / "category_expected_counting_z_36fb_v1")


def _hist_payload(values: np.ndarray, weights: np.ndarray, bins: np.ndarray) -> dict[str, Any]:
    mask = np.isfinite(values) & np.isfinite(weights)
    values = values[mask]
    weights = weights[mask]
    counts, _ = np.histogram(values, bins=bins, weights=weights)
    sumw2, _ = np.histogram(values, bins=bins, weights=weights * weights)
    return {
        "bin_edges": [float(value) for value in bins],
        "counts": [float(value) for value in counts],
        "sumw2": [float(value) for value in sumw2],
        "raw_count": int(values.size),
        "total_weight": float(np.sum(weights)),
        "underflow_weight": float(np.sum(weights[values < bins[0]])) if values.size else 0.0,
        "overflow_weight": float(np.sum(weights[values >= bins[-1]])) if values.size else 0.0,
    }


def _control_component_frame(frame: pd.DataFrame, component: str) -> pd.DataFrame:
    masks = _component_masks(frame)
    if component == "topH_signal":
        return frame.loc[masks["topH_signal_control_shape"]].copy()
    if component == "resonant_higgs_background":
        return frame.loc[masks["resonant_higgs_background_control_shape"]].copy()
    if component == "NTI_continuum_proxy":
        return frame.loc[masks["NTI_continuum_proxy_control_shape"]].copy()
    raise KeyError(component)


def _nti_control_shape_scale(output_dir: Path) -> tuple[float, str]:
    mixture_path = output_dir.parent / "model" / "background_mixture_and_normalization.json"
    if not mixture_path.exists():
        return 1.0, "unit observed-data weight; normalization file not found"
    try:
        payload = json.loads(mixture_path.read_text(encoding="utf-8"))
        sf1 = float(payload.get("sf1_ti_sideband_over_nti_sideband", 1.0))
    except Exception:
        return 1.0, "unit observed-data weight; normalization file could not be parsed"
    if not math.isfinite(sf1) or sf1 <= 0.0:
        return 1.0, "unit observed-data weight; invalid SF1 in normalization file"
    return sf1, "SF1 = observed TI sideband yield / observed NTI sideband yield"


def _plot_mgg_grid(frame: pd.DataFrame, plot_dir: Path, *, nti_shape_scale: float, nti_shape_scale_source: str) -> tuple[list[str], dict[str, Any]]:
    payload: dict[str, Any] = {
        "normalization": "absolute expected/model yield at 36 fb^-1 for MC TI events; NTI visible-mass control shapes use observed-data unit weights scaled by SF1",
        "binning": "55 uniform 1 GeV bins over m_gammagamma [105, 160] GeV; underflow/overflow are recorded in JSON and not drawn",
        "blinding_policy": "observed TI data are blinded in 120-130 GeV; NTI control-shape entries are retained across 105-160 GeV, including 120-130 GeV",
        "nti_control_shape_mass_window_gev": [105.0, 160.0],
        "nti_control_shape_includes_120_130": True,
        "nti_control_shape_weight": "observed_data_weight * nti_control_shape_scale",
        "nti_control_shape_scale": float(nti_shape_scale),
        "nti_control_shape_scale_source": nti_shape_scale_source,
        "yield_significance_note": "NTI control-shape weights are for plotting only; category yields/significance continue to use nti_continuum_proxy_weight from sidebands.",
        "categories": {},
    }
    fig, axes = plt.subplots(4, 3, figsize=(13.2, 11.2), sharex=True)
    axes_flat = axes.ravel()
    for index, category in enumerate(CATEGORIES):
        ax = axes_flat[index]
        category_payload: dict[str, Any] = {}
        total_counts = np.zeros(len(MASS_BINS) - 1, dtype=float)
        total_sumw2 = np.zeros(len(MASS_BINS) - 1, dtype=float)
        for component in COMPONENT_ORDER:
            subset = _control_component_frame(frame, component)
            subset = subset[subset["assigned_category"].astype(str) == category]
            values = _as_float_series(subset, "m_gammagamma").to_numpy(dtype=float)
            if component == "NTI_continuum_proxy":
                weights = (
                    _as_float_series(subset, "observed_data_weight").to_numpy(dtype=float) * float(nti_shape_scale)
                    if len(subset)
                    else np.asarray([], dtype=float)
                )
            else:
                weights = _component_weight(subset, component).to_numpy(dtype=float) if len(subset) else np.asarray([], dtype=float)
            hist = _hist_payload(values, weights, MASS_BINS)
            category_payload[component] = hist
            total_counts += np.asarray(hist["counts"], dtype=float)
            total_sumw2 += np.asarray(hist["sumw2"], dtype=float)
            ax.step(
                MASS_BINS,
                np.r_[hist["counts"], hist["counts"][-1] if hist["counts"] else 0.0],
                where="post",
                linewidth=1.6,
                color=COMPONENT_COLORS[component],
                label=COMPONENT_LABELS[component],
            )
        total_unc = np.sqrt(total_sumw2)
        ax.fill_between(
            MASS_BINS,
            np.r_[np.maximum(total_counts - total_unc, 0.0), max(float(total_counts[-1] - total_unc[-1]), 0.0)],
            np.r_[total_counts + total_unc, float(total_counts[-1] + total_unc[-1])],
            step="post",
            color="gray",
            alpha=0.22,
            label="model stat. unc." if index == 0 else None,
        )
        payload["categories"][category] = category_payload
        ax.set_title(category, fontsize=10)
        ax.set_xlim(105.0, 160.0)
        ax.grid(True, alpha=0.18)
        if index % 3 == 0:
            ax.set_ylabel("Expected events / 1 GeV")
        if index >= 9:
            ax.set_xlabel("m_gammagamma [GeV]")
    for ax in axes_flat[len(CATEGORIES) :]:
        ax.axis("off")
    axes_flat[0].legend(loc="upper right", frameon=False, fontsize=8)
    fig.suptitle("Categorization mass control shapes, L = 36 fb^-1", y=0.995, fontsize=13)
    fig.tight_layout()
    paths = _save_figure(fig, plot_dir / "category_mgg_control_shapes_36fb_v1")
    return paths, payload


def _clean_thresholds_descending(values: Any) -> list[float]:
    if values is None:
        return []
    clean: list[float] = []
    for value in values:
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(threshold) and 0.0 < threshold < 1.0:
            clean.append(threshold)
    return sorted(set(clean), reverse=True)


def _read_thresholds_json(path: Path) -> list[float]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        values = payload.get("thresholds_descending", payload.get("thresholds", []))
    else:
        values = payload
    return _clean_thresholds_descending(values)


def _plot_bdt_components(
    frame: pd.DataFrame,
    plot_dir: Path,
    *,
    thresholds_descending: list[float] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    thresholds = _clean_thresholds_descending(thresholds_descending)
    payload: dict[str, Any] = {
        "normalization": "absolute expected/model yield at 36 fb^-1 for the signal-window model components",
        "binning": "40 uniform bins over BDT score [0, 1], width 0.025; underflow/overflow are recorded in JSON and not drawn",
        "thresholds_descending": thresholds,
        "category_boundary_lines": [
            {"bdt_score": threshold, "style": "vertical dashed line", "source": "optimized hadronic BDT boundary"}
            for threshold in thresholds
        ],
        "components": {},
    }
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    total_counts = np.zeros(len(SCORE_BINS) - 1, dtype=float)
    total_sumw2 = np.zeros(len(SCORE_BINS) - 1, dtype=float)
    for component in COMPONENT_ORDER:
        masks = _component_masks(frame)
        subset = frame.loc[masks[component]].copy()
        values = _as_float_series(subset, "bdt_score").to_numpy(dtype=float)
        weights = _component_weight(subset, component).to_numpy(dtype=float) if len(subset) else np.asarray([], dtype=float)
        hist = _hist_payload(values, weights, SCORE_BINS)
        payload["components"][component] = hist
        total_counts += np.asarray(hist["counts"], dtype=float)
        total_sumw2 += np.asarray(hist["sumw2"], dtype=float)
        ax.step(
            SCORE_BINS,
            np.r_[hist["counts"], hist["counts"][-1] if hist["counts"] else 0.0],
            where="post",
            linewidth=1.8,
            color=COMPONENT_COLORS[component],
            label=COMPONENT_LABELS[component],
        )
    total_unc = np.sqrt(total_sumw2)
    ax.fill_between(
        SCORE_BINS,
        np.r_[np.maximum(total_counts - total_unc, 0.0), max(float(total_counts[-1] - total_unc[-1]), 0.0)],
        np.r_[total_counts + total_unc, float(total_counts[-1] + total_unc[-1])],
        step="post",
        color="gray",
        alpha=0.22,
        label="model stat. unc.",
    )
    for index, threshold in enumerate(thresholds):
        ax.axvline(
            threshold,
            color="black",
            linestyle=(0, (4, 3)),
            linewidth=1.0,
            alpha=0.85,
            label="category boundary" if index == 0 else None,
        )
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("BDT score")
    ax.set_ylabel("Expected events / bin at 36 fb^-1")
    ax.text(0.02, 0.96, "L = 36 fb^-1", transform=ax.transAxes, va="top", ha="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.23), ncol=2, frameon=False)
    ax.grid(True, alpha=0.2)
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.86])
    paths = _save_figure(fig, plot_dir / "bdt_score_model_components_36fb_v1")
    if thresholds:
        paths.extend(_save_figure(fig, plot_dir / "bdt_score_model_components_with_boundaries_36fb_v1"))
    return paths, payload


def run_categorization(
    inference_table: Path,
    output_dir: Path,
    *,
    thresholds_descending: list[float] | None = None,
) -> dict[str, Any]:
    started = utcnow_iso()
    output_dir = ensure_dir(output_dir)
    plot_dir = ensure_dir(output_dir / "plots")
    hist_dir = ensure_dir(output_dir / "histograms")
    thresholds = _clean_thresholds_descending(thresholds_descending)
    if not thresholds:
        thresholds = _read_thresholds_json(output_dir.parent / "optimization" / "thresholds.json")

    frame = pd.read_csv(inference_table, low_memory=False)
    for column in [
        "m_gammagamma",
        "bdt_score",
        "mc_event_weight_36fb",
        "observed_data_weight",
        "nti_continuum_proxy_weight",
        "significance_model_weight_36fb",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame, initial_summary, retention = _apply_min_background_requirement(frame)
    summary, component_details = _build_category_summary(frame)
    summary = summary.sort_values("category", key=lambda values: values.map({category: index for index, category in enumerate(CATEGORIES)}))
    pre_background = {
        str(row.category): float(row.total_background_yield_36fb)
        for row in initial_summary.itertuples(index=False)
    }
    pre_raw = {
        str(row.category): int(row.raw_selected_events)
        for row in initial_summary.itertuples(index=False)
    }
    removed_categories = set(str(value) for value in retention["removed_categories"])
    kept_categories = set(str(value) for value in retention["kept_categories"])
    summary["pre_retention_total_background_yield_36fb"] = summary["category"].map(pre_background).fillna(0.0)
    summary["pre_retention_raw_selected_events"] = summary["category"].map(pre_raw).fillna(0).astype(int)
    summary["min_background_requirement_yield_36fb"] = retention["minimum_total_background_yield_36fb"]
    summary["category_kept_for_analysis"] = summary["category"].map(lambda category: str(category) in kept_categories)
    summary["category_retention_status"] = summary["category"].map(
        lambda category: "catch_all"
        if str(category) == "unassigned"
        else "merged_into_unassigned"
        if str(category) in removed_categories
        else "kept"
    )
    summary["merged_into_unassigned_by_min_background"] = summary["category"].map(lambda category: str(category) in removed_categories)
    for category, detail in component_details.items():
        detail["pre_retention_total_background_yield_36fb"] = pre_background.get(category, 0.0)
        detail["pre_retention_raw_selected_events"] = pre_raw.get(category, 0)
        detail["min_background_requirement_yield_36fb"] = retention["minimum_total_background_yield_36fb"]
        detail["category_kept_for_analysis"] = category in kept_categories
        detail["category_retention_status"] = (
            "catch_all"
            if category == "unassigned"
            else "merged_into_unassigned"
            if category in removed_categories
            else "kept"
        )
    _write_table(summary, output_dir / "category_summary.csv")
    write_json(component_details, output_dir / "category_component_yields.json")
    write_json(retention, output_dir / "category_retention.json")
    category_yields_36fb = _category_yields_36fb_payload(summary)
    write_json(category_yields_36fb, output_dir.parent / "category_yields_36fb.json")
    write_json(category_yields_36fb, output_dir / "category_yields_36fb.json")

    plots: dict[str, list[str]] = {}
    plots["category_expected_yields"] = _plot_category_yields(summary, component_details, plot_dir)
    plots["category_expected_counting_z"] = _plot_category_significance(summary, plot_dir)
    nti_shape_scale, nti_shape_scale_source = _nti_control_shape_scale(output_dir)
    mgg_paths, mgg_payload = _plot_mgg_grid(
        frame,
        plot_dir,
        nti_shape_scale=nti_shape_scale,
        nti_shape_scale_source=nti_shape_scale_source,
    )
    plots["category_mgg_control_shapes"] = mgg_paths
    bdt_paths, bdt_payload = _plot_bdt_components(frame, plot_dir, thresholds_descending=thresholds)
    plots["bdt_score_model_components"] = bdt_paths
    write_json(mgg_payload, hist_dir / "category_mgg_control_histograms.json")
    write_json(bdt_payload, hist_dir / "bdt_score_model_component_histograms.json")

    combined_z = _combined_significance(summary)
    totals = {
        "signal_yield_36fb": float(summary["signal_yield_36fb"].sum()),
        "resonant_higgs_background_yield_36fb": float(summary["resonant_higgs_background_yield_36fb"].sum()),
        "nti_continuum_proxy_yield_36fb": float(summary["nti_continuum_proxy_yield_36fb"].sum()),
        "total_background_yield_36fb": float(summary["total_background_yield_36fb"].sum()),
        "total_model_yield_36fb": float(summary["total_model_yield_36fb"].sum()),
        "observed_ti_data_signal_window_count": None,
        "observed_ti_data_signal_window_blinded": True,
        "observed_ti_data_sideband_count": int(summary["observed_ti_data_sideband_count"].sum()),
        "combined_expected_counting_z": combined_z,
    }
    ranking = summary.sort_values("asimov_z", ascending=False)[
        ["category", "signal_yield_36fb", "total_background_yield_36fb", "s_over_b", "asimov_z"]
    ].to_dict(orient="records")
    manifest = {
        "status": "ok",
        "started_at_utc": started,
        "ended_at_utc": utcnow_iso(),
        "input_table": str(inference_table),
        "rows": int(len(frame)),
        "category_order": CATEGORIES,
        "component_order": COMPONENT_ORDER,
        "normalization": {
            "luminosity_fb": 36.0,
            "signal_window_gev": [123.0, 127.0],
            "visible_mass_window_gev": [105.0, 160.0],
            "sidebands_gev": [[105.0, 120.0], [130.0, 160.0]],
            "signal_window_model": "MC TI events in 125 +/- 2 GeV plus data NTI sideband proxy scaled by SF1*SF2",
            "signal_weight": "mc_event_weight_36fb for ttH+tH",
            "resonant_background_weight": "mc_event_weight_36fb for ggH/VBF/WH/ZH/ggZH",
            "continuum_background_weight": "nti_continuum_proxy_weight for data NTI sidebands",
            "observed_data_weight": "observed_data_weight for TI data counts; observed data are not included in expected Asimov significance",
            "blinding_policy": "observed TI data in 125 +/- 2 GeV are not counted or plotted; only sideband TI data counts are reported",
            "category_retention_policy": "non-unassigned categories are kept only if total expected background in 125 +/- 2 GeV is at least 0.8 events after resonant Higgs plus SF1*SF2-scaled NTI continuum normalization",
        },
        "category_retention": retention,
        "plotting": {
            "mass_binning": "55 uniform 1 GeV bins over [105, 160] GeV; underflow/overflow recorded in histogram JSON",
            "bdt_binning": "40 uniform bins over [0, 1]; underflow/overflow recorded in histogram JSON",
            "bdt_category_boundaries_descending": thresholds,
            "normalization": "absolute expected/model yield at 36 fb^-1",
            "uncertainty": "histogram JSON records sumw2 per bin; PNG/PDF previews draw statistical uncertainty on the summed model where applicable",
            "nti_control_shape_policy": "NTI distributions are drawn over the full 105-160 GeV control-shape range, including 120-130 GeV, using observed-data unit weights scaled by SF1. The 120-130 GeV blinding/removal policy applies only to observed TI data.",
        },
        "totals": totals,
        "ranking_by_expected_z": ranking,
        "artifacts": {
            "category_summary_csv": str(output_dir / "category_summary.csv"),
            "category_yields_36fb": str(output_dir.parent / "category_yields_36fb.json"),
            "category_component_yields": str(output_dir / "category_component_yields.json"),
            "category_retention": str(output_dir / "category_retention.json"),
            "mgg_histograms": str(hist_dir / "category_mgg_control_histograms.json"),
            "bdt_histograms": str(hist_dir / "bdt_score_model_component_histograms.json"),
            "plots": plots,
        },
    }
    write_json(manifest, output_dir / "categorization_manifest.json")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference-table", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--thresholds-json")
    args = parser.parse_args()
    thresholds = _read_thresholds_json(Path(args.thresholds_json)) if args.thresholds_json else None
    manifest = run_categorization(
        Path(args.inference_table),
        Path(args.output_dir),
        thresholds_descending=thresholds,
    )
    print(json.dumps({"status": manifest["status"], "rows": manifest["rows"], "output_dir": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
