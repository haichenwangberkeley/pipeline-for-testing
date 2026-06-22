import math

from analysis.top_categorization import (
    CATEGORY_ORDER,
    assign_top_category,
    build_jet_features,
    invariant_mass,
    optimize_bdt_boundaries,
    stable_partition,
)


def test_category_priority_and_fixed_boundaries():
    assert CATEGORY_ORDER[:3] == ["tH_lep_0fwd", "tH_lep_1fwd", "ttH_lep"]
    assert assign_top_category({"n_leptons": 1, "n_central_jets": 3, "n_forward_jets": 0, "n_btags": 1}, score=0.99) == "tH_lep_0fwd"
    assert assign_top_category({"n_leptons": 1, "n_central_jets": 4, "n_forward_jets": 1, "n_btags": 1}, score=0.99) == "tH_lep_1fwd"
    assert assign_top_category({"n_leptons": 2, "n_central_jets": 2, "n_forward_jets": 0, "n_btags": 1, "z_veto": False}, score=0.99) == "ttH_lep"
    assert assign_top_category({"n_leptons": 2, "n_central_jets": 2, "n_forward_jets": 0, "n_btags": 1, "z_veto": True}, score=0.99) == "unassigned"
    assert assign_top_category({"n_leptons": 0, "n_jets": 4, "n_central_jets": 4, "n_forward_jets": 0, "n_btags": 1}, score=0.9200001) == "ttH_had_BDT1"
    assert assign_top_category({"n_leptons": 0, "n_jets": 4, "n_central_jets": 4, "n_forward_jets": 0, "n_btags": 1}, score=0.92) == "ttH_had_BDT2"
    assert assign_top_category({"n_leptons": 0, "n_jets": 4, "n_central_jets": 4, "n_forward_jets": 0, "n_btags": 1}, score=0.52) == "tH_had_4j1b"


def test_jet_features_use_central_boundary_and_four_vector_mass():
    jets = [
        {"pt": 40.0, "eta": 0.0, "phi": 0.0, "e": 40.0, "btag_quantile": 4},
        {"pt": 40.0, "eta": 0.0, "phi": math.pi, "e": 40.0, "btag_quantile": 0},
        {"pt": 30.0, "eta": 2.5, "phi": 1.0, "e": 80.0, "btag_quantile": 0},
        {"pt": 35.0, "eta": -2.7, "phi": 2.0, "e": 130.0, "btag_quantile": 0},
        {"pt": 25.0, "eta": 0.1, "phi": 0.2, "e": 25.0, "btag_quantile": 4},
    ]
    features = build_jet_features(jets)
    assert features["n_jets"] == 4
    assert features["n_central_jets"] == 3
    assert features["n_forward_jets"] == 1
    assert features["n_btags"] == 1
    assert math.isclose(invariant_mass(jets[:2]), 80.0, rel_tol=1e-12)


def test_stable_partition_is_reproducible():
    first = stable_partition("346525:1:42", seed=123)
    assert first == stable_partition("346525:1:42", seed=123)
    assert first in {"training", "validation", "test"}


def test_optimizer_selects_global_split_on_synthetic_scores():
    rows = []
    for score in [0.10, 0.12, 0.14, 0.16, 0.18]:
        rows.append({"score": score, "weight": 10.0, "is_signal": False})
    rows.append({"score": 0.20, "weight": 0.5, "is_signal": True})
    for score in [0.80, 0.82, 0.84, 0.86, 0.88]:
        rows.append({"score": score, "weight": 3.0, "is_signal": True})
    rows.append({"score": 0.90, "weight": 1.0, "is_signal": False})
    result = optimize_bdt_boundaries(
        rows,
        {
            "max_categories": 2,
            "min_raw_events": 1,
            "min_effective_events": 1.0,
            "min_relative_gain": 0.0,
            "max_candidates": 20,
        },
    )
    assert result["status"] == "ok"
    assert len(result["accepted_splits"]) == 1
    assert 0.20 < result["thresholds"][0] < 0.80
    assert result["z_final"] > result["z_initial"]
