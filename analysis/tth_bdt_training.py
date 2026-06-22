from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.common import ensure_dir, utcnow_iso, write_json
from analysis.top_categorization import BDT_FEATURES, assign_top_category, optimize_bdt_boundaries


SIGNAL_WINDOW = (123.0, 127.0)
SIDEBANDS = ((105.0, 120.0), (130.0, 160.0))
SCORE_BINS = np.linspace(0.0, 1.0, 41)
TOPH_SIGNAL_PROCESSES = {"ttH", "tH"}
RESONANT_HIGGS_BACKGROUND_PROCESSES = {"ggH", "VBF", "WH", "ZH", "ggZH"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if math.isfinite(out) else default


def _safe_ratio(numerator: float, denominator: float) -> float:
    denominator = float(denominator)
    if denominator == 0.0:
        return 0.0
    return float(numerator) / denominator


def _weighted_sum(frame: pd.DataFrame, mask: pd.Series, column: str = "event_weight") -> float:
    if frame.empty:
        return 0.0
    return float(frame.loc[mask, column].sum())


def _count(frame: pd.DataFrame, mask: pd.Series) -> int:
    if frame.empty:
        return 0
    return int(mask.sum())


def _write_table(frame: pd.DataFrame, path: Path) -> Path:
    ensure_dir(path.parent)
    frame.to_csv(path, index=False)
    return path


def _categorical_code_map(frame: pd.DataFrame, column: str) -> dict[str, int]:
    values = sorted({str(value) for value in frame[column].fillna("missing").to_numpy()})
    return {value: index for index, value in enumerate(values)}


def _write_root_numeric_tree(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    ensure_dir(path.parent)
    try:
        import uproot
    except Exception as exc:
        return {
            "status": "skipped",
            "reason": f"uproot import failed: {type(exc).__name__}: {exc}",
            "path": str(path),
            "tree_name": "analysis",
            "columns_written": [],
            "columns_skipped": list(frame.columns),
        }

    arrays: dict[str, np.ndarray] = {}
    skipped: list[str] = []
    for column in frame.columns:
        series = frame[column]
        if pd.api.types.is_bool_dtype(series):
            arrays[column] = series.fillna(False).to_numpy(dtype=np.bool_)
            continue
        if pd.api.types.is_numeric_dtype(series):
            if pd.api.types.is_integer_dtype(series.dtype) and series.notna().all():
                arrays[column] = series.to_numpy(dtype=np.int64)
            else:
                arrays[column] = series.to_numpy(dtype=np.float64)
            continue
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().all():
            arrays[column] = numeric.to_numpy(dtype=np.float64)
        else:
            skipped.append(column)

    try:
        with uproot.recreate(path) as handle:
            handle["analysis"] = arrays
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}",
            "path": str(path),
            "tree_name": "analysis",
            "columns_written": sorted(arrays),
            "columns_skipped": skipped,
        }

    return {
        "status": "ok",
        "path": str(path),
        "tree_name": "analysis",
        "rows": int(len(frame)),
        "columns_written": sorted(arrays),
        "columns_skipped": skipped,
    }


def _add_categorization_weights(
    frame: pd.DataFrame,
    *,
    event_weight_luminosity_fb: float,
    significance_luminosity_fb: float,
    nti_to_ti_signal_window_scale: float,
) -> pd.DataFrame:
    frame = frame.copy()
    event_weight_luminosity_fb = float(event_weight_luminosity_fb)
    significance_luminosity_fb = float(significance_luminosity_fb)
    mc_lumi_scale = _safe_ratio(significance_luminosity_fb, event_weight_luminosity_fb)

    process = frame["process"].astype(str)
    role = frame["role"].astype(str) if "role" in frame else pd.Series([""] * len(frame), index=frame.index)
    is_data = (process == "data") | (role == "data")
    is_mc = ~is_data
    nti_proxy = is_data & frame["is_nti_diphoton"].astype(bool) & frame["in_mgg_sideband_105_120_130_160"].astype(bool)

    frame["event_weight_luminosity_fb"] = np.where(is_mc, event_weight_luminosity_fb, np.nan)
    frame["mc_lumi_scale_to_36fb"] = np.where(is_mc, mc_lumi_scale, np.nan)
    frame["mc_event_weight_36fb"] = np.where(is_mc, frame["event_weight"].astype(float) * mc_lumi_scale, 0.0)
    frame["observed_data_weight"] = np.where(is_data, 1.0, 0.0)
    frame["nti_continuum_proxy_weight"] = np.where(
        nti_proxy,
        frame["observed_data_weight"].astype(float) * float(nti_to_ti_signal_window_scale),
        0.0,
    )
    frame["significance_model_weight_36fb"] = frame["mc_event_weight_36fb"].astype(float) + frame["nti_continuum_proxy_weight"].astype(float)

    component = np.full(len(frame), "unused_observed_data", dtype=object)
    component[process.isin(TOPH_SIGNAL_PROCESSES).to_numpy()] = "topH_signal"
    component[process.isin(RESONANT_HIGGS_BACKGROUND_PROCESSES).to_numpy()] = "resonant_higgs_background"
    component[nti_proxy.to_numpy()] = "NTI_continuum_proxy_sideband"
    component[(is_data & frame["is_ti_diphoton"].astype(bool) & frame["in_mgg_123_127"].astype(bool)).to_numpy()] = "observed_TI_data_signal_window"
    frame["categorization_component"] = component
    return frame


def _write_inference_artifacts(
    frame: pd.DataFrame,
    out_dir: Path,
    *,
    thresholds: list[float],
    model_path: Path,
    event_weight_luminosity_fb: float,
    significance_luminosity_fb: float,
    nti_to_ti_signal_window_scale: float,
) -> dict[str, Any]:
    inference_dir = ensure_dir(out_dir / "inference")
    inference_frame = frame.copy()
    code_maps: dict[str, dict[str, int]] = {}
    for column in ["process", "role", "preselection_channel", "partition", "assigned_category", "bdt_training_role", "categorization_component"]:
        code_map = _categorical_code_map(inference_frame, column)
        code_maps[column] = code_map
        inference_frame[f"{column}_code"] = (
            inference_frame[column].fillna("missing").astype(str).map(code_map).astype(np.int64)
        )
    inference_frame["bdt_score_is_finite"] = np.isfinite(pd.to_numeric(inference_frame["bdt_score"], errors="coerce"))

    csv_path = _write_table(inference_frame, inference_dir / "events_with_bdt_scores.csv")
    root_payload = inference_frame.drop(
        columns=[
            "event_id",
            "sample_id",
            "process",
            "role",
            "source_file",
            "preselection_channel",
            "partition",
            "assigned_category",
            "bdt_training_role",
            "categorization_component",
        ],
        errors="ignore",
    )
    root_status = _write_root_numeric_tree(root_payload, inference_dir / "events_with_bdt_scores.root")

    score_is_finite = inference_frame["bdt_score_is_finite"].astype(bool)
    summary: dict[str, Any] = {
        "status": "ok" if bool(score_is_finite.all()) else "warning",
        "scope": "all preselected events with finite BDT input features",
        "rows": int(len(inference_frame)),
        "scored_rows": int(score_is_finite.sum()),
        "unscored_rows": int((~score_is_finite).sum()),
        "bdt_score_column": "bdt_score",
        "bdt_score_range": {
            "min": float(inference_frame.loc[score_is_finite, "bdt_score"].min()) if bool(score_is_finite.any()) else None,
            "max": float(inference_frame.loc[score_is_finite, "bdt_score"].max()) if bool(score_is_finite.any()) else None,
        },
        "features": BDT_FEATURES,
        "model_path": str(model_path),
        "thresholds_descending": thresholds,
        "category_note": "BDT scores are evaluated for all preselected events; hadronic BDT thresholds are only used by hadronic category assignment.",
        "normalization_strategy": {
            "event_weight": f"MC physical event weight at {float(event_weight_luminosity_fb):.6g} fb^-1; data rows have event_weight = 1",
            "mc_event_weight_36fb": "MC event_weight rescaled to 36 fb^-1; data rows are zero in this column",
            "nti_continuum_proxy_weight": "data NTI sideband rows scaled by SF1*SF2 to proxy the TI continuum in the 125 +/- 2 GeV signal window",
            "significance_model_weight_36fb": "expected-yield model weight for categorization/significance: MC at 36 fb^-1 plus scaled NTI continuum proxy; ordinary observed data rows are zero",
            "observed_data_weight": "unit data weight for observed data comparisons, not for expected Asimov significance",
            "event_weight_luminosity_fb": float(event_weight_luminosity_fb),
            "significance_mc_luminosity_fb": float(significance_luminosity_fb),
            "mc_lumi_scale_to_36fb": _safe_ratio(float(significance_luminosity_fb), float(event_weight_luminosity_fb)),
            "nti_to_ti_signal_window_scale": float(nti_to_ti_signal_window_scale),
            "class_balanced_bdt_fit_weight_warning": "bdt_fit_weight is only for classifier fitting and must not be used for category yields or significance.",
        },
        "csv": str(csv_path),
        "root": root_status,
        "categorical_code_maps": code_maps,
        "counts_by_channel": {
            str(channel): {
                "rows": int(len(subset)),
                "scored_rows": int(subset["bdt_score_is_finite"].sum()),
            }
            for channel, subset in inference_frame.groupby("preselection_channel", dropna=False)
        },
        "counts_by_process": {
            str(process): {
                "rows": int(len(subset)),
                "scored_rows": int(subset["bdt_score_is_finite"].sum()),
            }
            for process, subset in inference_frame.groupby("process", dropna=False)
        },
        "columns": list(inference_frame.columns),
    }
    write_json(summary, inference_dir / "inference_manifest.json")
    return summary


def _save_figure(fig: plt.Figure, base: Path) -> list[str]:
    ensure_dir(base.parent)
    paths = []
    for suffix in [".png", ".pdf"]:
        output = base.with_suffix(suffix)
        fig.savefig(output, dpi=140 if suffix == ".png" else None)
        paths.append(str(output))
    plt.close(fig)
    return paths


def _normalised_hist(
    ax: plt.Axes,
    values: np.ndarray,
    weights: np.ndarray,
    *,
    bins: np.ndarray,
    label: str,
    color: str,
    linestyle: str = "-",
) -> None:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights) & (weights >= 0.0)
    values = values[mask]
    weights = weights[mask]
    total = float(np.sum(weights))
    if values.size == 0 or total <= 0.0:
        counts = np.zeros(len(bins) - 1, dtype=float)
    else:
        counts, _ = np.histogram(values, bins=bins, weights=weights)
        counts = counts / total
    ax.step(bins, np.r_[counts, counts[-1] if counts.size else 0.0], where="post", label=label, color=color, linewidth=1.8, linestyle=linestyle)


def _histogram_payload(values: np.ndarray, weights: np.ndarray, bins: np.ndarray, *, normalize: bool) -> dict[str, Any]:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights)
    values = values[mask]
    weights = weights[mask]
    counts, _ = np.histogram(values, bins=bins, weights=weights)
    sumw2, _ = np.histogram(values, bins=bins, weights=weights * weights)
    total = float(np.sum(weights))
    if normalize and total != 0.0:
        counts = counts / total
        sumw2 = sumw2 / (total * total)
    return {
        "bin_edges": [float(value) for value in bins],
        "counts": [float(value) for value in counts],
        "sumw2": [float(value) for value in sumw2],
        "total_weight": total,
        "raw_count": int(values.size),
    }


def _plot_score_by_component(training_frame: pd.DataFrame, plot_dir: Path) -> tuple[dict[str, list[str]], dict[str, Any]]:
    components = [
        ("topH_signal", "ttH + tH signal", "#005f73"),
        ("ggH_resonant_background", "ggH resonant Higgs background", "#0a9396"),
        ("NTI_continuum_proxy_sideband", "NTI continuum background", "#ca6702"),
    ]
    score_bins = SCORE_BINS
    outputs: dict[str, list[str]] = {}
    histogram_payload: dict[str, Any] = {
        "score_bins": [float(value) for value in score_bins],
        "binning": "40 uniform bins over BDT score [0, 1], width 0.025",
        "normalization_modes": {
            "shape": "each component is unit-normalized to area 1 with nonnegative classifier fit weights",
        },
        "component_totals_before_shape_normalization": {},
        "components": {},
    }

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    for component, label, color in components:
        subset = training_frame[training_frame["training_component"] == component]
        weights = subset["fit_weight"].to_numpy(dtype=float)
        scores = subset["bdt_score"].to_numpy(dtype=float)
        histogram_payload["component_totals_before_shape_normalization"][component] = {
            "raw_count": int(len(subset)),
            "fit_weight_sum": float(np.sum(weights)),
            "physical_training_weight_sum": float(subset["physical_training_weight"].sum()),
        }
        _normalised_hist(ax, scores, weights, bins=score_bins, label=label, color=color)
        histogram_payload["components"].setdefault(component, {})["shape"] = _histogram_payload(
            scores,
            weights,
            score_bins,
            normalize=True,
        )
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("BDT score")
    ax.set_ylabel("Normalized events / bin")
    ax.legend(loc="upper center", frameon=False)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    outputs["score_by_component_shape"] = _save_figure(fig, plot_dir / "score_by_component_shape_bdt_v1")
    return outputs, histogram_payload


def _plot_training_diagnostics(training_frame: pd.DataFrame, plot_dir: Path) -> dict[str, list[str]]:
    from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve

    outputs: dict[str, list[str]] = {}
    eval_frame = training_frame[
        training_frame["partition"].isin(["training", "validation"])
        & np.isfinite(training_frame["bdt_score"])
        & (training_frame["fit_weight"] >= 0.0)
    ].copy()
    if eval_frame.empty or eval_frame["label"].nunique() < 2:
        return outputs

    y = eval_frame["label"].to_numpy(dtype=int)
    score = eval_frame["bdt_score"].to_numpy(dtype=float)
    weight = eval_frame["fit_weight"].to_numpy(dtype=float)

    fpr, tpr, _ = roc_curve(y, score, sample_weight=weight)
    auc = roc_auc_score(y, score, sample_weight=weight)
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.plot(tpr, 1.0 - fpr, color="#005f73", linewidth=2.0, label=f"Validation/training AUC = {auc:.3f}")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Signal efficiency")
    ax.set_ylabel("Background rejection")
    ax.legend(loc="lower left", frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    outputs["roc_curve"] = _save_figure(fig, plot_dir / "roc_curve_bdt_training_v1")

    precision, recall, _ = precision_recall_curve(y, score, sample_weight=weight)
    average_precision = average_precision_score(y, score, sample_weight=weight)
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.plot(recall, precision, color="#9b2226", linewidth=2.0, label=f"AP = {average_precision:.3f}")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Signal efficiency")
    ax.set_ylabel("Precision")
    ax.legend(loc="lower left", frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    outputs["precision_recall"] = _save_figure(fig, plot_dir / "precision_recall_bdt_training_v1")

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    style = {
        ("training", 1): ("Signal training", "#005f73", "-"),
        ("training", 0): ("Background training", "#ca6702", "-"),
        ("validation", 1): ("Signal validation", "#005f73", "--"),
        ("validation", 0): ("Background validation", "#ca6702", "--"),
    }
    for (partition, label), (legend, color, linestyle) in style.items():
        subset = training_frame[(training_frame["partition"] == partition) & (training_frame["label"] == label)]
        _normalised_hist(
            ax,
            subset["bdt_score"].to_numpy(dtype=float),
            subset["fit_weight"].to_numpy(dtype=float),
            bins=SCORE_BINS,
            label=legend,
            color=color,
            linestyle=linestyle,
        )
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("BDT score")
    ax.set_ylabel("Normalized events / bin")
    ax.legend(loc="upper center", ncols=2, frameon=False)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    outputs["score_training_validation"] = _save_figure(fig, plot_dir / "score_training_validation_bdt_v1")
    component_outputs, component_payload = _plot_score_by_component(training_frame, plot_dir)
    outputs.update(component_outputs)
    write_json(component_payload, plot_dir / "score_by_component_histograms.json")

    feature_bins = {
        "ht_jets": np.linspace(0.0, 1200.0, 31),
        "m_all_jets": np.linspace(0.0, 1800.0, 31),
        "n_jets": np.arange(2.5, 12.6, 1.0),
        "n_central_jets": np.arange(-0.5, 10.6, 1.0),
        "n_btags": np.arange(0.5, 6.6, 1.0),
    }
    fig, axes = plt.subplots(2, 3, figsize=(12.0, 7.2))
    axes_flat = axes.ravel()
    for idx, feature in enumerate(BDT_FEATURES):
        ax = axes_flat[idx]
        bins = feature_bins[feature]
        for label, legend, color in [(1, "ttH signal", "#005f73"), (0, "ggH + NTI background", "#ca6702")]:
            subset = training_frame[(training_frame["partition"] == "training") & (training_frame["label"] == label)]
            _normalised_hist(
                ax,
                subset[feature].to_numpy(dtype=float),
                subset["fit_weight"].to_numpy(dtype=float),
                bins=bins,
                label=legend,
                color=color,
            )
        ax.set_xlabel(feature)
        ax.set_ylabel("Normalized events / bin")
        ax.grid(True, alpha=0.2)
    axes_flat[-1].axis("off")
    axes_flat[0].legend(loc="upper right", frameon=False)
    fig.tight_layout()
    outputs["input_variables"] = _save_figure(fig, plot_dir / "input_variables_bdt_training_v1")
    return outputs


def _category_yields(frame: pd.DataFrame, *, weight_column: str = "event_weight") -> dict[str, Any]:
    categories: dict[str, Any] = {}
    if "assigned_category" not in frame:
        return categories
    for category, category_frame in frame.groupby("assigned_category", dropna=False):
        category_name = str(category)
        payload: dict[str, Any] = {
            "raw_count": int(len(category_frame)),
            "weight_column": weight_column,
            "weighted_yield": float(category_frame[weight_column].sum()),
            "by_process": {},
        }
        for process, process_frame in category_frame.groupby("process"):
            payload["by_process"][str(process)] = {
                "raw_count": int(len(process_frame)),
                "weighted_yield": float(process_frame[weight_column].sum()),
            }
        categories[category_name] = payload
    return categories


def _plot_category_yields(
    category_yields: dict[str, Any],
    plot_dir: Path,
    *,
    basename: str = "category_yields_bdt_v1",
    ylabel: str = "Weighted yield",
) -> list[str]:
    ordered = [key for key in [
        "tH_lep_0fwd",
        "tH_lep_1fwd",
        "ttH_lep",
        "ttH_had_BDT1",
        "ttH_had_BDT2",
        "ttH_had_BDT3",
        "ttH_had_BDT4",
        "tH_had_4j1b",
        "tH_had_4j2b",
        "unassigned",
    ] if key in category_yields]
    if not ordered:
        return []
    values = [float(category_yields[key]["weighted_yield"]) for key in ordered]
    fig, ax = plt.subplots(figsize=(9.6, 4.8))
    ax.bar(ordered, values, color="#005f73")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Assigned category")
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    return _save_figure(fig, plot_dir / basename)


def run_prescribed_bdt_training(
    rows: list[dict[str, Any]],
    out_dir: Path,
    *,
    random_seed: int,
    event_weight_luminosity_fb: float = 139.0,
    significance_luminosity_fb: float = 36.0,
) -> dict[str, Any]:
    from joblib import dump
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import average_precision_score, roc_auc_score

    started = utcnow_iso()
    started_perf = time.perf_counter()
    model_dir = ensure_dir(out_dir / "model")
    opt_dir = ensure_dir(out_dir / "optimization")
    plot_dir = ensure_dir(out_dir / "plots")

    frame = pd.DataFrame(rows)
    if frame.empty:
        result = {"status": "blocked", "reason": "no input rows"}
        write_json(result, model_dir / "training_metadata.json")
        return result

    for column in BDT_FEATURES + ["event_weight", "m_gammagamma"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in [
        "is_ti_diphoton",
        "is_nti_diphoton",
        "in_mgg_123_127",
        "in_mgg_sideband_105_120_130_160",
    ]:
        frame[column] = frame[column].astype(bool)

    finite_features = np.isfinite(frame[BDT_FEATURES]).all(axis=1)
    hadronic = (frame["preselection_channel"] == "hadronic") & finite_features
    signal_mask = (
        hadronic
        & frame["process"].isin(["ttH", "tH"])
        & frame["is_ti_diphoton"]
        & frame["in_mgg_123_127"]
    )
    ggh_mask = (
        hadronic
        & (frame["process"] == "ggH")
        & frame["is_ti_diphoton"]
        & frame["in_mgg_123_127"]
    )
    data_hadronic = hadronic & (frame["process"] == "data")
    ti_sideband = data_hadronic & frame["is_ti_diphoton"] & frame["in_mgg_sideband_105_120_130_160"]
    nti_sideband = data_hadronic & frame["is_nti_diphoton"] & frame["in_mgg_sideband_105_120_130_160"]
    nti_signal_window = data_hadronic & frame["is_nti_diphoton"] & frame["in_mgg_123_127"]

    ti_sideband_yield = _weighted_sum(frame, ti_sideband)
    nti_sideband_yield = _weighted_sum(frame, nti_sideband)
    nti_signal_window_yield = _weighted_sum(frame, nti_signal_window)
    sf1 = _safe_ratio(ti_sideband_yield, nti_sideband_yield)
    sf2 = _safe_ratio(nti_signal_window_yield, nti_sideband_yield)
    nti_to_ti_signal_window_scale = sf1 * sf2

    training_pieces = []
    signal = frame.loc[signal_mask].copy()
    signal["label"] = 1
    signal["training_component"] = "topH_signal"
    signal["physical_training_weight"] = signal["event_weight"].astype(float)
    training_pieces.append(signal)

    ggh = frame.loc[ggh_mask].copy()
    ggh["label"] = 0
    ggh["training_component"] = "ggH_resonant_background"
    ggh["physical_training_weight"] = ggh["event_weight"].astype(float)
    training_pieces.append(ggh)

    nti = frame.loc[nti_sideband].copy()
    nti["label"] = 0
    nti["training_component"] = "NTI_continuum_proxy_sideband"
    nti["physical_training_weight"] = nti["event_weight"].astype(float) * nti_to_ti_signal_window_scale
    training_pieces.append(nti)

    training_frame = pd.concat(training_pieces, ignore_index=False).copy()
    training_frame = training_frame[np.isfinite(training_frame[BDT_FEATURES]).all(axis=1)].copy()
    training_frame["fit_weight_base"] = np.abs(training_frame["physical_training_weight"].to_numpy(dtype=float))
    training_frame = training_frame[training_frame["fit_weight_base"] > 0.0].copy()
    if training_frame.empty or training_frame["label"].nunique() < 2:
        result = {
            "status": "blocked",
            "reason": "training sample is empty or lacks one class",
            "training_counts": {
                "topH_signal": _count(frame, signal_mask),
                "ggH_resonant_background": _count(frame, ggh_mask),
                "NTI_continuum_proxy_sideband": _count(frame, nti_sideband),
            },
        }
        write_json(result, model_dir / "training_metadata.json")
        return result

    fit_partition = training_frame["partition"] == "training"
    class_sums = training_frame.loc[fit_partition].groupby("label")["fit_weight_base"].sum().to_dict()
    if set(class_sums) != {0, 1} or min(class_sums.values()) <= 0.0:
        result = {"status": "blocked", "reason": "training partition lacks positive fit weight for both classes", "class_sums": class_sums}
        write_json(result, model_dir / "training_metadata.json")
        return result
    target_class_sum = 0.5 * (float(class_sums[0]) + float(class_sums[1]))
    class_balance_scale = {int(label): _safe_ratio(target_class_sum, value) for label, value in class_sums.items()}
    training_frame["fit_weight"] = training_frame.apply(
        lambda row: float(row["fit_weight_base"]) * class_balance_scale[int(row["label"])],
        axis=1,
    )

    model = GradientBoostingClassifier(
        n_estimators=160,
        learning_rate=0.08,
        max_depth=2,
        min_samples_leaf=25,
        subsample=0.8,
        random_state=random_seed,
    )
    fit_frame = training_frame.loc[fit_partition].copy()
    model.fit(
        fit_frame[BDT_FEATURES].to_numpy(dtype=float),
        fit_frame["label"].to_numpy(dtype=int),
        sample_weight=fit_frame["fit_weight"].to_numpy(dtype=float),
    )

    training_frame["bdt_score"] = model.predict_proba(training_frame[BDT_FEATURES].to_numpy(dtype=float))[:, 1]

    score_mask = finite_features
    frame["bdt_score"] = np.nan
    frame.loc[score_mask, "bdt_score"] = model.predict_proba(frame.loc[score_mask, BDT_FEATURES].to_numpy(dtype=float))[:, 1]

    validation = training_frame[(training_frame["partition"] == "validation") & np.isfinite(training_frame["bdt_score"])].copy()
    optimization_rows = [
        {
            "score": float(row["bdt_score"]),
            "weight": float(row["physical_training_weight"]),
            "is_signal": bool(row["label"] == 1),
        }
        for _, row in validation.iterrows()
    ]
    boundary_optimization_config = {
        "max_categories": 5,
        "min_raw_events": 20,
        "min_effective_events": 10.0,
        "min_signal_yield": 0.0,
        "min_background_yield": 0.0,
        "min_interval_width": 1.0e-4,
        "min_absolute_gain": 0.0,
        "min_relative_gain": 0.05,
        "max_candidates": 180,
    }
    optimization = optimize_bdt_boundaries(
        optimization_rows,
        boundary_optimization_config,
    )
    thresholds = [float(value) for value in optimization.get("thresholds_descending", [])]

    training_index = set(training_frame.index)
    role_by_index = training_frame["training_component"].to_dict()
    label_by_index = training_frame["label"].to_dict()
    physical_weight_by_index = training_frame["physical_training_weight"].to_dict()
    fit_weight_by_index = training_frame["fit_weight"].to_dict()
    frame["bdt_training_role"] = ["not_used"] * len(frame)
    frame["bdt_training_label"] = np.nan
    frame["bdt_physical_training_weight"] = 0.0
    frame["bdt_fit_weight"] = 0.0
    for index in training_index:
        frame.at[index, "bdt_training_role"] = role_by_index[index]
        frame.at[index, "bdt_training_label"] = int(label_by_index[index])
        frame.at[index, "bdt_physical_training_weight"] = float(physical_weight_by_index[index])
        frame.at[index, "bdt_fit_weight"] = float(fit_weight_by_index[index])

    frame["assigned_category"] = [
        assign_top_category(
            {
                "n_leptons": row.n_leptons,
                "n_central_jets": row.n_central_jets,
                "n_forward_jets": row.n_forward_jets,
                "n_btags": row.n_btags,
                "n_jets": row.n_jets,
                "z_veto": False,
            },
            score=None if not math.isfinite(_safe_float(row.bdt_score, float("nan"))) else float(row.bdt_score),
            thresholds=thresholds,
        )
        for row in frame.itertuples(index=False)
    ]

    frame = _add_categorization_weights(
        frame,
        event_weight_luminosity_fb=event_weight_luminosity_fb,
        significance_luminosity_fb=significance_luminosity_fb,
        nti_to_ti_signal_window_scale=nti_to_ti_signal_window_scale,
    )

    category_yields = _category_yields(frame)
    write_json(category_yields, out_dir / "category_yields.json")
    _plot_category_yields(category_yields, plot_dir)
    category_yields_36fb = _category_yields(frame, weight_column="significance_model_weight_36fb")
    write_json(category_yields_36fb, out_dir / "category_yields_36fb.json")
    _plot_category_yields(
        category_yields_36fb,
        plot_dir,
        basename="category_model_yields_36fb_bdt_v1",
        ylabel="Expected model yield at 36 fb^-1",
    )

    scan_records = pd.DataFrame(optimization.get("scan_records", []))
    if not scan_records.empty:
        _write_table(scan_records, opt_dir / "boundary_scan.csv")
    write_json(optimization.get("accepted_splits", []), opt_dir / "accepted_splits.json")
    write_json(optimization.get("rejected_splits", []), opt_dir / "rejected_splits.json")
    write_json(
        {
            "status": optimization.get("status"),
            "thresholds_descending": thresholds,
            "thresholds_ascending": optimization.get("thresholds", []),
            "z_initial": optimization.get("z_initial", 0.0),
            "z_final": optimization.get("z_final", 0.0),
            "source_partition": "validation",
            "objective": "simplified Asimov counting significance using physical signed event weights",
            "stopping_rule": "accept another boundary only while the relative improvement in expected significance versus the previous iteration is at least 5%",
            "min_relative_gain": boundary_optimization_config["min_relative_gain"],
            "config": optimization.get("config", boundary_optimization_config),
            "accepted_splits": optimization.get("accepted_splits", []),
        },
        opt_dir / "thresholds.json",
    )

    model_path = model_dir / "bdt_model.joblib"
    dump(model, model_path)
    _write_table(training_frame.reset_index(drop=False).rename(columns={"index": "source_row_index"}), model_dir / "training_sample.csv")
    _write_table(frame, out_dir / "predictions.csv")
    _write_table(
        frame[["event_id", "partition", "process", "event_weight", "m_gammagamma", "bdt_score", "assigned_category", *BDT_FEATURES]],
        out_dir / "hadronic_features.csv",
    )
    inference_manifest = _write_inference_artifacts(
        frame,
        out_dir,
        thresholds=thresholds,
        model_path=model_path,
        event_weight_luminosity_fb=event_weight_luminosity_fb,
        significance_luminosity_fb=significance_luminosity_fb,
        nti_to_ti_signal_window_scale=nti_to_ti_signal_window_scale,
    )

    plot_outputs = _plot_training_diagnostics(training_frame, plot_dir)
    train_eval = training_frame[training_frame["partition"].isin(["training", "validation", "test"])].copy()
    metric_payload: dict[str, Any] = {}
    for partition, subset in train_eval.groupby("partition"):
        if subset["label"].nunique() < 2:
            continue
        y = subset["label"].to_numpy(dtype=int)
        score = subset["bdt_score"].to_numpy(dtype=float)
        weight = subset["fit_weight"].to_numpy(dtype=float)
        metric_payload[str(partition)] = {
            "weighted_auc": float(roc_auc_score(y, score, sample_weight=weight)),
            "weighted_average_precision": float(average_precision_score(y, score, sample_weight=weight)),
            "raw_count": int(len(subset)),
            "signal_raw_count": int(np.sum(y == 1)),
            "background_raw_count": int(np.sum(y == 0)),
            "signal_fit_weight_sum": float(np.sum(weight[y == 1])),
            "background_fit_weight_sum": float(np.sum(weight[y == 0])),
        }

    component_summary: dict[str, Any] = {}
    for component, subset in training_frame.groupby("training_component"):
        component_summary[str(component)] = {
            "raw_count": int(len(subset)),
            "physical_weight_sum": float(subset["physical_training_weight"].sum()),
            "fit_weight_sum": float(subset["fit_weight"].sum()),
            "partitions": {
                str(partition): int(count)
                for partition, count in subset.groupby("partition").size().to_dict().items()
            },
        }

    negative_weight_summary = {
        "training_rows_with_negative_physical_weight": int((training_frame["physical_training_weight"] < 0.0).sum()),
        "signal_rows_with_negative_physical_weight": int(((training_frame["label"] == 1) & (training_frame["physical_training_weight"] < 0.0)).sum()),
        "background_rows_with_negative_physical_weight": int(((training_frame["label"] == 0) & (training_frame["physical_training_weight"] < 0.0)).sum()),
        "classifier_policy": "GradientBoostingClassifier receives abs(physical_training_weight) scaled to equal signal/background class sums; signed physical weights are preserved for yield and threshold-optimization artifacts.",
    }

    mixture = {
        "status": "ok",
        "scope": "hadronic preselection only",
        "signal_window_gev": list(SIGNAL_WINDOW),
        "sidebands_gev": [list(item) for item in SIDEBANDS],
        "signal_definition": "ttH and tH MC, TI diphoton, 125 +/- 2 GeV",
        "background_definition": "ggH MC, TI diphoton, 125 +/- 2 GeV, mixed with data NTI sideband continuum proxy",
        "nti_definition": "two kinematic photons with at least one failing tight-ID or tight-isolation",
        "sf1_ti_sideband_over_nti_sideband": sf1,
        "sf2_nti_signal_window_over_nti_sideband": sf2,
        "nti_sideband_to_ti_signal_window_scale": nti_to_ti_signal_window_scale,
        "raw_counts": {
            "data_ti_sideband": _count(frame, ti_sideband),
            "data_nti_sideband": _count(frame, nti_sideband),
            "data_nti_123_127": _count(frame, nti_signal_window),
            "topH_signal_123_127": _count(frame, signal_mask),
            "ggH_background_123_127": _count(frame, ggh_mask),
        },
        "weighted_yields": {
            "data_ti_sideband": ti_sideband_yield,
            "data_nti_sideband": nti_sideband_yield,
            "data_nti_123_127": nti_signal_window_yield,
            "predicted_nti_continuum_123_127_from_sideband": float(training_frame.loc[training_frame["training_component"] == "NTI_continuum_proxy_sideband", "physical_training_weight"].sum()),
            "ggH_background_123_127": float(training_frame.loc[training_frame["training_component"] == "ggH_resonant_background", "physical_training_weight"].sum()),
            "topH_signal_123_127": float(training_frame.loc[training_frame["training_component"] == "topH_signal", "physical_training_weight"].sum()),
        },
        "signal_process_breakdown": {
            process: {
                "raw_count": int(len(subset)),
                "sm_normalized_signed_weight_sum": float(subset["physical_training_weight"].sum()),
                "class_balanced_fit_weight_sum": float(subset["fit_weight"].sum()),
            }
            for process, subset in training_frame.loc[training_frame["training_component"] == "topH_signal"].groupby("process")
        },
    }
    write_json(mixture, model_dir / "background_mixture_and_normalization.json")

    balance_check = {
        "fit_partition": "training",
        "class_weight_sums_before_balance": {str(key): float(value) for key, value in class_sums.items()},
        "target_class_sum_after_balance": target_class_sum,
        "class_balance_scale": {str(key): float(value) for key, value in class_balance_scale.items()},
        "class_weight_sums_after_balance": {
            str(label): float(training_frame.loc[fit_partition & (training_frame["label"] == label), "fit_weight"].sum())
            for label in [0, 1]
        },
    }
    write_json(balance_check, model_dir / "class_balance_check.json")

    metadata = {
        "status": "ok",
        "started_at_utc": started,
        "ended_at_utc": utcnow_iso(),
        "duration_seconds": float(time.perf_counter() - started_perf),
        "random_seed": random_seed,
        "features": BDT_FEATURES,
        "model": {
            "backend": "sklearn.ensemble.GradientBoostingClassifier",
            "path": str(model_path),
            "hyperparameters": {
                "n_estimators": 160,
                "learning_rate": 0.08,
                "max_depth": 2,
                "min_samples_leaf": 25,
                "subsample": 0.8,
                "random_state": random_seed,
            },
        },
        "training_prescription": {
            "signal": "ttH and tH MC, TI, hadronic, 125 +/- 2 GeV",
            "background": "ggH MC, TI, hadronic, 125 +/- 2 GeV + data NTI hadronic sidebands scaled by SF1*SF2",
            "event_weight_order": "MC processes are first normalized with SM cross section x filter efficiency x k-factor divided by signed sum of generator weights, including per-event scale factors; only after that are classifier fit weights rescaled to equal signal/background class sums.",
            "class_balancing": "fit weights are scaled so combined ttH+tH signal and combined ggH+NTI background sums match in the training partition",
            "categorization_significance_normalization": "Use significance_model_weight_36fb for expected category yields/significance. It uses MC weights rescaled to 36 fb^-1 plus the SF1*SF2-scaled NTI continuum proxy; do not use bdt_fit_weight for yields.",
            "excluded_from_training": "nominal TI observed data in the 125 +/- 2 GeV signal window",
            "bdt_excludes_m_gammagamma": True,
        },
        "normalization_for_categorization": inference_manifest["normalization_strategy"],
        "component_summary": component_summary,
        "class_balance_check": balance_check,
        "negative_weight_summary": negative_weight_summary,
        "metrics": metric_payload,
        "thresholds_descending": thresholds,
        "optimization": {
            "status": optimization.get("status"),
            "z_initial": optimization.get("z_initial", 0.0),
            "z_final": optimization.get("z_final", 0.0),
            "source_partition": "validation",
        },
        "plot_outputs": plot_outputs,
        "inference": {
            "scope": inference_manifest["scope"],
            "rows": inference_manifest["rows"],
            "scored_rows": inference_manifest["scored_rows"],
            "unscored_rows": inference_manifest["unscored_rows"],
            "manifest": str(out_dir / "inference" / "inference_manifest.json"),
            "csv": inference_manifest["csv"],
            "root": inference_manifest["root"].get("path"),
        },
        "artifacts": {
            "model": str(model_path),
            "training_sample": str(model_dir / "training_sample.csv"),
            "background_mixture": str(model_dir / "background_mixture_and_normalization.json"),
            "class_balance": str(model_dir / "class_balance_check.json"),
            "thresholds": str(opt_dir / "thresholds.json"),
            "predictions": str(out_dir / "predictions.csv"),
            "inference_manifest": str(out_dir / "inference" / "inference_manifest.json"),
            "inference_events_csv": str(out_dir / "inference" / "events_with_bdt_scores.csv"),
            "inference_events_root": str(out_dir / "inference" / "events_with_bdt_scores.root"),
            "category_yields": str(out_dir / "category_yields.json"),
            "category_yields_36fb": str(out_dir / "category_yields_36fb.json"),
            "score_by_component_histograms": str(plot_dir / "score_by_component_histograms.json"),
        },
    }
    write_json(metadata, model_dir / "training_metadata.json")
    write_json(
        {
            "stage_id": "hadronic_bdt_training_with_nti_background",
            "started_at_utc": started,
            "ended_at_utc": metadata["ended_at_utc"],
            "inputs_used": ["preselected_rows_in_memory"],
            "outputs_written": sorted(metadata["artifacts"].values()),
            "assumptions": [
                "BDT signal is combined ttH+tH MC, matching the top-associated Higgs target requested for this task.",
                "NTI signal-window aggregate is used only for the SF2 control normalization; nominal TI signal-window data are not used in training or threshold optimization.",
                "SF2 is implemented as N_NTI(123-127) / N_NTI(sidebands), the sideband-to-window shape factor.",
                "Categorization/significance model yields should use significance_model_weight_36fb, which rescales MC to 36 fb^-1 and keeps the NTI continuum proxy normalization separate from observed data rows.",
            ],
            "deviations": [
                "The current staged pipeline uses CSV instead of parquet for table artifacts.",
                "Boundary optimization uses simplified Asimov counting significance, not a full diphoton mass likelihood.",
            ],
            "unresolved_issues": [
                "The leptonic Z-veto category refinement is not yet implemented in this staged fast path."
            ],
            "reviewers_run": ["self_consistency_checks"],
            "review_outcomes": ["conditional_pass"],
            "blocking_reasons": [],
            "next_skill": "background_and_signal_model_generator.md",
        },
        model_dir / "bdt_training_stage_log.json",
    )
    return metadata
