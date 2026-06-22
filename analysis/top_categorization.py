from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np


CATEGORY_ORDER = [
    "tH_lep_0fwd",
    "tH_lep_1fwd",
    "ttH_lep",
    "ttH_had_BDT1",
    "ttH_had_BDT2",
    "ttH_had_BDT3",
    "ttH_had_BDT4",
    "tH_had_4j1b",
    "tH_had_4j2b",
]

BDT_FEATURES = [
    "ht_jets",
    "m_all_jets",
    "n_jets",
    "n_central_jets",
    "n_btags",
]

FIXED_BDT_THRESHOLDS = [0.92, 0.83, 0.79, 0.52]
Z_MASS_GEV = 91.1876


@dataclass(frozen=True)
class Interval:
    low: float
    high: float

    def contains(self, score: float) -> bool:
        return self.low < score <= self.high

    def as_dict(self) -> dict[str, float]:
        return {"low": self.low, "high": self.high}


def _px(pt: float, phi: float) -> float:
    return float(pt) * math.cos(float(phi))


def _py(pt: float, phi: float) -> float:
    return float(pt) * math.sin(float(phi))


def _pz(pt: float, eta: float) -> float:
    return float(pt) * math.sinh(float(eta))


def invariant_mass(objects: Iterable[dict[str, Any]]) -> float:
    """Return the invariant mass of objects with pt/eta/phi/e or px/py/pz/e."""
    energy = 0.0
    px = 0.0
    py = 0.0
    pz = 0.0
    for obj in objects:
        energy += float(obj.get("e", obj.get("energy", 0.0)))
        if {"px", "py", "pz"}.issubset(obj):
            px += float(obj["px"])
            py += float(obj["py"])
            pz += float(obj["pz"])
        else:
            px += _px(float(obj["pt"]), float(obj["phi"]))
            py += _py(float(obj["pt"]), float(obj["phi"]))
            pz += _pz(float(obj["pt"]), float(obj["eta"]))
    mass2 = energy * energy - px * px - py * py - pz * pz
    return math.sqrt(max(mass2, 0.0))


def selected_leptons(
    leptons: Iterable[dict[str, Any]],
    *,
    pt_min_gev: float = 10.0,
    require_tight_id: bool = False,
    require_tight_iso: bool = False,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for lepton in leptons:
        if float(lepton.get("pt", 0.0)) <= pt_min_gev:
            continue
        if require_tight_id and not bool(lepton.get("is_tight_id", True)):
            continue
        if require_tight_iso and not bool(lepton.get("is_tight_iso", True)):
            continue
        selected.append(dict(lepton))
    return selected


def same_flavor_os_z_veto(leptons: Iterable[dict[str, Any]], *, window_gev: float = 10.0) -> bool:
    selected = list(leptons)
    for index, first in enumerate(selected):
        for second in selected[index + 1 :]:
            first_type = abs(int(first.get("type", first.get("pdg_id", 0))))
            second_type = abs(int(second.get("type", second.get("pdg_id", 0))))
            if first_type != second_type:
                continue
            first_charge = float(first.get("charge", 0.0))
            second_charge = float(second.get("charge", 0.0))
            if first_charge * second_charge >= 0.0:
                continue
            mass = invariant_mass([first, second])
            if abs(mass - Z_MASS_GEV) < window_gev:
                return True
    return False


def selected_jets(
    jets: Iterable[dict[str, Any]],
    *,
    pt_min_gev: float = 25.0,
    abs_eta_max: float = 4.5,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for jet in jets:
        if float(jet.get("pt", 0.0)) <= pt_min_gev:
            continue
        if abs(float(jet.get("eta", 0.0))) > abs_eta_max:
            continue
        selected.append(dict(jet))
    selected.sort(key=lambda item: float(item.get("pt", 0.0)), reverse=True)
    return selected


def build_jet_features(
    jets: Iterable[dict[str, Any]],
    *,
    pt_min_gev: float = 25.0,
    abs_eta_max: float = 4.5,
    central_abs_eta: float = 2.5,
    btag_quantile_min: int = 4,
) -> dict[str, Any]:
    clean_jets = selected_jets(jets, pt_min_gev=pt_min_gev, abs_eta_max=abs_eta_max)
    central = [jet for jet in clean_jets if abs(float(jet["eta"])) <= central_abs_eta]
    forward = [jet for jet in clean_jets if abs(float(jet["eta"])) > central_abs_eta]
    btags = [
        jet
        for jet in clean_jets
        if bool(jet.get("btag", False)) or int(jet.get("btag_quantile", -1)) >= btag_quantile_min
    ]
    return {
        "selected_jets": clean_jets,
        "ht_jets": float(sum(float(jet["pt"]) for jet in clean_jets)),
        "m_all_jets": invariant_mass(clean_jets),
        "n_jets": int(len(clean_jets)),
        "n_central_jets": int(len(central)),
        "n_forward_jets": int(len(forward)),
        "n_btags": int(len(btags)),
    }


def hadronic_preselection(event: dict[str, Any]) -> bool:
    return (
        int(event.get("n_leptons", 0)) == 0
        and int(event.get("n_jets", 0)) >= 3
        and int(event.get("n_btags", 0)) >= 1
    )


def assign_bdt_category(score: float | None, thresholds: Iterable[float] | None = None) -> str | None:
    if score is None or not math.isfinite(float(score)):
        return None
    ordered = sorted([float(value) for value in (thresholds or FIXED_BDT_THRESHOLDS)], reverse=True)
    labels = ["ttH_had_BDT1", "ttH_had_BDT2", "ttH_had_BDT3", "ttH_had_BDT4"]
    for threshold, label in zip(ordered[:4], labels, strict=False):
        if float(score) > threshold:
            return label
    return None


def assign_top_category(
    event: dict[str, Any],
    *,
    score: float | None = None,
    thresholds: Iterable[float] | None = None,
) -> str:
    """Assign one mutually exclusive top-associated category in priority order."""
    n_leptons = int(event.get("n_leptons", 0))
    n_central = int(event.get("n_central_jets", 0))
    n_forward = int(event.get("n_forward_jets", 0))
    n_btags = int(event.get("n_btags", 0))
    n_jets = int(event.get("n_jets", n_central + n_forward))
    z_veto = bool(event.get("z_veto", False))

    if n_leptons == 1 and n_central <= 3 and n_btags >= 1 and n_forward == 0:
        return "tH_lep_0fwd"
    if n_leptons == 1 and n_central <= 4 and n_btags >= 1 and n_forward >= 1:
        return "tH_lep_1fwd"
    if n_leptons >= 1 and n_central >= 2 and n_btags >= 1 and not z_veto:
        return "ttH_lep"

    if n_leptons == 0 and n_jets >= 3 and n_btags >= 1:
        bdt_category = assign_bdt_category(score, thresholds)
        if bdt_category is not None:
            return bdt_category

    if n_leptons == 0 and n_central == 4 and n_btags == 1:
        return "tH_had_4j1b"
    if n_leptons == 0 and n_central == 4 and n_btags >= 2:
        return "tH_had_4j2b"
    return "unassigned"


def stable_partition(event_id: str, *, seed: int = 314159, fractions: tuple[float, float, float] = (0.5, 0.25, 0.25)) -> str:
    total = sum(fractions)
    if total <= 0:
        raise ValueError("partition fractions must have positive sum")
    train, validation, test = [float(value) / total for value in fractions]
    digest = hashlib.sha256(f"{seed}:{event_id}".encode("utf-8")).hexdigest()
    unit = int(digest[:16], 16) / float(16**16 - 1)
    if unit < train:
        return "training"
    if unit < train + validation:
        return "validation"
    return "test"


def effective_count(weights: Iterable[float]) -> float:
    array = np.asarray(list(weights), dtype=float)
    if array.size == 0:
        return 0.0
    sumw = float(np.sum(array))
    sumw2 = float(np.sum(array * array))
    if sumw2 <= 0.0:
        return 0.0
    return (sumw * sumw) / sumw2


def _rows_in_interval(rows: list[dict[str, Any]], interval: Interval) -> list[dict[str, Any]]:
    return [row for row in rows if interval.contains(float(row["score"]))]


def category_stats(rows: list[dict[str, Any]], interval: Interval) -> dict[str, float | int]:
    selected = _rows_in_interval(rows, interval)
    weights = np.asarray([float(row.get("weight", 1.0)) for row in selected], dtype=float)
    signal = np.asarray([bool(row.get("is_signal", False)) for row in selected], dtype=bool)
    signal_weights = weights[signal]
    background_weights = weights[~signal]
    return {
        "raw_count": int(len(selected)),
        "effective_count": float(effective_count(weights)),
        "signal_yield": float(np.sum(signal_weights)),
        "background_yield": float(np.sum(background_weights)),
        "sumw": float(np.sum(weights)),
        "sum_absw": float(np.sum(np.abs(weights))),
        "sumw2": float(np.sum(weights * weights)),
    }


def asimov_counting_z(signal_yield: float, background_yield: float) -> float:
    signal_yield = float(signal_yield)
    background_yield = float(background_yield)
    if signal_yield <= 0.0 or background_yield <= 0.0:
        return 0.0
    value = 2.0 * ((signal_yield + background_yield) * math.log1p(signal_yield / background_yield) - signal_yield)
    return math.sqrt(max(value, 0.0))


def combined_significance(rows: list[dict[str, Any]], intervals: list[Interval]) -> float:
    total = 0.0
    for interval in intervals:
        stats = category_stats(rows, interval)
        signal_yield = float(stats["signal_yield"])
        background_yield = float(stats["background_yield"])
        if signal_yield <= 0.0 or background_yield <= 0.0:
            continue
        total += (signal_yield + background_yield) * math.log1p(signal_yield / background_yield) - signal_yield
    return math.sqrt(max(2.0 * total, 0.0))


def _candidate_thresholds(scores: np.ndarray, *, max_candidates: int) -> list[float]:
    unique = np.unique(np.asarray(scores, dtype=float))
    unique = unique[np.isfinite(unique)]
    if unique.size < 2:
        return []
    midpoints = (unique[:-1] + unique[1:]) / 2.0
    if len(midpoints) <= max_candidates:
        return [float(value) for value in midpoints]
    quantile_positions = np.linspace(0, len(midpoints) - 1, max_candidates)
    indices = sorted({int(round(value)) for value in quantile_positions})
    return [float(midpoints[index]) for index in indices]


def _constraint_failure(stats: dict[str, float | int], config: dict[str, Any]) -> str | None:
    if int(stats["raw_count"]) < int(config["min_raw_events"]):
        return "min_raw_events"
    if float(stats["effective_count"]) < float(config["min_effective_events"]):
        return "min_effective_events"
    if float(stats["signal_yield"]) <= float(config["min_signal_yield"]):
        return "min_signal_yield"
    if float(stats["background_yield"]) <= float(config["min_background_yield"]):
        return "min_background_yield"
    return None


def optimize_bdt_boundaries(rows: list[dict[str, Any]], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = {
        "max_categories": 4,
        "min_raw_events": 20,
        "min_effective_events": 10.0,
        "min_signal_yield": 0.0,
        "min_background_yield": 0.0,
        "min_interval_width": 1.0e-4,
        "min_absolute_gain": 0.0,
        "min_relative_gain": 0.05,
        "max_candidates": 160,
    }
    if config:
        cfg.update(config)

    clean_rows = [
        {**row, "score": float(row["score"]), "weight": float(row.get("weight", 1.0))}
        for row in rows
        if math.isfinite(float(row.get("score", float("nan"))))
    ]
    if not clean_rows:
        return {
            "status": "blocked",
            "reason": "no finite validation scores",
            "thresholds": [],
            "intervals": [],
            "accepted_splits": [],
            "rejected_splits": [],
            "scan_records": [],
            "z_initial": 0.0,
            "z_final": 0.0,
        }

    intervals = [Interval(float("-inf"), float("inf"))]
    current_z = combined_significance(clean_rows, intervals)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    scan_records: list[dict[str, Any]] = []

    while len(intervals) < int(cfg["max_categories"]):
        best: dict[str, Any] | None = None
        for parent_index, parent in enumerate(intervals):
            parent_rows = _rows_in_interval(clean_rows, parent)
            thresholds = _candidate_thresholds(
                np.asarray([row["score"] for row in parent_rows], dtype=float),
                max_candidates=int(cfg["max_candidates"]),
            )
            if not thresholds:
                rejected.append({"parent": parent.as_dict(), "reason": "no_candidate_thresholds"})
                continue
            median = float(np.median([row["score"] for row in parent_rows]))
            for threshold in thresholds:
                if threshold <= parent.low or threshold >= parent.high:
                    continue
                low = Interval(parent.low, threshold)
                high = Interval(threshold, parent.high)
                low_stats = category_stats(clean_rows, low)
                high_stats = category_stats(clean_rows, high)
                width_ok = (high.high - high.low if math.isfinite(high.high) and math.isfinite(high.low) else 1.0) >= float(cfg["min_interval_width"])
                failure = _constraint_failure(low_stats, cfg) or _constraint_failure(high_stats, cfg)
                if not width_ok:
                    failure = "min_interval_width"
                proposal = intervals[:parent_index] + [low, high] + intervals[parent_index + 1 :]
                z_new = combined_significance(clean_rows, proposal)
                delta = z_new - current_z
                relative = delta / current_z if current_z > 0.0 else float("inf")
                record = {
                    "parent_index": parent_index,
                    "parent": parent.as_dict(),
                    "threshold": float(threshold),
                    "z_before": float(current_z),
                    "z_after": float(z_new),
                    "delta_z": float(delta),
                    "relative_gain": float(relative),
                    "low": {**low.as_dict(), **{f"low_{key}": value for key, value in low_stats.items()}},
                    "high": {**high.as_dict(), **{f"high_{key}": value for key, value in high_stats.items()}},
                    "valid": failure is None,
                    "rejection_reason": failure,
                }
                scan_records.append(record)
                if failure is not None:
                    rejected.append(record)
                    continue
                tie_key = (
                    z_new,
                    min(float(low_stats["effective_count"]), float(high_stats["effective_count"])),
                    -abs(float(threshold) - median),
                    -float(threshold),
                )
                if best is None or tie_key > best["tie_key"]:
                    best = {
                        "tie_key": tie_key,
                        "parent_index": parent_index,
                        "threshold": float(threshold),
                        "low": low,
                        "high": high,
                        "z_new": float(z_new),
                        "delta_z": float(delta),
                        "relative_gain": float(relative),
                        "low_stats": low_stats,
                        "high_stats": high_stats,
                    }

        if best is None:
            break
        if best["delta_z"] < float(cfg["min_absolute_gain"]):
            break
        if best["relative_gain"] < float(cfg["min_relative_gain"]):
            break
        intervals = (
            intervals[: best["parent_index"]]
            + [best["low"], best["high"]]
            + intervals[best["parent_index"] + 1 :]
        )
        current_z = best["z_new"]
        accepted.append(
            {
                "parent_index": best["parent_index"],
                "threshold": best["threshold"],
                "z_after": best["z_new"],
                "delta_z": best["delta_z"],
                "relative_gain": best["relative_gain"],
                "low": {**best["low"].as_dict(), **best["low_stats"]},
                "high": {**best["high"].as_dict(), **best["high_stats"]},
                "tie_breaking": "z_new,min_child_effective_count,median_closeness,lowest_threshold",
            }
        )

    finite_thresholds = sorted({split["threshold"] for split in accepted})
    sorted_intervals = sorted(intervals, key=lambda interval: interval.low)
    return {
        "status": "ok",
        "thresholds": finite_thresholds,
        "thresholds_descending": sorted(finite_thresholds, reverse=True),
        "intervals": [interval.as_dict() for interval in sorted_intervals],
        "accepted_splits": accepted,
        "rejected_splits": rejected,
        "scan_records": scan_records,
        "z_initial": float(combined_significance(clean_rows, [Interval(float("-inf"), float("inf"))])),
        "z_final": float(combined_significance(clean_rows, intervals)),
        "config": cfg,
    }
