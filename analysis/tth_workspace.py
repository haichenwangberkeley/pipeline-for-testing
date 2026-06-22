from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
import ROOT

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.common import ensure_dir, read_json, stable_hash, utcnow_iso, write_json
from analysis.stats.fit import FIT_ID
from analysis.stats.models import (
    MASS_RANGE_GEV,
    background_candidate,
    configure_mass_var,
    fit_pdf,
    histogram_counts,
    make_weighted_bin_center_dataset,
    make_weighted_dataset,
    pdf_to_counts,
)
from analysis.tth_categorization import RESONANT_BACKGROUND_PROCESSES, SIGNAL_PROCESSES

ROOT.gROOT.SetBatch(True)
ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)

HADRONIC_CATEGORY_ORDER = [
    "ttH_had_BDT1",
    "ttH_had_BDT2",
    "ttH_had_BDT3",
    "ttH_had_BDT4",
    "tH_had_4j1b",
    "tH_had_4j2b",
]
WORKSPACE_CATEGORY_ORDER = [*HADRONIC_CATEGORY_ORDER, "unassigned"]
MASS_BINS = np.linspace(105.0, 160.0, 56)
SIDE_BAND_RANGES = [(105.0, 120.0), (130.0, 160.0)]
SIGNAL_WINDOW = (123.0, 127.0)
COMPONENT_LABELS = {
    "topH_signal": "ttH+tH signal",
    "resonant_higgs_background": "resonant Higgs background",
    "TI_sideband_continuum": "TI-sideband continuum",
}
COMPONENT_COLORS = {
    "topH_signal": "#005f73",
    "resonant_higgs_background": "#0a9396",
    "TI_sideband_continuum": "#ca6702",
    "total": "#222222",
}
WORKSPACE_COMPONENT_ORDER = [
    "topH_signal",
    "resonant_higgs_background",
    "TI_sideband_continuum",
]


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _as_float(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").astype(float)


def _is_sideband(values: pd.Series) -> pd.Series:
    masses = pd.to_numeric(values, errors="coerce").astype(float)
    return ((masses >= 105.0) & (masses < 120.0)) | ((masses > 130.0) & (masses <= 160.0))


def _is_fit_range(values: pd.Series) -> pd.Series:
    masses = pd.to_numeric(values, errors="coerce").astype(float)
    return (masses >= MASS_RANGE_GEV[0]) & (masses <= MASS_RANGE_GEV[1])


def _write_figure(fig: plt.Figure, base: Path) -> list[str]:
    ensure_dir(base.parent)
    out = []
    for suffix in [".png", ".pdf"]:
        path = base.with_suffix(suffix)
        fig.savefig(path, dpi=160 if suffix == ".png" else None, bbox_inches="tight")
        out.append(str(path))
    plt.close(fig)
    return out


def _load_inference_frame(inference_table: Path, retention_json: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_csv(inference_table, low_memory=False)
    for column in [
        "m_gammagamma",
        "mc_event_weight_36fb",
        "observed_data_weight",
        "nti_continuum_proxy_weight",
        "significance_model_weight_36fb",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)

    retention = read_json(retention_json) if retention_json.exists() else {"removed_categories": []}
    removed = set(str(value) for value in retention.get("removed_categories", []))
    frame = frame[frame["preselection_channel"].astype(str) == "hadronic"].copy()
    frame["workspace_category"] = frame["assigned_category"].astype(str)
    if removed:
        frame.loc[frame["workspace_category"].isin(removed), "workspace_category"] = "unassigned"
    frame.loc[~frame["workspace_category"].isin(WORKSPACE_CATEGORY_ORDER), "workspace_category"] = "unassigned"
    return frame, retention


def _positive_hist_counts(masses: np.ndarray, weights: np.ndarray, *, bins: int = 55) -> np.ndarray:
    counts = histogram_counts(masses, weights, bins=bins)
    counts = np.nan_to_num(counts, nan=0.0, posinf=0.0, neginf=0.0)
    counts = np.clip(counts, 0.0, None)
    if counts.sum() <= 0.0 and len(masses):
        counts = histogram_counts(masses, None, bins=bins)
        counts = np.clip(counts, 0.0, None)
    if counts.sum() <= 0.0:
        centers = np.linspace(105.5, 159.5, bins)
        counts = np.exp(-0.5 * ((centers - 125.0) / 1.8) ** 2)
    floor = max(float(np.sum(counts)) * 1.0e-8 / float(bins), 1.0e-12)
    counts = counts + floor
    return counts.astype(float)


def _hist_pdf(name: str, mass_var, counts: np.ndarray):
    counts = np.asarray(counts, dtype=float)
    datahist = ROOT.RooDataHist.from_numpy(
        counts,
        [mass_var],
        bins=[len(counts)],
        ranges=[(105.0, 160.0)],
        weights_squared_sum=np.clip(counts, 0.0, None),
        name=f"dh_{name}",
    )
    pdf = ROOT.RooHistPdf(f"pdf_{name}", f"pdf_{name}", ROOT.RooArgSet(mass_var), datahist)
    return pdf, datahist


def _weighted_sum(values: pd.Series) -> float:
    total = float(pd.to_numeric(values, errors="coerce").fillna(0.0).sum())
    return total if math.isfinite(total) else 0.0


def _component_payload(frame: pd.DataFrame, category: str) -> dict[str, Any] | None:
    category_frame = frame[frame["workspace_category"] == category]
    if category_frame.empty:
        return None

    process = category_frame["process"].astype(str)
    is_ti = _bool_series(category_frame["is_ti_diphoton"])
    is_nti = _bool_series(category_frame["is_nti_diphoton"])
    fit_range = _is_fit_range(category_frame["m_gammagamma"])
    sideband = _is_sideband(category_frame["m_gammagamma"])
    is_data = process == "data"

    signal = category_frame[process.isin(SIGNAL_PROCESSES) & is_ti & fit_range].copy()
    resonant = category_frame[process.isin(RESONANT_BACKGROUND_PROCESSES) & is_ti & fit_range].copy()
    nti_sideband = category_frame[is_data & is_nti & sideband].copy()
    ti_sideband = category_frame[is_data & is_ti & sideband].copy()

    if signal.empty or ti_sideband.empty:
        return None

    nti_sideband_count = int(len(nti_sideband))
    ti_sideband_count = int(len(ti_sideband))

    return {
        "category": category,
        "frame": category_frame,
        "signal_masses": signal["m_gammagamma"].to_numpy(dtype=float),
        "signal_weights": signal["mc_event_weight_36fb"].to_numpy(dtype=float),
        "resonant_masses": resonant["m_gammagamma"].to_numpy(dtype=float),
        "resonant_weights": resonant["mc_event_weight_36fb"].to_numpy(dtype=float),
        "ti_sideband_masses": ti_sideband["m_gammagamma"].to_numpy(dtype=float),
        "ti_sideband_weights": np.ones(ti_sideband_count, dtype=float),
        "ti_sideband_count": ti_sideband_count,
        "nti_sideband_count": nti_sideband_count,
        "continuum_shape_source": "observed_ti_data_sidebands",
        "continuum_normalization_source": "observed_ti_data_sideband_count",
        "signal_yield_full_range_36fb": _weighted_sum(signal["mc_event_weight_36fb"]),
        "resonant_yield_full_range_36fb": _weighted_sum(resonant["mc_event_weight_36fb"]) if not resonant.empty else 0.0,
    }


def _sideband_fraction(pdf, mass_var, *, bins: int = 55) -> float:
    unit = pdf_to_counts(pdf, mass_var, 1.0, bins=bins)
    centers = np.linspace(105.5, 159.5, bins)
    side = ((centers >= 105.0) & (centers < 120.0)) | ((centers > 130.0) & (centers <= 160.0))
    fraction = float(np.sum(unit[side]))
    return fraction if math.isfinite(fraction) and fraction > 1.0e-9 else 1.0


def _fit_continuum(category: str, mass_var, payload: dict[str, Any]) -> tuple[dict[str, Any], Any, list]:
    masses = payload["ti_sideband_masses"]
    weights = payload["ti_sideband_weights"]
    dataset = make_weighted_dataset(f"ti_side_{category}", mass_var, masses)
    candidates = []
    for kind in ["exponential", "bernstein2", "bernstein3"]:
        model = background_candidate(f"cont_{category}", mass_var, kind)
        result = fit_pdf(model.pdf, dataset, fit_range="sideband_lo,sideband_hi", weighted=False)
        nll = float(result.minNll()) if math.isfinite(float(result.minNll())) else float("inf")
        aic = 2.0 * len(model.params) + 2.0 * nll
        candidate = {
            "category": category,
            "model": kind,
            "complexity": model.complexity,
            "fit_status": int(result.status()),
            "cov_qual": int(result.covQual()),
            "sideband_aic": float(aic),
            "param_snapshot": {param.GetName(): float(param.getVal()) for param in model.params},
        }
        candidates.append((candidate, model))

    valid = [
        (candidate, model)
        for candidate, model in candidates
        if candidate["fit_status"] == 0 and candidate["cov_qual"] >= 2 and math.isfinite(candidate["sideband_aic"])
    ]
    if not valid:
        valid = [(candidate, model) for candidate, model in candidates if math.isfinite(candidate["sideband_aic"])]
    if not valid:
        valid = candidates
    valid.sort(key=lambda item: (item[0]["sideband_aic"], item[0]["complexity"], item[0]["model"]))
    selected, selected_model = valid[0]
    selected = dict(selected)
    selected["selected"] = True
    for candidate, _ in candidates:
        candidate["selected"] = candidate["model"] == selected["model"]
    sideband_yield = float(np.sum(weights))
    sideband_fraction = _sideband_fraction(selected_model.pdf, mass_var)
    full_range_yield = sideband_yield / sideband_fraction
    choice = {
        "status": "ok",
        "category": category,
        "selected_model": selected["model"],
        "selected_complexity": selected["complexity"],
        "selection_rule": "minimum AIC among observed TI sideband fits with acceptable RooFit status/covariance when available",
        "sideband_fit_status": selected["fit_status"],
        "sideband_cov_qual": selected["cov_qual"],
        "sideband_aic": selected["sideband_aic"],
        "sideband_param_snapshot": selected["param_snapshot"],
        "sideband_fit_yield": sideband_yield,
        "sideband_observed_ti_yield": sideband_yield,
        "sideband_fraction_of_full_pdf": sideband_fraction,
        "continuum_full_range_yield_36fb": full_range_yield,
        "continuum_normalization_source": payload["continuum_normalization_source"],
        "continuum_shape_source": payload["continuum_shape_source"],
        "observed_ti_sideband_count": payload["ti_sideband_count"],
        "observed_nti_sideband_count": payload["nti_sideband_count"],
    }
    scan = {
        "status": "ok",
        "category": category,
        "template_source": "observed TI data sidebands",
        "sidebands_gev": [list(item) for item in SIDE_BAND_RANGES],
        "candidates": [candidate for candidate, _ in candidates],
    }
    return {"scan": scan, "choice": choice}, selected_model.pdf, selected_model.params


def _restore_background_params(params: list, snapshot: dict[str, float]) -> None:
    for param in params:
        if param.GetName() in snapshot:
            param.setVal(float(snapshot[param.GetName()]))
        param.setConstant(False)


def _fit_with_mu(fit_context: dict[str, Any], dataset, *, mu_value: float | None):
    shared_mu = fit_context["shared_mu"]
    if mu_value is None:
        shared_mu.setConstant(False)
    else:
        shared_mu.setVal(float(mu_value))
        shared_mu.setConstant(True)
    return fit_context["simultaneous"].fitTo(
        dataset,
        ROOT.RooFit.Save(True),
        ROOT.RooFit.PrintLevel(-1),
        ROOT.RooFit.Strategy(1),
        ROOT.RooFit.SumW2Error(False),
        ROOT.RooFit.Extended(True),
        ROOT.RooFit.Range("full"),
    )


def _snapshot_state(fit_context: dict[str, Any]) -> dict[str, Any]:
    out = {
        "mu": float(fit_context["shared_mu"].getVal()),
        "mu_error": float(fit_context["shared_mu"].getError()),
        "mu_constant": bool(fit_context["shared_mu"].isConstant()),
        "categories": {},
    }
    for category, model in fit_context["final_models"].items():
        out["categories"][category] = {
            "ncont": float(model["ncont"].getVal()),
            "ncont_error": float(model["ncont"].getError()),
            "ncont_constant": bool(model["ncont"].isConstant()),
            "background_params": {param.GetName(): float(param.getVal()) for param in model["continuum_params"]},
        }
    return out


def _restore_state(fit_context: dict[str, Any], snapshot: dict[str, Any]) -> None:
    fit_context["shared_mu"].setVal(snapshot["mu"])
    fit_context["shared_mu"].setError(snapshot["mu_error"])
    fit_context["shared_mu"].setConstant(snapshot["mu_constant"])
    for category, model in fit_context["final_models"].items():
        cat = snapshot["categories"].get(category, {})
        model["ncont"].setVal(cat.get("ncont", model["ncont"].getVal()))
        model["ncont"].setError(cat.get("ncont_error", model["ncont"].getError()))
        model["ncont"].setConstant(cat.get("ncont_constant", False))
        _restore_background_params(model["continuum_params"], cat.get("background_params", {}))


def _generation_setup(fit_context: dict[str, Any]) -> None:
    fit_context["shared_mu"].setVal(1.0)
    fit_context["shared_mu"].setConstant(False)
    for category, model in fit_context["final_models"].items():
        choice = fit_context["category_context"][category]["background_choice"]
        _restore_background_params(model["continuum_params"], choice["sideband_param_snapshot"])
        model["ncont"].setVal(float(choice["continuum_full_range_yield_36fb"]))
        model["ncont"].setConstant(False)


def _model_counts(fit_context: dict[str, Any]) -> dict[str, dict[str, list[float]]]:
    counts: dict[str, dict[str, list[float]]] = {}
    mass_var = fit_context["common_mass"]
    for category, model in fit_context["final_models"].items():
        signal = pdf_to_counts(model["signal_pdf"], mass_var, float(model["nsig"].getVal()))
        resonant = pdf_to_counts(model["resonant_pdf"], mass_var, float(model["nres"].getVal()))
        continuum = pdf_to_counts(model["continuum_pdf"], mass_var, float(model["ncont"].getVal()))
        total = signal + resonant + continuum
        counts[category] = {
            "signal_counts": signal.tolist(),
            "resonant_higgs_background_counts": resonant.tolist(),
            "continuum_background_counts": continuum.tolist(),
            "background_counts": (resonant + continuum).tolist(),
            "total_counts": total.tolist(),
        }
    return counts


def _combined_counts(category_counts: dict[str, dict[str, list[float]]]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    keys = [
        "signal_counts",
        "resonant_higgs_background_counts",
        "continuum_background_counts",
        "background_counts",
        "total_counts",
    ]
    for key in keys:
        if category_counts:
            out[key] = [
                sum(float(payload[key][idx]) for payload in category_counts.values())
                for idx in range(55)
            ]
        else:
            out[key] = [0.0] * 55
    return out


def _build_asimov_dataset(fit_context: dict[str, Any]):
    _generation_setup(fit_context)
    common_mass = fit_context["common_mass"]
    channel = fit_context["channel"]
    category_counts = _model_counts(fit_context)
    import_map = {
        category: make_weighted_bin_center_dataset(
            f"asimov_{category}",
            common_mass,
            np.asarray(payload["total_counts"], dtype=float),
        )
        for category, payload in category_counts.items()
    }
    dataset = ROOT.RooDataSet(
        "asimovData",
        "asimovData",
        ROOT.RooArgSet(common_mass, channel),
        Index=channel,
        Import=import_map,
    )
    return dataset, category_counts


def _plot_safe_category(category: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in category)


def _write_sideband_plot(category_context: dict[str, Any], plot_dir: Path) -> list[str]:
    fig, ax = plt.subplots(figsize=(8.2, 5.4))
    centers = 0.5 * (MASS_BINS[:-1] + MASS_BINS[1:])
    total_side = np.zeros(55, dtype=float)
    total_fit = np.zeros(55, dtype=float)
    for category, ctx in category_context.items():
        masses = ctx["component_payload"]["ti_sideband_masses"]
        weights = ctx["component_payload"]["ti_sideband_weights"]
        side_counts, _ = np.histogram(masses, bins=MASS_BINS, weights=weights)
        fit_counts = np.asarray(ctx["generation_counts"]["continuum_background_counts"], dtype=float)
        total_side += side_counts
        total_fit += fit_counts
    side_mask = ((centers >= 105.0) & (centers < 120.0)) | ((centers > 130.0) & (centers <= 160.0))
    ax.errorbar(
        centers[side_mask],
        total_side[side_mask],
        yerr=np.sqrt(np.clip(total_side[side_mask], 0.0, None)),
        fmt="o",
        color="black",
        markersize=4,
        label="observed TI sidebands",
    )
    ax.step(MASS_BINS, np.r_[total_fit, total_fit[-1]], where="post", color=COMPONENT_COLORS["total"], linewidth=1.8, label="continuum fit")
    ax.axvspan(SIGNAL_WINDOW[0], SIGNAL_WINDOW[1], color="#bbbbbb", alpha=0.18, label="blinded TI signal window")
    ax.set_xlim(105.0, 160.0)
    ax.set_xlabel("m_gammagamma [GeV]")
    ax.set_ylabel("Events / 1 GeV")
    ax.set_title("Hadronic TI Sideband Fit")
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    return _write_figure(fig, plot_dir / "sidebands_background_fit")


def _sideband_plot_arrays(ctx: dict[str, Any]) -> dict[str, Any]:
    centers = 0.5 * (MASS_BINS[:-1] + MASS_BINS[1:])
    masses = ctx["component_payload"]["ti_sideband_masses"]
    weights = ctx["component_payload"]["ti_sideband_weights"]
    observed_counts, _ = np.histogram(masses, bins=MASS_BINS, weights=weights)
    fit_counts = np.asarray(ctx["generation_counts"]["continuum_background_counts"], dtype=float)
    side_mask = ((centers >= 105.0) & (centers < 120.0)) | ((centers > 130.0) & (centers <= 160.0))
    ratio = np.full_like(observed_counts, np.nan, dtype=float)
    ratio_error = np.full_like(observed_counts, np.nan, dtype=float)
    valid = side_mask & (fit_counts > 0.0)
    ratio[valid] = observed_counts[valid] / fit_counts[valid]
    ratio_error[valid] = np.sqrt(np.clip(observed_counts[valid], 0.0, None)) / fit_counts[valid]
    return {
        "centers": centers,
        "observed_counts": observed_counts,
        "fit_counts": fit_counts,
        "side_mask": side_mask,
        "ratio": ratio,
        "ratio_error": ratio_error,
    }


def _write_category_sideband_fit_plot(category: str, ctx: dict[str, Any], plot_dir: Path) -> dict[str, Any]:
    arrays = _sideband_plot_arrays(ctx)
    centers = arrays["centers"]
    observed_counts = arrays["observed_counts"]
    fit_counts = arrays["fit_counts"]
    side_mask = arrays["side_mask"]
    ratio = arrays["ratio"]
    ratio_error = arrays["ratio_error"]

    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(8.2, 6.2),
        sharex=True,
        gridspec_kw={"height_ratios": [3.0, 1.0], "hspace": 0.06},
    )
    yerr = np.sqrt(np.clip(observed_counts[side_mask], 0.0, None))
    ax.errorbar(
        centers[side_mask],
        observed_counts[side_mask],
        yerr=yerr,
        fmt="o",
        color="black",
        markersize=4,
        label="observed TI sidebands",
    )
    ax.step(
        MASS_BINS,
        np.r_[fit_counts, fit_counts[-1]],
        where="post",
        color=COMPONENT_COLORS["total"],
        linewidth=1.8,
        label="continuum fit",
    )
    ax.axvspan(SIGNAL_WINDOW[0], SIGNAL_WINDOW[1], color="#bbbbbb", alpha=0.18, label="blinded TI signal window")
    ymax = float(max(np.max(fit_counts), np.max(observed_counts[side_mask] + yerr) if np.any(side_mask) else 0.0, 1.0))
    ax.set_ylim(0.0, 1.25 * ymax)
    ax.set_ylabel("Events / 1 GeV")
    ax.set_title(f"{category} TI Sideband Fit")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.2)

    valid_ratio = side_mask & np.isfinite(ratio) & np.isfinite(ratio_error)
    rax.errorbar(
        centers[valid_ratio],
        ratio[valid_ratio],
        yerr=ratio_error[valid_ratio],
        fmt="o",
        color="black",
        markersize=4,
    )
    rax.axhline(1.0, color=COMPONENT_COLORS["total"], linewidth=1.2)
    rax.axvspan(SIGNAL_WINDOW[0], SIGNAL_WINDOW[1], color="#bbbbbb", alpha=0.18)
    finite_ratio_high = ratio[valid_ratio] + ratio_error[valid_ratio]
    ratio_upper = float(max(2.0, 1.15 * np.max(finite_ratio_high))) if len(finite_ratio_high) else 2.0
    rax.set_xlim(105.0, 160.0)
    rax.set_ylim(0.0, ratio_upper)
    rax.set_xlabel("m_gammagamma [GeV]")
    rax.set_ylabel("Data/Fit")
    rax.grid(True, alpha=0.2)
    fig.tight_layout()

    safe_category = _plot_safe_category(category)
    paths = _write_figure(fig, plot_dir / f"sidebands_background_fit_{safe_category}")
    return {
        "category": category,
        "paths": paths,
        "bin_edges": MASS_BINS.tolist(),
        "normalization": "absolute observed TI sideband counts; fitted continuum extrapolated over 105-160 GeV",
        "uncertainty": "Poisson statistical uncertainties on observed TI sideband counts; fitted-PDF uncertainty is not propagated",
        "ratio": "Data/Fit: observed TI sideband counts divided by fitted continuum expectation in sideband bins only",
        "ratio_ylim": [0.0, ratio_upper],
        "observed_counts": observed_counts.tolist(),
        "fit_counts": fit_counts.tolist(),
        "ratio_values": [None if not math.isfinite(value) else float(value) for value in ratio],
        "ratio_errors": [None if not math.isfinite(value) else float(value) for value in ratio_error],
    }


def _write_category_sideband_fit_plots(category_context: dict[str, Any], plot_dir: Path) -> dict[str, Any]:
    categories = {
        category: _write_category_sideband_fit_plot(category, ctx, plot_dir)
        for category, ctx in sorted(category_context.items())
    }
    payload = {
        "status": "ok",
        "plot_type": "per-category observed TI sideband background fits",
        "observable": "m_gammagamma",
        "binning": {"n_bins": 55, "range": [105.0, 160.0], "bin_edges": MASS_BINS.tolist()},
        "sidebands_gev": [list(item) for item in SIDE_BAND_RANGES],
        "blinded_signal_window_gev": list(SIGNAL_WINDOW),
        "normalization": "absolute observed TI sideband counts; fitted continuum extrapolated over 105-160 GeV",
        "ratio_definition": "Data/Fit: observed TI sideband counts / fitted continuum expectation in sideband bins",
        "categories": categories,
    }
    write_json(payload, plot_dir.parent / "sideband_fit_plots.json")
    return payload


def _write_asimov_plot(plot_payload: dict[str, Any], plot_dir: Path) -> list[str]:
    combined = plot_payload["combined"]
    asimov = np.asarray(combined["asimov_counts"], dtype=float)
    free = np.asarray(combined["free_fit"]["total_counts"], dtype=float)
    signal = np.asarray(combined["generation_signal_counts"], dtype=float)
    resonant = np.asarray(combined["generation_resonant_higgs_background_counts"], dtype=float)
    continuum = np.asarray(combined["generation_continuum_background_counts"], dtype=float)
    centers = 0.5 * (MASS_BINS[:-1] + MASS_BINS[1:])
    fig, ax = plt.subplots(figsize=(8.2, 5.4))
    ax.errorbar(centers, asimov, yerr=np.sqrt(np.clip(asimov, 0.0, None)), fmt="o", color="black", markersize=4, label="Asimov S+B pseudo-data")
    ax.step(MASS_BINS, np.r_[free, free[-1]], where="post", color=COMPONENT_COLORS["total"], linewidth=2.0, label="free-mu S+B fit")
    ax.step(MASS_BINS, np.r_[continuum, continuum[-1]], where="post", color=COMPONENT_COLORS["TI_sideband_continuum"], linewidth=1.3, label="generated TI-sideband continuum")
    ax.step(MASS_BINS, np.r_[resonant, resonant[-1]], where="post", color=COMPONENT_COLORS["resonant_higgs_background"], linewidth=1.3, label="generated resonant Higgs bkg")
    ax.step(MASS_BINS, np.r_[signal, signal[-1]], where="post", color=COMPONENT_COLORS["topH_signal"], linewidth=1.5, label="generated ttH+tH signal")
    ax.set_xlim(105.0, 160.0)
    ax.set_xlabel("m_gammagamma [GeV]")
    ax.set_ylabel("Expected events / 1 GeV")
    ax.set_title("Hadronic Combined Asimov S+B Fit")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    return _write_figure(fig, plot_dir / "asimov_sb_fit")


def _plot_payload(
    *,
    asimov_counts: dict[str, dict[str, list[float]]],
    free_fit_counts: dict[str, dict[str, list[float]]],
    mu0_fit_counts: dict[str, dict[str, list[float]]],
    mu_hat: float,
    mu_uncertainty: float,
    free_result,
    mu0_result,
) -> dict[str, Any]:
    categories = {}
    for category, payload in asimov_counts.items():
        categories[category] = {
            "asimov_counts": payload["total_counts"],
            "generation_signal_counts": payload["signal_counts"],
            "generation_resonant_higgs_background_counts": payload["resonant_higgs_background_counts"],
            "generation_continuum_background_counts": payload["continuum_background_counts"],
            "generation_background_counts": payload["background_counts"],
            "free_fit": free_fit_counts[category],
            "mu0_fit": mu0_fit_counts[category],
        }
    combined_asimov = _combined_counts(asimov_counts)
    return {
        "status": "ok",
        "fit_id": FIT_ID,
        "dataset_type": "asimov",
        "generation_hypothesis": "signal_plus_background",
        "mu_gen": 1.0,
        "binning": {"observable": "m_gammagamma", "n_bins": 55, "range": [105.0, 160.0]},
        "categories": categories,
        "combined": {
            "asimov_counts": combined_asimov["total_counts"],
            "generation_signal_counts": combined_asimov["signal_counts"],
            "generation_resonant_higgs_background_counts": combined_asimov["resonant_higgs_background_counts"],
            "generation_continuum_background_counts": combined_asimov["continuum_background_counts"],
            "generation_background_counts": combined_asimov["background_counts"],
            "free_fit": _combined_counts(free_fit_counts),
            "mu0_fit": _combined_counts(mu0_fit_counts),
        },
        "free_fit": {
            "mu_hat": mu_hat,
            "mu_uncertainty": mu_uncertainty,
            "fit_status": int(free_result.status()),
            "cov_qual": int(free_result.covQual()),
        },
        "mu0_fit": {
            "mu_fixed": 0.0,
            "fit_status": int(mu0_result.status()),
            "cov_qual": int(mu0_result.covQual()),
        },
    }


def _build_model_context(category: str, mass_var, shared_mu, payload: dict[str, Any], continuum_pdf, continuum_params, choice: dict[str, Any]):
    signal_counts = _positive_hist_counts(payload["signal_masses"], payload["signal_weights"])
    resonant_counts = _positive_hist_counts(payload["resonant_masses"], payload["resonant_weights"])
    signal_pdf, signal_hist = _hist_pdf(f"sig_{category}", mass_var, signal_counts)
    resonant_pdf, resonant_hist = _hist_pdf(f"res_{category}", mass_var, resonant_counts)

    signal_yield = max(float(payload["signal_yield_full_range_36fb"]), 1.0e-9)
    resonant_yield = max(float(payload["resonant_yield_full_range_36fb"]), 0.0)
    continuum_yield = max(float(choice["continuum_full_range_yield_36fb"]), 1.0e-9)
    s_const = ROOT.RooRealVar(f"sconst_{category}", f"sconst_{category}", signal_yield)
    s_const.setConstant(True)
    nsig = ROOT.RooFormulaVar(f"nsig_{category}", "@0*@1", ROOT.RooArgList(shared_mu, s_const))
    nres = ROOT.RooRealVar(f"nres_{category}", f"nres_{category}", resonant_yield)
    nres.setConstant(True)
    ncont = ROOT.RooRealVar(
        f"ncont_{category}",
        f"ncont_{category}",
        continuum_yield,
        0.0,
        20.0 * max(continuum_yield + resonant_yield + signal_yield, 1.0),
    )
    model = ROOT.RooAddPdf(
        f"model_{category}",
        f"model_{category}",
        ROOT.RooArgList(signal_pdf, resonant_pdf, continuum_pdf),
        ROOT.RooArgList(nsig, nres, ncont),
    )
    return {
        "model": model,
        "signal_pdf": signal_pdf,
        "signal_hist": signal_hist,
        "resonant_pdf": resonant_pdf,
        "resonant_hist": resonant_hist,
        "continuum_pdf": continuum_pdf,
        "continuum_params": continuum_params,
        "nsig": nsig,
        "s_const": s_const,
        "nres": nres,
        "ncont": ncont,
        "background_choice": choice,
        "signal_shape_counts": signal_counts.tolist(),
        "resonant_shape_counts": resonant_counts.tolist(),
    }


def _create_workspace_file(fit_context: dict[str, Any], asimov_data, fit_dir: Path, fit_summary: dict[str, Any]) -> dict[str, Any]:
    workspace_root = fit_dir / "workspace.root"
    workspace = ROOT.RooWorkspace("w")
    getattr(workspace, "import")(fit_context["simultaneous"])
    getattr(workspace, "import")(asimov_data)
    try:
        model_config = ROOT.RooStats.ModelConfig("ModelConfig", workspace)
        model_config.SetPdf(fit_context["simultaneous"])
        model_config.SetParametersOfInterest(ROOT.RooArgSet(fit_context["shared_mu"]))
        model_config.SetObservables(ROOT.RooArgSet(fit_context["common_mass"], fit_context["channel"]))
        getattr(workspace, "import")(model_config)
        model_config_status = "ok"
    except Exception as exc:  # pragma: no cover - ROOT builds can vary RooStats availability
        model_config_status = f"not_imported: {exc}"
    workspace.writeToFile(str(workspace_root))
    payload = {
        "status": "ok",
        "fit_id": FIT_ID,
        "workspace_root": str(workspace_root),
        "workspace_hash": stable_hash(fit_summary),
        "backend": "pyroot_roofit",
        "dataset_type": "asimov",
        "model_config_status": model_config_status,
        "categories": fit_summary["categories"],
        "pdf": "simPdf",
        "dataset": "asimovData",
        "poi": "mu",
    }
    write_json(payload, fit_dir.parent / "workspace.json")
    return payload


def run_hadronic_workspace(
    inference_table: Path,
    output_dir: Path,
    *,
    retention_json: Path | None = None,
    mixture_json: Path | None = None,
) -> dict[str, Any]:
    started = utcnow_iso()
    output_dir = ensure_dir(output_dir)
    fit_dir = ensure_dir(output_dir / "fit" / FIT_ID)
    plot_dir = ensure_dir(fit_dir / "plots")
    retention_json = retention_json or output_dir / "categorization" / "category_retention.json"
    frame, retention = _load_inference_frame(inference_table, retention_json)

    common_mass = configure_mass_var("mgg")
    channel = ROOT.RooCategory("channel", "channel")
    shared_mu = ROOT.RooRealVar("mu", "mu", 1.0, -5.0, 10.0)
    simultaneous = ROOT.RooSimultaneous("simPdf", "simPdf", channel)

    category_context: dict[str, Any] = {}
    final_models: dict[str, Any] = {}
    background_scan = {"status": "ok", "categories": {}}
    background_choice = {"status": "ok", "categories": {}}
    signal_pdf = {"status": "ok", "categories": {}}
    resonant_pdf = {"status": "ok", "categories": {}}
    background_template_selection = {
        "status": "ok",
        "template_source": "observed TI data sidebands",
        "sidebands_gev": [list(item) for item in SIDE_BAND_RANGES],
        "normalization": "observed TI sideband count extrapolated to the full 105-160 GeV fit range using the fitted smooth PDF",
        "categories": {},
    }

    for category in WORKSPACE_CATEGORY_ORDER:
        payload = _component_payload(frame, category)
        if payload is None:
            continue
        fit_payload, continuum_pdf, continuum_params = _fit_continuum(category, common_mass, payload)
        choice = fit_payload["choice"]
        model_ctx = _build_model_context(category, common_mass, shared_mu, payload, continuum_pdf, continuum_params, choice)
        final_models[category] = model_ctx
        channel.defineType(category)
        simultaneous.addPdf(model_ctx["model"], category)
        category_context[category] = {
            "component_payload": payload,
            "background_choice": choice,
            "expected_signal_yield": float(model_ctx["s_const"].getVal()),
            "expected_resonant_higgs_background_yield": float(model_ctx["nres"].getVal()),
            "expected_continuum_background_yield": float(choice["continuum_full_range_yield_36fb"]),
            "template_total_yield": float(choice["continuum_full_range_yield_36fb"]),
        }
        background_scan["categories"][category] = fit_payload["scan"]
        background_choice["categories"][category] = choice
        signal_pdf["categories"][category] = {
            "shape": "RooHistPdf from ttH+tH TI MC in 105-160 GeV",
            "expected_yield_36fb": float(model_ctx["s_const"].getVal()),
            "raw_count": int(len(payload["signal_masses"])),
            "hist_counts": model_ctx["signal_shape_counts"],
        }
        resonant_pdf["categories"][category] = {
            "shape": "RooHistPdf from non-top Higgs TI MC in 105-160 GeV",
            "expected_yield_36fb": float(model_ctx["nres"].getVal()),
            "raw_count": int(len(payload["resonant_masses"])),
            "hist_counts": model_ctx["resonant_shape_counts"],
        }
        background_template_selection["categories"][category] = {
            "observed_ti_sideband_count": payload["ti_sideband_count"],
            "observed_nti_sideband_count": payload["nti_sideband_count"],
            "continuum_shape_source": payload["continuum_shape_source"],
            "continuum_normalization_source": choice["continuum_normalization_source"],
            "sideband_fit_yield": choice["sideband_fit_yield"],
            "sideband_fraction_of_full_pdf": choice["sideband_fraction_of_full_pdf"],
            "continuum_full_range_yield_36fb": choice["continuum_full_range_yield_36fb"],
            "selected_model": choice["selected_model"],
        }

    if not final_models:
        raise RuntimeError("No hadronic categories had enough signal and TI sideband entries to build a workspace.")

    fit_context = {
        "common_mass": common_mass,
        "channel": channel,
        "shared_mu": shared_mu,
        "simultaneous": simultaneous,
        "category_context": category_context,
        "final_models": final_models,
    }
    snapshot = _snapshot_state(fit_context)
    asimov_data, asimov_counts = _build_asimov_dataset(fit_context)
    for category, counts in asimov_counts.items():
        category_context[category]["generation_counts"] = counts

    shared_mu.setVal(1.0)
    free_result = _fit_with_mu(fit_context, asimov_data, mu_value=None)
    twice_nll_free = 2.0 * float(free_result.minNll())
    mu_hat = float(shared_mu.getVal())
    mu_uncertainty = float(shared_mu.getError())
    free_counts = _model_counts(fit_context)

    mu0_result = _fit_with_mu(fit_context, asimov_data, mu_value=0.0)
    twice_nll_mu0 = 2.0 * float(mu0_result.minNll())
    q0_raw = max(twice_nll_mu0 - twice_nll_free, 0.0)
    q0 = q0_raw if mu_hat > 0.0 else 0.0
    z_discovery = math.sqrt(q0)
    mu0_counts = _model_counts(fit_context)

    diagnostics = []
    if int(free_result.status()) != 0:
        diagnostics.append("Free-mu Asimov significance fit returned a non-zero RooFit status.")
    if int(mu0_result.status()) != 0:
        diagnostics.append("Mu=0 Asimov significance fit returned a non-zero RooFit status.")
    if int(free_result.covQual()) < 2:
        diagnostics.append("Free-mu Asimov significance fit covariance quality is below the acceptable threshold of 2.")
    if int(mu0_result.covQual()) < 2:
        diagnostics.append("Mu=0 Asimov significance fit covariance quality is below the acceptable threshold of 2.")
    if mu_hat <= 0.0:
        diagnostics.append("Best-fit signal strength is non-positive, so q0 is clipped to zero.")
    status = "ok" if not diagnostics else "warning"

    plot_payload = _plot_payload(
        asimov_counts=asimov_counts,
        free_fit_counts=free_counts,
        mu0_fit_counts=mu0_counts,
        mu_hat=mu_hat,
        mu_uncertainty=mu_uncertainty,
        free_result=free_result,
        mu0_result=mu0_result,
    )
    fit_summary = {
        "status": status,
        "fit_id": FIT_ID,
        "backend": "pyroot_roofit",
        "dataset_type": "asimov",
        "observed_data_used_in_fit": False,
        "mu_hat": mu_hat,
        "mu_uncertainty": mu_uncertainty,
        "min_nll": float(free_result.minNll()),
        "fit_status": int(free_result.status()),
        "cov_qual": int(free_result.covQual()),
        "categories": sorted(final_models.keys()),
        "shared_mu": True,
        "model": "mu*(ttH+tH signal) + fixed resonant-Higgs background + floating smooth TI-sideband continuum background",
        "expected_signal_yields": {
            category: ctx["expected_signal_yield"] for category, ctx in category_context.items()
        },
        "expected_resonant_higgs_background_yields": {
            category: ctx["expected_resonant_higgs_background_yield"] for category, ctx in category_context.items()
        },
        "expected_continuum_background_yields": {
            category: ctx["expected_continuum_background_yield"] for category, ctx in category_context.items()
        },
        "diagnostics": diagnostics,
        "notes": [
            "Hadronic-only combined workspace.",
            "Observed TI data in the 125 +/- 2 GeV signal window are not used.",
            "Continuum background shape and normalization are determined by fitting observed TI data sidebands.",
            "Central significance uses signal-plus-background Asimov pseudo-data with mu_gen = 1.",
        ],
    }
    workspace_json = _create_workspace_file(fit_context, asimov_data, fit_dir, fit_summary)
    sideband_plot_paths = _write_sideband_plot(category_context, plot_dir)
    category_sideband_plot_payload = _write_category_sideband_fit_plots(category_context, plot_dir)
    asimov_plot_paths = _write_asimov_plot(plot_payload, plot_dir)

    asimov_artifact = {
        "fit_id": FIT_ID,
        "status": status,
        "dataset_type": "asimov",
        "generation_hypothesis": "signal_plus_background",
        "mu_gen": 1.0,
        "backend": "pyroot_roofit",
        "poi_name": "signal_strength_mu",
        "mu_hat": mu_hat,
        "mu_uncertainty": mu_uncertainty,
        "twice_nll_mu0": twice_nll_mu0,
        "twice_nll_free": twice_nll_free,
        "q0": q0,
        "z_discovery": z_discovery,
        "fit_range": [105.0, 160.0],
        "categories": sorted(final_models.keys()),
        "shared_mu": True,
        "fit_status_free": int(free_result.status()),
        "fit_status_mu0": int(mu0_result.status()),
        "cov_qual_free": int(free_result.covQual()),
        "cov_qual_mu0": int(mu0_result.covQual()),
        "diagnostics": diagnostics,
        "model_components": WORKSPACE_COMPONENT_ORDER,
        "model": fit_summary["model"],
        "workspace_root": workspace_json["workspace_root"],
    }
    construction = {
        "fit_id": FIT_ID,
        "status": "ok",
        "dataset_type": "asimov",
        "generation_hypothesis": "signal_plus_background",
        "mu_gen": 1.0,
        "construction_mode": "weighted_bin_center_dataset",
        "binning": {"observable": "m_gammagamma", "n_bins": 55, "range": [105.0, 160.0]},
        "hadronic_only": True,
        "signal_component": "ttH+tH TI MC normalized to 36 fb^-1 over 105-160 GeV",
        "resonant_higgs_background_component": "ggH/VBF/WH/ZH/ggZH TI MC fixed background normalized to 36 fb^-1 over 105-160 GeV",
        "continuum_background_component": "observed TI data sidebands fitted with a smooth PDF and extrapolated over 105-160 GeV for Asimov generation",
        "category_payload": asimov_counts,
    }
    observed_blocked = {
        "fit_id": FIT_ID,
        "status": "blocked",
        "dataset_type": "observed",
        "backend": "pyroot_roofit",
        "observed_significance_allowed": False,
        "blind_window_in_observed_data": [123.0, 127.0],
        "categories": sorted(final_models.keys()),
        "error": "Observed significance is disabled by blinding policy; central claims use Asimov expected significance only.",
    }
    backend = {
        "status": "ok",
        "primary_backend": "pyroot_roofit",
        "configuration": {
            "statistical_model": fit_summary["model"],
            "analytic_background_families": {
                category: choice["selected_model"]
                for category, choice in background_choice["categories"].items()
            },
            "signal_shape": "RooHistPdf from top-Higgs MC",
            "resonant_higgs_background_shape": "RooHistPdf from non-top Higgs MC",
            "workspace": workspace_json["workspace_root"],
        },
    }
    parameter_policy = {
        "observed_significance_allowed": False,
        "explicit_unblinding_required": True,
        "explicit_unblinding_performed": False,
        "signal_strength_parameter": "mu",
        "signal_shape_parameter_policy": "fixed_from_topH_mc_histogram",
        "resonant_higgs_background_policy": "fixed MC shape and normalization",
        "continuum_background_parameter_policy": "floating shape and normalization initialized from observed TI sideband fit",
    }
    measurement_dataset = {
        "status": "ok",
        "dataset_type": "asimov",
        "generation_hypothesis": "signal_plus_background",
        "mu_gen": 1.0,
        "construction_mode": "weighted_bin_center_dataset",
        "categories": sorted(final_models.keys()),
    }
    manifest = {
        "status": status,
        "started_at_utc": started,
        "ended_at_utc": utcnow_iso(),
        "fit_id": FIT_ID,
        "input_table": str(inference_table),
        "hadronic_rows": int(len(frame)),
        "included_categories": sorted(final_models.keys()),
        "excluded_scope": "leptonic categories are excluded from the workspace",
        "retention_source": str(retention_json),
        "retention": retention,
        "asimov_expected_significance": z_discovery,
        "mu_hat": mu_hat,
        "mu_uncertainty": mu_uncertainty,
        "fit_status_free": int(free_result.status()),
        "fit_status_mu0": int(mu0_result.status()),
        "cov_qual_free": int(free_result.covQual()),
        "cov_qual_mu0": int(mu0_result.covQual()),
        "artifacts": {
            "workspace_root": workspace_json["workspace_root"],
            "workspace_json": str(output_dir / "fit" / "workspace.json"),
            "results": str(fit_dir / "results.json"),
            "significance_asimov": str(fit_dir / "significance_asimov.json"),
            "significance_asimov_construction": str(fit_dir / "significance_asimov_construction.json"),
            "significance_asimov_plot_payload": str(fit_dir / "significance_asimov_plot_payload.json"),
            "sideband_fit_plots": str(fit_dir / "sideband_fit_plots.json"),
            "sidebands_background_fit": sideband_plot_paths,
            "sidebands_background_fit_by_category": {
                category: payload["paths"]
                for category, payload in category_sideband_plot_payload["categories"].items()
            },
            "asimov_sb_fit": asimov_plot_paths,
        },
    }

    _restore_state(fit_context, snapshot)
    write_json(fit_summary, fit_dir / "results.json")
    write_json(asimov_artifact, fit_dir / "significance_asimov.json")
    write_json(construction, fit_dir / "significance_asimov_construction.json")
    write_json(plot_payload, fit_dir / "significance_asimov_plot_payload.json")
    write_json(observed_blocked, fit_dir / "significance.json")
    write_json(backend, fit_dir / "backend.json")
    write_json(background_scan, fit_dir / "background_pdf_scan.json")
    write_json(background_choice, fit_dir / "background_pdf_choice.json")
    write_json(background_template_selection, fit_dir / "background_template_selection.json")
    write_json(signal_pdf, fit_dir / "signal_pdf.json")
    write_json(resonant_pdf, fit_dir / "resonant_higgs_pdf.json")
    write_json(parameter_policy, fit_dir / "significance_parameter_policy.json")
    write_json(measurement_dataset, fit_dir / "measurement_dataset.json")
    write_json(manifest, output_dir / "workspace_manifest.json")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference-table", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--retention-json")
    parser.add_argument("--mixture-json")
    args = parser.parse_args()
    manifest = run_hadronic_workspace(
        Path(args.inference_table),
        Path(args.output_dir),
        retention_json=Path(args.retention_json) if args.retention_json else None,
        mixture_json=Path(args.mixture_json) if args.mixture_json else None,
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "z_discovery": manifest["asimov_expected_significance"],
                "mu_hat": manifest["mu_hat"],
                "mu_uncertainty": manifest["mu_uncertainty"],
                "categories": manifest["included_categories"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
