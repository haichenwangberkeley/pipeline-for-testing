from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import awkward as ak
import matplotlib
import numpy as np
import uproot

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.common import ensure_dir, list_root_files, write_json
from analysis.samples.metadata import read_root_metadata
from analysis.top_categorization import BDT_FEATURES, CATEGORY_ORDER, stable_partition
from analysis.tth_bdt_training import run_prescribed_bdt_training
from analysis.tth_categorization import run_categorization
from analysis.tth_workspace import run_hadronic_workspace


RANDOM_SEED = 314159
RESULT_SCHEMA_VERSION = "tth-diphoton-preselection-v1"
MC_EVENT_WEIGHT_LUMINOSITY_FB = float(os.environ.get("TTH_MC_EVENT_WEIGHT_LUMINOSITY_FB", "139.0"))
SIGNIFICANCE_MC_LUMINOSITY_FB = float(os.environ.get("TTH_SIGNIFICANCE_MC_LUMINOSITY_FB", "36.0"))
DEFAULT_MAX_SELECTED_PER_SAMPLE = (
    int(os.environ["TTH_MAX_SELECTED_PER_SAMPLE"])
    if os.environ.get("TTH_MAX_SELECTED_PER_SAMPLE")
    else None
)

BRANCHES = [
    "num_events",
    "sum_of_weights",
    "sum_of_weights_squared",
    "xsec",
    "filteff",
    "kfac",
    "channelNumber",
    "eventNumber",
    "runNumber",
    "mcWeight",
    "ScaleFactor_PILEUP",
    "ScaleFactor_PHOTON",
    "ScaleFactor_JVT",
    "ScaleFactor_BTAG",
    "ScaleFactor_FTAG",
    "photon_n",
    "photon_pt",
    "photon_eta",
    "photon_phi",
    "photon_e",
    "photon_isTightID",
    "photon_isTightIso",
    "jet_n",
    "jet_pt",
    "jet_eta",
    "jet_phi",
    "jet_e",
    "jet_btag_quantile",
    "lep_n",
    "lep_type",
    "lep_pt",
    "lep_eta",
    "lep_phi",
    "lep_e",
    "lep_charge",
    "passes_leptonic_preselection",
    "passes_hadronic_preselection",
    "preselection_channel_id",
]

NEGATIVE_HIGGS_TOKENS = [
    "tautau",
    "mumu",
    "zz",
    "ww",
    "bb",
    "hinv",
    "hzzinv",
    "zgam",
    "gamstargam",
]

HIGGS_PROCESS_TOKENS = [
    ("ggH", ["ggh125_gamgam", "ggh_hyy", "ggh125_hyy"]),
    ("VBF", ["vbfh125_gamgam", "vbf_hyy", "vbf125_hyy"]),
    ("WH", ["wph125j_hyy", "wmh125j_hyy", "wph125j_gamgam", "wmh125j_gamgam", "wph_hyy", "wmh_hyy"]),
    ("ZH", ["zh125j_hyy", "zh125j_gamgam", "zh_hyy", "zh125_hyy"]),
    ("ggZH", ["ggzh_hyy", "ggzh125_hgamgam", "ggzh125_hyy"]),
    ("ttH", ["tth125_gamgam", "tth_hyy", "tth125_hyy"]),
    ("tH", ["thjb125_4fl_gamgam", "thjb125_hyy", "twh125_yy", "twh125_hyy"]),
]


def _write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def _yaml_dump(payload: dict[str, Any]) -> str:
    try:
        import yaml

        return yaml.safe_dump(payload, sort_keys=False)
    except Exception:
        return json.dumps(payload, indent=2, sort_keys=True)


def resolve_inputs(explicit: str | None = None) -> Path:
    candidates = [Path(explicit)] if explicit else []
    if os.environ.get("TTH_PRESELECTED_ROOTS"):
        candidates.append(Path(os.environ["TTH_PRESELECTED_ROOTS"]))
    if os.environ.get("TB_HYY_INPUTS"):
        candidates.append(Path(os.environ["TB_HYY_INPUTS"]))
    candidates.extend(
        [
            Path("input-data"),
            Path("input"),
            Path("/root/input-data"),
            Path("/input-data"),
            Path("/Users/haichenwang/Work/newpipeline/input-data"),
            Path("/Volumes/Extreme SSD/analysis-automation-input-data"),
        ]
    )
    for candidate in candidates:
        if candidate and (candidate / "manifest.json").is_file():
            return candidate
        if candidate and (candidate / "MC").is_dir() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError("Could not find input data with MC/ and data/ directories; set TB_HYY_INPUTS")


def _dsid_from_path(path: Path) -> str:
    match = re.search(r"_mc_(\d+)\.", path.name)
    return match.group(1) if match else path.stem


def _classify_nominal_higgs(path: Path) -> tuple[bool, str]:
    lowered = path.name.lower()
    if "sherpa" in lowered or "yy" in lowered and not any(token in lowered for token in ["hyy", "twh125_yy"]):
        return False, "continuum_or_sherpa"
    if any(token in lowered for token in NEGATIVE_HIGGS_TOKENS):
        return False, "non_Hyy_decay"
    if not any(token in lowered for token in ["gamgam", "hyy", "hgamgam", "gammagamma"]):
        return False, "no_Hyy_token"
    for process, tokens in HIGGS_PROCESS_TOKENS:
        if any(token in lowered for token in tokens):
            return True, process
    return False, "unclassified_Hyy"


def sample_manifest(inputs: Path, include_data: bool = True) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for path in list_root_files(inputs / "MC"):
        ok, process = _classify_nominal_higgs(path)
        if not ok:
            continue
        samples.append(
            {
                "sample_id": _dsid_from_path(path),
                "process": process,
                "role": "nominal_higgs_signal",
                "file": str(path),
            }
        )
    if include_data:
        data_files = [path for path in sorted(list_root_files(inputs / "data")) if "gamgam_data" in str(path).lower()]
        samples.append(
            {
                "sample_id": "data",
                "process": "data",
                "role": "data",
                "file": [str(path) for path in data_files],
            }
        )
    return samples


def skim_manifest(inputs: Path, include_data: bool = True) -> list[dict[str, Any]]:
    payload = json.loads((inputs / "manifest.json").read_text(encoding="utf-8"))
    samples: list[dict[str, Any]] = []
    for process_payload in payload.get("processes", []):
        process = process_payload["process"]
        if process == "data" and not include_data:
            continue
        path = Path(process_payload["output"])
        if not path.is_absolute():
            path = inputs / path.name
        samples.append(
            {
                "sample_id": process,
                "process": process,
                "role": "data" if process == "data" else "nominal_higgs_signal",
                "file": str(path),
                "input_mode": "preselected_root_skim",
                "source_manifest": str(inputs / "manifest.json"),
                "events_selected_in_skim": int(process_payload.get("events_selected", 0)),
                "input_files": process_payload.get("input_files", []),
            }
        )
    return samples


def _available_branches(path: str | Path, tree_name: str) -> list[str]:
    with uproot.open(path) as handle:
        keys = set(handle[tree_name].keys())
    return [branch for branch in BRANCHES if branch in keys]


def _norm_factor(sample: dict[str, Any]) -> float:
    if sample["role"] == "data":
        return 1.0
    meta = read_root_metadata(Path(sample["file"]))
    if isinstance(meta, dict):
        sum_weights = float(meta.get("sum_of_weights", meta.get("sumw", 0.0)))
        generated_events = float(meta.get("num_events", meta.get("entries", 0.0)))
        cross_section_pb = float(meta.get("xsec", meta.get("cross_section_pb", 1.0)))
        filter_efficiency = float(meta.get("filteff", meta.get("filter_efficiency", 1.0)))
        k_factor = float(meta.get("kfac", meta.get("k_factor", 1.0)))
        luminosity_pb = float(meta.get("luminosity_pb", MC_EVENT_WEIGHT_LUMINOSITY_FB * 1000.0))
    else:
        sum_weights = float(meta.sum_weights)
        generated_events = float(meta.generated_events)
        cross_section_pb = float(meta.cross_section_pb)
        filter_efficiency = float(meta.filter_efficiency)
        k_factor = float(meta.k_factor)
        luminosity_pb = float(meta.luminosity_pb)
    denominator = sum_weights if abs(sum_weights) > 0.0 else generated_events
    if denominator == 0.0:
        return 1.0
    return float(cross_section_pb * filter_efficiency * k_factor * luminosity_pb / denominator)


def _event_weight(batch: ak.Array, index: int, sample: dict[str, Any], norm_factor: float) -> float:
    if sample["role"] == "data":
        return 1.0
    if sample.get("input_mode") == "preselected_root_skim" and all(
        branch in batch.fields for branch in ["xsec", "filteff", "kfac", "sum_of_weights"]
    ):
        denominator = float(batch["sum_of_weights"][index])
        if abs(denominator) > 0.0:
            norm_factor = (
                float(batch["xsec"][index])
                * float(batch["filteff"][index])
                * float(batch["kfac"][index])
                * MC_EVENT_WEIGHT_LUMINOSITY_FB
                * 1000.0
                / denominator
            )
    weight = norm_factor * float(batch["mcWeight"][index])
    for branch in ["ScaleFactor_PILEUP", "ScaleFactor_PHOTON", "ScaleFactor_JVT"]:
        if branch in batch.fields:
            weight *= float(batch[branch][index])
    if "ScaleFactor_BTAG" in batch.fields:
        weight *= float(batch["ScaleFactor_BTAG"][index])
    elif "ScaleFactor_FTAG" in batch.fields:
        weight *= float(batch["ScaleFactor_FTAG"][index])
    return float(weight)


def _as_numpy(values: ak.Array, *, fill: Any = 0, dtype: Any = float) -> np.ndarray:
    return np.asarray(ak.to_numpy(ak.fill_none(values, fill)), dtype=dtype)


def _batch_diphoton_masses(batch: ak.Array) -> tuple[np.ndarray, np.ndarray]:
    info = _batch_diphoton_info(batch)
    return info["mass"], info["has_candidate"]


def _batch_diphoton_info(batch: ak.Array) -> dict[str, np.ndarray]:
    pt = batch["photon_pt"]
    eta = batch["photon_eta"]
    phi = batch["photon_phi"]
    energy = batch["photon_e"]
    abs_eta = np.abs(eta)
    selected = (pt > 25.0) & (abs_eta < 2.37) & ~((abs_eta > 1.37) & (abs_eta < 1.52))

    selected_pt = pt[selected]
    selected_eta = eta[selected]
    selected_phi = phi[selected]
    selected_energy = energy[selected]
    order = ak.argsort(selected_pt, ascending=False)
    sorted_pt = ak.pad_none(selected_pt[order], 2, clip=True)
    sorted_eta = ak.pad_none(selected_eta[order], 2, clip=True)
    sorted_phi = ak.pad_none(selected_phi[order], 2, clip=True)
    sorted_energy = ak.pad_none(selected_energy[order], 2, clip=True)

    first_pt = sorted_pt[:, 0]
    second_pt = sorted_pt[:, 1]
    first_eta = sorted_eta[:, 0]
    second_eta = sorted_eta[:, 1]
    first_phi = sorted_phi[:, 0]
    second_phi = sorted_phi[:, 1]
    first_energy = sorted_energy[:, 0]
    second_energy = sorted_energy[:, 1]

    total_energy = first_energy + second_energy
    px = first_pt * np.cos(first_phi) + second_pt * np.cos(second_phi)
    py = first_pt * np.sin(first_phi) + second_pt * np.sin(second_phi)
    pz = first_pt * np.sinh(first_eta) + second_pt * np.sinh(second_eta)
    mass2 = total_energy * total_energy - px * px - py * py - pz * pz
    mass = np.sqrt(np.maximum(mass2, 0.0))
    mass_np = _as_numpy(mass, fill=np.nan, dtype=float)
    has_candidate = np.isfinite(mass_np) & (mass_np > 0.0)

    has_ti_nti_info = all(branch in batch.fields for branch in ["photon_isTightID", "photon_isTightIso"])
    if has_ti_nti_info:
        tight_id = batch["photon_isTightID"][selected]
        tight_iso = batch["photon_isTightIso"][selected]
        sorted_tight_id = ak.pad_none(tight_id[order], 2, clip=True)
        sorted_tight_iso = ak.pad_none(tight_iso[order], 2, clip=True)
        lead_tight_id = _as_numpy(sorted_tight_id[:, 0], fill=False, dtype=bool)
        sublead_tight_id = _as_numpy(sorted_tight_id[:, 1], fill=False, dtype=bool)
        lead_tight_iso = _as_numpy(sorted_tight_iso[:, 0], fill=False, dtype=bool)
        sublead_tight_iso = _as_numpy(sorted_tight_iso[:, 1], fill=False, dtype=bool)
    else:
        lead_tight_id = np.zeros(len(mass_np), dtype=bool)
        sublead_tight_id = np.zeros(len(mass_np), dtype=bool)
        lead_tight_iso = np.zeros(len(mass_np), dtype=bool)
        sublead_tight_iso = np.zeros(len(mass_np), dtype=bool)

    is_ti = has_candidate & lead_tight_id & lead_tight_iso & sublead_tight_id & sublead_tight_iso
    is_nti = has_candidate & np.logical_not(is_ti) if has_ti_nti_info else np.zeros(len(mass_np), dtype=bool)
    return {
        "mass": mass_np,
        "has_candidate": has_candidate,
        "has_ti_nti_info": np.full(len(mass_np), has_ti_nti_info, dtype=bool),
        "lead_photon_tight_id": lead_tight_id,
        "lead_photon_tight_iso": lead_tight_iso,
        "sublead_photon_tight_id": sublead_tight_id,
        "sublead_photon_tight_iso": sublead_tight_iso,
        "is_ti_diphoton": is_ti,
        "is_nti_diphoton": is_nti,
    }


def _batch_event_features(batch: ak.Array) -> dict[str, np.ndarray]:
    jet_pt = batch["jet_pt"]
    jet_eta = batch["jet_eta"]
    jet_phi = batch["jet_phi"]
    jet_energy = batch["jet_e"]
    jet_btag = batch["jet_btag_quantile"] if "jet_btag_quantile" in batch.fields else ak.zeros_like(jet_pt)

    jet_selected = (jet_pt > 25.0) & (np.abs(jet_eta) <= 4.5)
    sel_pt = jet_pt[jet_selected]
    sel_eta = jet_eta[jet_selected]
    sel_phi = jet_phi[jet_selected]
    sel_energy = jet_energy[jet_selected]

    e_sum = ak.sum(sel_energy, axis=1)
    px_sum = ak.sum(sel_pt * np.cos(sel_phi), axis=1)
    py_sum = ak.sum(sel_pt * np.sin(sel_phi), axis=1)
    pz_sum = ak.sum(sel_pt * np.sinh(sel_eta), axis=1)
    mass2 = e_sum * e_sum - px_sum * px_sum - py_sum * py_sum - pz_sum * pz_sum
    jet_mass = np.sqrt(np.maximum(mass2, 0.0))

    lepton_mask = batch["lep_pt"] > 10.0
    if "lep_type" in batch.fields:
        lepton_mask = lepton_mask & ((np.abs(batch["lep_type"]) == 11) | (np.abs(batch["lep_type"]) == 13))

    return {
        "ht_jets": _as_numpy(ak.sum(sel_pt, axis=1), dtype=float),
        "m_all_jets": _as_numpy(jet_mass, dtype=float),
        "n_jets": _as_numpy(ak.sum(jet_selected, axis=1), dtype=int),
        "n_central_jets": _as_numpy(ak.sum(jet_selected & (np.abs(jet_eta) <= 2.5), axis=1), dtype=int),
        "n_forward_jets": _as_numpy(ak.sum(jet_selected & (np.abs(jet_eta) > 2.5), axis=1), dtype=int),
        "n_btags": _as_numpy(ak.sum(jet_selected & (jet_btag >= 4), axis=1), dtype=int),
        "n_leptons": _as_numpy(ak.sum(lepton_mask, axis=1), dtype=int),
    }


def collect_preselected_events(
    samples: list[dict[str, Any]],
    *,
    tree_name: str,
    max_selected_per_sample: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cutflow: dict[str, Any] = {}
    for sample in samples:
        files = sample["file"] if isinstance(sample["file"], list) else [sample["file"]]
        norm = _norm_factor(sample)
        flow = {
            "files": len(files),
            "events_read": 0,
            "diphoton_105_160_no_id_iso": 0,
            "ti_diphoton": 0,
            "nti_diphoton": 0,
            "diphoton_123_127_no_id_iso": 0,
            "diphoton_sideband_105_120_130_160_no_id_iso": 0,
            "leptonic_preselection": 0,
            "hadronic_preselection": 0,
            "selected": 0,
        }
        for file_path in files:
            if max_selected_per_sample is not None and flow["selected"] >= max_selected_per_sample:
                break
            branches = _available_branches(file_path, tree_name)
            file_tag = Path(file_path).name.removesuffix(".root")
            with uproot.open(file_path) as handle:
                tree = handle[tree_name]
                for batch in tree.iterate(branches, step_size="50 MB", library="ak"):
                    diphotons = _batch_diphoton_info(batch)
                    masses = diphotons["mass"]
                    has_photons = diphotons["has_candidate"]
                    features = _batch_event_features(batch)
                    in_mass = has_photons & (masses >= 105.0) & (masses <= 160.0)
                    in_signal_window = has_photons & (masses >= 123.0) & (masses <= 127.0)
                    in_sideband = has_photons & (((masses >= 105.0) & (masses <= 120.0)) | ((masses >= 130.0) & (masses <= 160.0)))
                    leptonic = in_mass & (features["n_leptons"] >= 1) & (features["n_btags"] >= 1)
                    hadronic = (
                        in_mass
                        & (features["n_leptons"] == 0)
                        & (features["n_jets"] >= 3)
                        & (features["n_btags"] >= 1)
                    )
                    selected = leptonic | hadronic
                    flow["events_read"] += len(batch["eventNumber"])
                    flow["diphoton_105_160_no_id_iso"] += int(np.sum(in_mass))
                    flow["ti_diphoton"] += int(np.sum(diphotons["is_ti_diphoton"]))
                    flow["nti_diphoton"] += int(np.sum(diphotons["is_nti_diphoton"]))
                    flow["diphoton_123_127_no_id_iso"] += int(np.sum(in_signal_window))
                    flow["diphoton_sideband_105_120_130_160_no_id_iso"] += int(np.sum(in_sideband))
                    flow["leptonic_preselection"] += int(np.sum(leptonic))
                    flow["hadronic_preselection"] += int(np.sum(hadronic))

                    for index in np.flatnonzero(selected):
                        if max_selected_per_sample is not None and flow["selected"] >= max_selected_per_sample:
                            break
                        run_number = int(batch["runNumber"][index])
                        event_number = int(batch["eventNumber"][index])
                        event_id = f"{sample['sample_id']}:{file_tag}:{run_number}:{event_number}"
                        channel = "leptonic" if bool(leptonic[index]) else "hadronic"
                        row = {
                            "event_id": event_id,
                            "sample_id": sample["sample_id"],
                            "process": sample["process"],
                            "role": sample["role"],
                            "source_file": file_tag,
                            "run_number": run_number,
                            "event_number": event_number,
                            "event_weight": _event_weight(batch, int(index), sample, norm),
                            "m_gammagamma": float(masses[index]),
                            "has_diphoton_candidate": bool(has_photons[index]),
                            "in_mgg_105_160": bool(in_mass[index]),
                            "in_mgg_123_127": bool(in_signal_window[index]),
                            "in_mgg_sideband_105_120_130_160": bool(in_sideband[index]),
                            "has_ti_nti_info": bool(diphotons["has_ti_nti_info"][index]),
                            "lead_photon_tight_id": bool(diphotons["lead_photon_tight_id"][index]),
                            "lead_photon_tight_iso": bool(diphotons["lead_photon_tight_iso"][index]),
                            "sublead_photon_tight_id": bool(diphotons["sublead_photon_tight_id"][index]),
                            "sublead_photon_tight_iso": bool(diphotons["sublead_photon_tight_iso"][index]),
                            "is_ti_diphoton": bool(diphotons["is_ti_diphoton"][index]),
                            "is_nti_diphoton": bool(diphotons["is_nti_diphoton"][index]),
                            "n_leptons": int(features["n_leptons"][index]),
                            "n_jets": int(features["n_jets"][index]),
                            "n_central_jets": int(features["n_central_jets"][index]),
                            "n_forward_jets": int(features["n_forward_jets"][index]),
                            "n_btags": int(features["n_btags"][index]),
                            "ht_jets": float(features["ht_jets"][index]),
                            "m_all_jets": float(features["m_all_jets"][index]),
                            "passes_leptonic_preselection": bool(leptonic[index]),
                            "passes_hadronic_preselection": bool(hadronic[index]),
                            "preselection_channel": channel,
                            "partition": stable_partition(event_id, seed=RANDOM_SEED),
                        }
                        rows.append(row)
                        flow["selected"] += 1
                    if max_selected_per_sample is not None and flow["selected"] >= max_selected_per_sample:
                        break
        cutflow[sample["sample_id"]] = flow
    return rows, cutflow


def _stored_bool(batch: ak.Array, branch: str, default: np.ndarray) -> np.ndarray:
    if branch not in batch.fields:
        return default
    return np.asarray(ak.to_numpy(ak.fill_none(batch[branch], False)), dtype=bool)


def collect_skimmed_events(
    samples: list[dict[str, Any]],
    *,
    tree_name: str,
    max_selected_per_sample: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cutflow: dict[str, Any] = {}
    for sample in samples:
        file_path = Path(sample["file"])
        norm = 1.0 if sample.get("input_mode") == "preselected_root_skim" or sample["role"] == "data" else _norm_factor(sample)
        flow = {
            "files": 1,
            "events_read": 0,
            "skim_selected_input": int(sample.get("events_selected_in_skim", 0)),
            "diphoton_candidate_no_id_iso": 0,
            "diphoton_105_160_no_id_iso": 0,
            "ti_diphoton": 0,
            "nti_diphoton": 0,
            "diphoton_123_127_no_id_iso": 0,
            "diphoton_sideband_105_120_130_160_no_id_iso": 0,
            "leptonic_preselection": 0,
            "hadronic_preselection": 0,
            "selected": 0,
        }
        branches = _available_branches(file_path, tree_name)
        file_tag = file_path.name.removesuffix(".root")
        with uproot.open(file_path) as handle:
            tree = handle[tree_name]
            for batch in tree.iterate(branches, step_size="50 MB", library="ak"):
                features = _batch_event_features(batch)
                diphotons = _batch_diphoton_info(batch)
                masses = diphotons["mass"]
                has_photons = diphotons["has_candidate"]
                recomputed_leptonic = (features["n_leptons"] >= 1) & (features["n_btags"] >= 1)
                recomputed_hadronic = (
                    (features["n_leptons"] == 0)
                    & (features["n_jets"] >= 3)
                    & (features["n_btags"] >= 1)
                )
                leptonic = _stored_bool(batch, "passes_leptonic_preselection", recomputed_leptonic)
                hadronic = _stored_bool(batch, "passes_hadronic_preselection", recomputed_hadronic)
                selected = leptonic | hadronic
                in_mass = has_photons & (masses >= 105.0) & (masses <= 160.0)
                in_signal_window = has_photons & (masses >= 123.0) & (masses <= 127.0)
                in_sideband = has_photons & (((masses >= 105.0) & (masses <= 120.0)) | ((masses >= 130.0) & (masses <= 160.0)))
                flow["events_read"] += len(batch["eventNumber"])
                flow["diphoton_candidate_no_id_iso"] += int(np.sum(has_photons))
                flow["diphoton_105_160_no_id_iso"] += int(np.sum(in_mass))
                flow["ti_diphoton"] += int(np.sum(diphotons["is_ti_diphoton"]))
                flow["nti_diphoton"] += int(np.sum(diphotons["is_nti_diphoton"]))
                flow["diphoton_123_127_no_id_iso"] += int(np.sum(in_signal_window))
                flow["diphoton_sideband_105_120_130_160_no_id_iso"] += int(np.sum(in_sideband))
                flow["leptonic_preselection"] += int(np.sum(leptonic))
                flow["hadronic_preselection"] += int(np.sum(hadronic))
                for index in np.flatnonzero(selected):
                    if max_selected_per_sample is not None and flow["selected"] >= max_selected_per_sample:
                        break
                    run_number = int(batch["runNumber"][index])
                    event_number = int(batch["eventNumber"][index])
                    channel_number = int(batch["channelNumber"][index]) if "channelNumber" in batch.fields else sample["sample_id"]
                    sample_id = str(channel_number) if sample["role"] != "data" else sample["sample_id"]
                    event_id = f"{sample['process']}:{sample_id}:{run_number}:{event_number}"
                    channel = "leptonic" if bool(leptonic[index]) else "hadronic"
                    row = {
                        "event_id": event_id,
                        "sample_id": sample_id,
                        "process": sample["process"],
                        "role": sample["role"],
                        "source_file": file_tag,
                        "run_number": run_number,
                        "event_number": event_number,
                        "event_weight": _event_weight(batch, int(index), sample, norm),
                        "m_gammagamma": float(masses[index]),
                        "has_diphoton_candidate": bool(has_photons[index]),
                        "in_mgg_105_160": bool(in_mass[index]),
                        "in_mgg_123_127": bool(in_signal_window[index]),
                        "in_mgg_sideband_105_120_130_160": bool(in_sideband[index]),
                        "has_ti_nti_info": bool(diphotons["has_ti_nti_info"][index]),
                        "lead_photon_tight_id": bool(diphotons["lead_photon_tight_id"][index]),
                        "lead_photon_tight_iso": bool(diphotons["lead_photon_tight_iso"][index]),
                        "sublead_photon_tight_id": bool(diphotons["sublead_photon_tight_id"][index]),
                        "sublead_photon_tight_iso": bool(diphotons["sublead_photon_tight_iso"][index]),
                        "is_ti_diphoton": bool(diphotons["is_ti_diphoton"][index]),
                        "is_nti_diphoton": bool(diphotons["is_nti_diphoton"][index]),
                        "n_leptons": int(features["n_leptons"][index]),
                        "n_jets": int(features["n_jets"][index]),
                        "n_central_jets": int(features["n_central_jets"][index]),
                        "n_forward_jets": int(features["n_forward_jets"][index]),
                        "n_btags": int(features["n_btags"][index]),
                        "ht_jets": float(features["ht_jets"][index]),
                        "m_all_jets": float(features["m_all_jets"][index]),
                        "passes_leptonic_preselection": bool(leptonic[index]),
                        "passes_hadronic_preselection": bool(hadronic[index]),
                        "preselection_channel": channel,
                        "partition": stable_partition(event_id, seed=RANDOM_SEED),
                    }
                    rows.append(row)
                    flow["selected"] += 1
                if max_selected_per_sample is not None and flow["selected"] >= max_selected_per_sample:
                    break
        cutflow[sample["sample_id"]] = flow
    return rows, cutflow


def _write_table(rows: list[dict[str, Any]], stem: Path) -> None:
    ensure_dir(stem.parent)
    try:
        import pandas as pd

        pd.DataFrame(rows).to_csv(stem.with_suffix(".csv"), index=False)
    except Exception:
        _write_text(stem.with_suffix(".jsonl"), "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")


def build_preselection_summary(rows: list[dict[str, Any]], out_dir: Path, max_selected_per_sample: int | None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "ok",
        "schema_version": RESULT_SCHEMA_VERSION,
        "max_selected_per_sample": max_selected_per_sample,
        "definitions": {
            "photon_candidate": "two highest-pT photons passing pT > 25 GeV, |eta| < 2.37, and crack veto; no photon tight-ID or isolation requirement is applied",
            "leptonic_preselection": "at least one electron or muon with pT > 10 GeV and at least one selected b-jet",
            "hadronic_preselection": "zero selected electrons or muons, at least three selected jets, and at least one selected b-jet",
            "event_selection": "leptonic_preselection OR hadronic_preselection",
        },
        "overall": {
            "selected": {"raw_count": 0, "weighted_yield": 0.0},
            "leptonic_preselection": {"raw_count": 0, "weighted_yield": 0.0},
            "hadronic_preselection": {"raw_count": 0, "weighted_yield": 0.0},
        },
        "by_process": {},
    }
    for row in rows:
        weight = float(row["event_weight"])
        process = row["process"]
        summary["by_process"].setdefault(
            process,
            {
                "selected": {"raw_count": 0, "weighted_yield": 0.0},
                "leptonic_preselection": {"raw_count": 0, "weighted_yield": 0.0},
                "hadronic_preselection": {"raw_count": 0, "weighted_yield": 0.0},
            },
        )
        for scope in [summary["overall"], summary["by_process"][process]]:
            scope["selected"]["raw_count"] += 1
            scope["selected"]["weighted_yield"] += weight
            if row["passes_leptonic_preselection"]:
                scope["leptonic_preselection"]["raw_count"] += 1
                scope["leptonic_preselection"]["weighted_yield"] += weight
            if row["passes_hadronic_preselection"]:
                scope["hadronic_preselection"]["raw_count"] += 1
                scope["hadronic_preselection"]["weighted_yield"] += weight
    write_json(summary, out_dir / "preselection_summary.json")
    return summary


def write_plots(rows: list[dict[str, Any]], out_dir: Path) -> None:
    plot_dir = ensure_dir(out_dir / "plots")
    masses = np.asarray(
        [row["m_gammagamma"] for row in rows if row.get("has_diphoton_candidate", True)],
        dtype=float,
    )
    masses = masses[np.isfinite(masses)]
    channels = ["leptonic", "hadronic"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(masses, bins=40, range=(105, 160), histtype="stepfilled", alpha=0.65)
    ax.set_xlabel("m_gammagamma [GeV]")
    ax.set_ylabel("selected events")
    fig.tight_layout()
    fig.savefig(plot_dir / "preselection_mass.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(channels, [sum(row["preselection_channel"] == channel for row in rows) for channel in channels])
    ax.set_ylabel("selected events")
    fig.tight_layout()
    fig.savefig(plot_dir / "preselection_channels.png", dpi=130)
    plt.close(fig)

    processes = sorted({row["process"] for row in rows})
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(processes, [sum(row["process"] == process for row in rows) for process in processes])
    ax.set_ylabel("selected events")
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    fig.savefig(plot_dir / "preselection_processes.png", dpi=130)
    plt.close(fig)


def write_outputs(
    rows: list[dict[str, Any]],
    cutflow: dict[str, Any],
    samples: list[dict[str, Any]],
    out_dir: Path,
    inputs: Path,
    max_selected_per_sample: int | None,
    input_mode: str,
) -> None:
    ensure_dir(out_dir)
    config = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "random_seed": RANDOM_SEED,
        "input_path": str(inputs),
        "input_mode": input_mode,
        "tree_name": "analysis",
        "max_selected_per_sample": max_selected_per_sample,
        "mc_event_weight_luminosity_fb": MC_EVENT_WEIGHT_LUMINOSITY_FB,
        "significance_mc_luminosity_fb": SIGNIFICANCE_MC_LUMINOSITY_FB,
        "processed_sample_scope": "nominal Higgs H->gamma gamma MC samples and observed GamGam data only",
        "excluded_backgrounds": ["Sherpa yy", "prompt diphoton continuum MC", "non-Higgs MC"],
    }
    _write_text(out_dir / "config_resolved.yaml", _yaml_dump(config))
    write_json(config, out_dir / "config_resolved.json")
    write_json(
        {
            "status": "ok",
            "same_input_contract_as_tb_hyy": True,
            "source": "preselected ROOT skims" if input_mode == "preselected_root_skim" else "TB_HYY_INPUTS-compatible ATLAS open-data GamGam directory",
            "path": str(inputs),
            "samples": samples,
        },
        out_dir / "input_data_contract.json",
    )
    write_json(
        {
            "status": "ok",
            "object_definitions": {
                "photons": {
                    "pt_min_gev": 25.0,
                    "abs_eta_max": 2.37,
                    "eta_crack_veto": [1.37, 1.52],
                    "requires_tight_id": False,
                    "requires_tight_iso": False,
                },
                "leptons": {"flavors": ["electron", "muon"], "pt_min_gev": 10.0, "requires_tight_id": False, "requires_tight_iso": False},
                "jets": {"pt_min_gev": 25.0, "abs_eta_max": 4.5, "btag_definition": "jet_btag_quantile >= 4"},
            },
            "preselection": {
                "leptonic": "n_electrons_or_muons >= 1 and n_btags >= 1",
                "hadronic": "n_electrons_or_muons == 0 and n_jets >= 3 and n_btags >= 1",
                "selected_if": "leptonic OR hadronic",
            },
            "bdt_features_reserved_for_later": BDT_FEATURES,
            "category_order_reserved_for_later": CATEGORY_ORDER,
        },
        out_dir / "object_definition_record.json",
    )
    write_json(cutflow, out_dir / "cutflow.json")
    summary = build_preselection_summary(rows, out_dir, max_selected_per_sample)
    _write_table(rows, out_dir / "preselected_events")
    bdt_training = run_prescribed_bdt_training(
        rows,
        out_dir,
        random_seed=RANDOM_SEED,
        event_weight_luminosity_fb=MC_EVENT_WEIGHT_LUMINOSITY_FB,
        significance_luminosity_fb=SIGNIFICANCE_MC_LUMINOSITY_FB,
    )
    if bdt_training.get("status") != "ok":
        _write_table(rows, out_dir / "predictions")
        _write_table(
            [
                {key: row[key] for key in ["event_id", "partition", "process", "event_weight", "m_gammagamma", *BDT_FEATURES]}
                for row in rows
            ],
            out_dir / "hadronic_features",
        )
        categorization = {"status": "skipped", "reason": "BDT training did not complete"}
        workspace_fit = {"status": "skipped", "reason": "BDT training did not complete"}
    else:
        categorization = run_categorization(
            out_dir / "inference" / "events_with_bdt_scores.csv",
            out_dir / "categorization",
            thresholds_descending=bdt_training.get("thresholds_descending", []),
        )
        workspace_fit = run_hadronic_workspace(
            out_dir / "inference" / "events_with_bdt_scores.csv",
            out_dir,
            retention_json=out_dir / "categorization" / "category_retention.json",
            mixture_json=out_dir / "model" / "background_mixture_and_normalization.json",
        )
    partition_counts: dict[str, int] = {}
    for row in rows:
        partition_counts[row["partition"]] = partition_counts.get(row["partition"], 0) + 1
    metrics = {
        "status": "ok",
        "schema_version": RESULT_SCHEMA_VERSION,
        "input_mode": input_mode,
        "n_selected_rows": len(rows),
        "partition_counts": partition_counts,
        "processes": sorted({row["process"] for row in rows}),
        "channels": {
            "leptonic": int(sum(row["preselection_channel"] == "leptonic" for row in rows)),
            "hadronic": int(sum(row["preselection_channel"] == "hadronic" for row in rows)),
        },
        "diphoton_candidates_no_id_iso": int(sum(row.get("has_diphoton_candidate", False) for row in rows)),
        "diphoton_105_160_no_id_iso": int(sum(row.get("in_mgg_105_160", False) for row in rows)),
        "diphoton_123_127_no_id_iso": int(sum(row.get("in_mgg_123_127", False) for row in rows)),
        "diphoton_sideband_105_120_130_160_no_id_iso": int(
            sum(row.get("in_mgg_sideband_105_120_130_160", False) for row in rows)
        ),
        "ti_diphoton": int(sum(row.get("is_ti_diphoton", False) for row in rows)),
        "nti_diphoton": int(sum(row.get("is_nti_diphoton", False) for row in rows)),
        "bdt_training": {
            "status": bdt_training.get("status"),
            "thresholds_descending": bdt_training.get("thresholds_descending", []),
            "metrics": bdt_training.get("metrics", {}),
        },
        "categorization": {
            "status": categorization.get("status"),
            "combined_expected_counting_z": categorization.get("totals", {}).get("combined_expected_counting_z"),
            "category_summary": categorization.get("artifacts", {}).get("category_summary_csv"),
        },
        "workspace_fit": {
            "status": workspace_fit.get("status"),
            "asimov_expected_significance": workspace_fit.get("asimov_expected_significance"),
            "mu_hat": workspace_fit.get("mu_hat"),
            "mu_uncertainty": workspace_fit.get("mu_uncertainty"),
            "included_categories": workspace_fit.get("included_categories", []),
            "workspace_root": workspace_fit.get("artifacts", {}).get("workspace_root"),
            "significance_asimov": workspace_fit.get("artifacts", {}).get("significance_asimov"),
        },
    }
    write_json(metrics, out_dir / "metrics.json")
    write_plots(rows, out_dir)
    lines = [
        "# ttH diphoton preselection development sample",
        "",
        f"Selected rows: {len(rows)}",
        f"Maximum selected rows per sample: {max_selected_per_sample}",
        f"Input mode: {input_mode}",
        f"BDT training status: {bdt_training.get('status')}",
        f"Hadronic workspace expected Z: {workspace_fit.get('asimov_expected_significance', 'n/a')}",
        "",
        "Photon candidates use kinematic requirements only; no tight-ID or isolation requirement is applied.",
        "Events are kept if they satisfy the leptonic or hadronic top preselection.",
        "Only nominal Higgs H->gamma gamma MC samples and observed data are processed; prompt diphoton continuum MC is excluded.",
        "Hadronic BDT training uses ttH+tH MC as signal and a class-balanced ggH+NTI background mixture following the recorded SF1*SF2 prescription.",
        "",
        "| Channel | Raw count | Weighted yield |",
        "|---|---:|---:|",
    ]
    for key in ["leptonic_preselection", "hadronic_preselection"]:
        payload = summary["overall"][key]
        lines.append(f"| {key} | {payload['raw_count']} | {payload['weighted_yield']:.6g} |")
    _write_text(out_dir / "report.md", "\n".join(lines) + "\n")
    write_json(
        {
            "status": "ok",
            "schema_version": RESULT_SCHEMA_VERSION,
            "input_mode": input_mode,
            "outputs_written": sorted(str(path.relative_to(out_dir)) for path in out_dir.rglob("*") if path.is_file()),
            "notes": [
                "This is a preselection and hadronic-BDT development sample.",
                "No Sherpa yy or other continuum-background MC samples are processed.",
                "The BDT training metadata records the NTI sideband source, SF1/SF2 normalization, and class-balance check.",
                "The hadronic combined workspace uses signal-plus-background Asimov pseudo-data and a shared signal-strength parameter.",
            ],
        },
        out_dir / "run_manifest.json",
    )


def run(args: argparse.Namespace) -> None:
    inputs = resolve_inputs(args.inputs)
    outputs = ensure_dir(Path(args.outputs))
    if (inputs / "manifest.json").is_file():
        input_mode = "preselected_root_skim"
        samples = skim_manifest(inputs, include_data=not args.skip_data)
        rows, cutflow = collect_skimmed_events(
            samples,
            tree_name="analysis",
            max_selected_per_sample=args.max_selected_per_sample,
        )
    else:
        input_mode = "full_root_inputs"
        samples = sample_manifest(inputs, include_data=not args.skip_data)
        rows, cutflow = collect_preselected_events(
            samples,
            tree_name="analysis",
            max_selected_per_sample=args.max_selected_per_sample,
        )
    write_outputs(rows, cutflow, samples, outputs, inputs, args.max_selected_per_sample, input_mode)
    print(json.dumps({"status": "ok", "rows": len(rows), "outputs": str(outputs)}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs")
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--max-selected-per-sample", type=int, default=DEFAULT_MAX_SELECTED_PER_SAMPLE)
    parser.add_argument("--skip-data", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
