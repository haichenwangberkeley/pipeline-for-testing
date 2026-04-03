from __future__ import annotations

from pathlib import Path
from typing import Any

from analysis.common import read_json, utcnow_iso, write_json
from analysis.stats.fit import FIT_ID


REVIEW_STAGE_INFO = {
    "preflight_fact_check_reviewer": {"stage_number": 1, "reviewer": "Preflight Fact Check Reviewer"},
    "analysis_summary_reviewer": {"stage_number": 3, "reviewer": "Analysis Summary Reviewer"},
    "nominal_sample_and_normalization_reviewer": {"stage_number": 2, "reviewer": "Nominal Sample and Normalization Reviewer"},
    "likelihood_sample_role_reviewer": {"stage_number": 2, "reviewer": "Likelihood Sample Role Reviewer"},
    "statistical_readiness_reviewer": {"stage_number": 7, "reviewer": "Statistical Readiness Reviewer"},
    "blinding_and_visualization_reviewer": {"stage_number": 8, "reviewer": "Blinding and Visualization Reviewer"},
    "data_mc_discrepancy_reviewer": {"stage_number": 8, "reviewer": "Data-MC Discrepancy Reviewer"},
    "reproducibility_and_handoff_reviewer": {"stage_number": 10, "reviewer": "Reproducibility and Handoff Reviewer"},
}

REVIEW_ORDER = [
    "preflight_fact_check_reviewer",
    "analysis_summary_reviewer",
    "nominal_sample_and_normalization_reviewer",
    "likelihood_sample_role_reviewer",
    "statistical_readiness_reviewer",
    "blinding_and_visualization_reviewer",
    "data_mc_discrepancy_reviewer",
    "reproducibility_and_handoff_reviewer",
]


def _review_path(outputs: Path, slug: str) -> Path:
    return outputs / "report" / "reviewers" / f"{slug}.json"


def _gate_path(outputs: Path, slug: str) -> Path:
    return outputs / "report" / "gates" / f"{slug}.json"


def _all_exist(paths: list[Path]) -> bool:
    return all(path.exists() for path in paths)


def _gate_outcome(verdict: str) -> str:
    if verdict == "pass":
        return "PASS"
    if verdict == "conditional_pass":
        return "CONDITIONAL_PASS"
    return "BLOCKED"


def _write_gate_payload(
    *,
    path: Path,
    stage_id: str,
    name: str,
    assertion_results: dict[str, str],
    verdict: str,
    findings: list[str],
    evidence_paths: list[Path],
    next_skill: str,
    repair_applied: bool = False,
) -> dict[str, Any]:
    payload = {
        "stage_id": stage_id,
        "name": name,
        "status": verdict,
        "verdict": verdict,
        "generated_at_utc": utcnow_iso(),
        "assertions_checked": list(assertion_results.keys()),
        "assertion_results": assertion_results,
        "violations_found": sum(1 for value in assertion_results.values() if value != "pass"),
        "repair_applied": repair_applied,
        "gate_outcome": _gate_outcome(verdict),
        "next_skill": next_skill,
        "findings": findings,
        "evidence_paths": [str(path_item) for path_item in evidence_paths],
    }
    write_json(payload, path)
    return payload


def write_execution_deviations(
    summary: dict[str, Any],
    inputs: Path,
    outputs: Path,
    max_events: int | None,
) -> dict[str, Any]:
    requested_mode = summary["runtime_defaults"]["blinding"]
    overrides = []
    if max_events is not None:
        overrides.append(
            {
                "field": "max_events",
                "value": int(max_events),
                "effect": "partial_statistics_smoke_scope",
                "approved_for_central_claim": False,
            }
        )
    payload = {
        "status": "ok",
        "summary_path": summary["source_summary"],
        "inputs_root": str(inputs),
        "outputs_root": str(outputs),
        "overrides": overrides,
        "notes": [
            "No unblinding override is active for this run.",
            f"Observed significance allowed: {requested_mode['observed_significance_allowed']}.",
            f"Signal-window plotting blinded: {requested_mode['plot_signal_window']}.",
        ],
    }
    write_json(payload, outputs / "report" / "execution_deviations.json")
    return payload


def _sample_contract(sample: dict[str, Any]) -> dict[str, Any]:
    if sample["kind"] == "data":
        return {
            "sample_id": sample["sample_id"],
            "kind": "data",
            "physics_role": "observed_diphoton_data",
            "nominality": "central",
            "likelihood_role": "sideband_observed_data_source",
            "normalization_mode": "unit_weight_counting",
            "event_partitions": {
                "sidebands_105_120_and_130_160": "background_model_observed_data",
                "signal_window_120_130": "withheld_blinded_observed_data",
            },
            "disjoint_event_policy": "The invariant-mass sidebands and the blinded 120-130 GeV signal window are disjoint event partitions.",
        }
    if sample["analysis_role"] == "signal_nominal":
        likelihood_role = "signal_model_nominal"
    elif sample["analysis_role"] == "signal_alternative":
        likelihood_role = "signal_validation_only"
    elif sample["analysis_role"] == "background_nominal":
        likelihood_role = "spurious_signal_template_source"
    else:
        likelihood_role = "alternative_or_validation_only"
    return {
        "sample_id": sample["sample_id"],
        "kind": sample["kind"],
        "process_key": sample["process_key"],
        "physics_role": sample["analysis_role"],
        "nominality": "nominal" if sample["is_nominal"] else "alternative",
        "likelihood_role": likelihood_role,
        "normalization_mode": "cross section x k-factor x filter efficiency x signed generator-weight sum",
        "effective_lumi_fb": sample.get("effective_lumi_fb"),
        "weight_expression": sample["weight_expr"],
    }


def write_sample_semantics_artifacts(
    summary: dict[str, Any],
    registry: list[dict[str, Any]],
    process_roles: dict[str, Any],
    classification: dict[str, Any],
    strategy: dict[str, Any],
    outputs: Path,
) -> dict[str, Any]:
    intake = {
        "status": "ok",
        "analysis_target": summary["analysis_objectives"][0]["target_process"],
        "fit_id": next(iter(summary["fit_regions"])),
        "signal_signature": summary["signal_signatures"][0]["event_topology_description"],
        "signal_regions": [region["signal_region_id"] for region in summary["signal_regions"]],
        "control_regions": [region["control_region_id"] for region in summary["control_regions"]],
        "blinding_mode": "blinded",
        "template_policy": {
            "continuum_background": "data_sideband_analytic",
            "prompt_diphoton_mc": "spurious_signal_and_smoothing_only",
            "observed_data": "signal_window_hidden_in_blinded_mode",
        },
    }
    sample_strategy = {
        "status": "ok",
        "central_luminosity_fb": summary["runtime_defaults"]["central_mc_lumi_fb"],
        "normalization_basis": "cross section x k-factor x filter efficiency x signed generator-weight sum",
        "nominal_selection": process_roles["selected_nominal_samples"],
        "alternative_samples": process_roles["alternative_samples"],
        "classification": classification,
        "strategy": strategy,
    }
    sample_contracts = {
        "status": "ok",
        "central_luminosity_fb": summary["runtime_defaults"]["central_mc_lumi_fb"],
        "normalization_basis": "cross section x k-factor x filter efficiency x signed generator-weight sum",
        "samples": [_sample_contract(sample) for sample in registry],
    }
    template_contracts = {
        "status": "ok",
        "templates": [
            {
                "template_id": "continuum_background_sideband_model",
                "source_kind": "data",
                "source_region": "Selected diphoton events in 105-120 and 130-160 GeV sidebands for each category.",
                "target_use": "Analytic background model in the blinded Higgs-to-diphoton likelihood.",
                "observable": "m_gg",
                "normalization_mode": "floating analytic fit to observed sideband data",
                "overlap_policy": "Sideband data are disjoint from the blinded 120-130 GeV signal window by invariant-mass partition.",
                "closure_rationale": "The continuum background is smooth across the full fit range and is constrained with sideband-only observed data while the signal window remains hidden.",
            },
            {
                "template_id": "prompt_diphoton_spurious_signal_template",
                "source_kind": "MC",
                "source_process": "prompt_diphoton",
                "target_use": "Spurious-signal diagnostics and smoothing checks only.",
                "observable": "m_gg",
                "normalization_mode": "cross section x k-factor x filter efficiency x signed generator-weight sum",
                "overlap_policy": "The prompt-diphoton MC template source is distinct from all observed-data likelihood inputs.",
                "closure_rationale": "The template is reviewer-visible and auditable, but it is not promoted to the observed-data side of the central blinded likelihood.",
            },
        ],
    }
    write_json(intake, outputs / "report" / "likelihood_intake_decision.json")
    write_json(sample_strategy, outputs / "report" / "sample_strategy_decision.json")
    write_json(sample_contracts, outputs / "samples" / "sample_contracts.json")
    write_json(template_contracts, outputs / "templates" / "data_driven_template_contracts.json")
    return {
        "intake": intake,
        "sample_strategy": sample_strategy,
        "sample_contracts": sample_contracts,
        "template_contracts": template_contracts,
    }


def write_preflight_fact_check_review(outputs: Path) -> dict[str, Any]:
    preflight = read_json(outputs / "report" / "preflight_fact_check.json")
    contract = read_json(outputs / "report" / "execution_contract.json")
    evidence = [
        outputs / "report" / "preflight_fact_check.json",
        outputs / "report" / "execution_contract.json",
        outputs / "report" / "runtime_recovery.json",
    ]
    assertion_results = {
        "assertion_1": "pass",
        "assertion_2": "pass" if _all_exist(evidence) else "fail",
        "assertion_3": "pass"
        if preflight["status"] == "pass"
        and contract.get("requested_mode") in {"blinded", "unblinded"}
        and contract.get("analysis_name")
        else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_review_path(outputs, "preflight_fact_check_reviewer"),
        stage_id="preflight_fact_check_reviewer",
        name="Preflight Fact Check Reviewer",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=list(preflight.get("missing_or_ambiguous", [])),
        evidence_paths=evidence,
        next_skill="analysis_summary_reviewer.md" if verdict in {"pass", "conditional_pass"} else "runtime_and_preflight_wrapper.md",
    )


def write_analysis_summary_review(outputs: Path) -> dict[str, Any]:
    summary = read_json(outputs / "summary.normalized.json")
    diagnostics = read_json(outputs / "validation" / "diagnostics.json")
    overlap = read_json(outputs / "validation" / "overlap_policy.json")
    contract = read_json(outputs / "report" / "execution_contract.json")
    deviations = read_json(outputs / "report" / "execution_deviations.json")
    partition = read_json(outputs / "partition" / "partition_spec.json")
    summary_region_ids = {category["source_region_id"] for category in summary["categories"]}
    fit_region_refs = {
        region_id
        for fit_region in summary["fit_regions"].values()
        for region_id in fit_region["regions"]
    }
    evidence = [
        outputs / "summary.normalized.json",
        outputs / "validation" / "diagnostics.json",
        outputs / "validation" / "overlap_policy.json",
        outputs / "report" / "execution_contract.json",
        outputs / "report" / "execution_deviations.json",
        outputs / "partition" / "partition_spec.json",
    ]
    assertion_results = {
        "assertion_1": "pass",
        "assertion_2": "pass" if _all_exist(evidence) else "fail",
        "assertion_3": "pass"
        if diagnostics["status"] == "ok"
        and fit_region_refs.issubset(summary_region_ids)
        and "overrides" in deviations
        and overlap.get("default_allow_overlap") is False
        else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_review_path(outputs, "analysis_summary_reviewer"),
        stage_id="analysis_summary_reviewer",
        name="Analysis Summary Reviewer",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[],
        evidence_paths=evidence,
        next_skill="sample_and_template_semantics_pipeline.md" if verdict in {"pass", "conditional_pass"} else "summary_loader_wrapper.md",
    )


def write_nominal_sample_and_normalization_review(outputs: Path) -> dict[str, Any]:
    selection = read_json(outputs / "report" / "mc_sample_selection.json")
    strategy = read_json(outputs / "report" / "sample_strategy_decision.json")
    contracts = read_json(outputs / "samples" / "sample_contracts.json")
    norm_table = read_json(outputs / "normalization" / "norm_table.json")
    metadata = read_json(outputs / "normalization" / "metadata_resolution.json")
    evidence = [
        outputs / "report" / "likelihood_intake_decision.json",
        outputs / "samples.registry.json",
        outputs / "samples" / "sample_contracts.json",
        outputs / "report" / "mc_sample_selection.json",
        outputs / "normalization" / "norm_table.json",
        outputs / "normalization" / "metadata_resolution.json",
        outputs / "report" / "sample_strategy_decision.json",
    ]
    lumi_values = {row["target_lumi_fb"] for row in norm_table["rows"]}
    assertion_results = {
        "assertion_1": "pass",
        "assertion_2": "pass" if _all_exist(evidence) else "fail",
        "assertion_3": "pass"
        if contracts["central_luminosity_fb"] == 36.1 and lumi_values == {36.1}
        else "fail",
        "assertion_4": "pass"
        if strategy["normalization_basis"] == "cross section x k-factor x filter efficiency x signed generator-weight sum"
        and metadata["status"] == "ok"
        else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_review_path(outputs, "nominal_sample_and_normalization_reviewer"),
        stage_id="nominal_sample_and_normalization_reviewer",
        name="Nominal Sample and Normalization Reviewer",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[] if selection["status"] == "resolved" else ["Nominal sample selection remained unresolved."],
        evidence_paths=evidence,
        next_skill="likelihood_sample_role_reviewer.md" if verdict in {"pass", "conditional_pass"} else "sample_strategy_inversion.md",
    )


def write_likelihood_sample_role_review(outputs: Path) -> dict[str, Any]:
    contracts = read_json(outputs / "samples" / "sample_contracts.json")
    templates = read_json(outputs / "templates" / "data_driven_template_contracts.json")
    evidence = [
        outputs / "report" / "likelihood_intake_decision.json",
        outputs / "samples" / "sample_contracts.json",
        outputs / "report" / "mc_sample_selection.json",
        outputs / "templates" / "data_driven_template_contracts.json",
        outputs / "validation" / "overlap_policy.json",
        outputs / "cr_sr_constraint_map.json",
    ]
    required_fields = {"likelihood_role", "physics_role", "nominality", "normalization_mode"}
    contracts_ok = all(required_fields.issubset(sample) for sample in contracts["samples"])
    templates_ok = all(
        template.get("closure_rationale") and template.get("overlap_policy")
        for template in templates["templates"]
    )
    assertion_results = {
        "assertion_1": "pass",
        "assertion_2": "pass" if _all_exist(evidence) else "fail",
        "assertion_3": "pass" if contracts_ok else "fail",
        "assertion_4": "pass" if templates_ok else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_review_path(outputs, "likelihood_sample_role_reviewer"),
        stage_id="likelihood_sample_role_reviewer",
        name="Likelihood Sample Role Reviewer",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[],
        evidence_paths=evidence,
        next_skill="systematics_and_workspace_generator.md" if verdict in {"pass", "conditional_pass"} else "data_driven_template_generator.md",
    )


def write_statistical_readiness_review(outputs: Path, *, max_events: int | None) -> dict[str, Any]:
    likelihood_review = read_json(_review_path(outputs, "likelihood_sample_role_reviewer"))
    effective_lumi = read_json(outputs / "report" / "mc_effective_lumi_check.json")
    smoothing = read_json(outputs / "report" / "background_template_smoothing_check.json")
    smoothing_prov = read_json(outputs / "report" / "background_template_smoothing_provenance.json")
    background_choice = read_json(outputs / "fit" / FIT_ID / "background_pdf_choice.json")
    backend = read_json(outputs / "fit" / FIT_ID / "backend.json")
    fit_result = read_json(outputs / "fit" / FIT_ID / "results.json")
    asimov = read_json(outputs / "fit" / FIT_ID / "significance_asimov.json")
    parameter_policy = read_json(outputs / "fit" / FIT_ID / "significance_parameter_policy.json")
    evidence = [
        _review_path(outputs, "likelihood_sample_role_reviewer"),
        outputs / "report" / "mc_effective_lumi_check.json",
        outputs / "report" / "background_template_smoothing_check.json",
        outputs / "report" / "background_template_smoothing_provenance.json",
        outputs / "fit" / FIT_ID / "signal_pdf.json",
        outputs / "fit" / FIT_ID / "background_pdf_choice.json",
        outputs / "templates" / "data_driven_template_contracts.json",
        outputs / "systematics.json",
        outputs / "fit" / FIT_ID / "backend.json",
        outputs / "fit" / FIT_ID / "significance_asimov.json",
        outputs / "fit" / FIT_ID / "significance_parameter_policy.json",
    ]
    capped = [
        category
        for category, payload in background_choice["categories"].items()
        if payload.get("capped_noncompliant")
    ]
    assertion_results = {
        "assertion_1": "pass",
        "assertion_2": "pass" if _all_exist(evidence) and likelihood_review["verdict"] in {"pass", "conditional_pass"} else "fail",
        "assertion_3": "pass"
        if backend.get("primary_backend", backend.get("backend")) == "pyroot_roofit"
        and fit_result.get("backend") == "pyroot_roofit"
        else "fail",
        "assertion_4": "pass"
        if asimov.get("mu_gen") == 1.0
        and asimov.get("generation_hypothesis") == "signal_plus_background"
        and asimov.get("fit_range") == [105.0, 160.0]
        and parameter_policy.get("background_parameter_policy") == "floating_shape_and_normalization"
        else "fail",
    }
    findings = []
    if max_events is not None:
        findings.append("This run used max_events and is therefore a smoke-scope statistical check, not a full-statistics central result.")
    if fit_result.get("status") == "warning":
        findings.extend(fit_result.get("diagnostics", []))
    if asimov.get("status") == "warning":
        findings.extend(asimov.get("diagnostics", []))
    if capped:
        findings.append("Spurious-signal model selection reached the complexity cap in: " + ", ".join(sorted(capped)))
    if any(value != "pass" for value in assertion_results.values()):
        verdict = "block"
    elif findings or effective_lumi.get("status") != "ok" or smoothing.get("status") != "ok" or smoothing_prov.get("method") != "TH1::Smooth":
        verdict = "conditional_pass"
    else:
        verdict = "pass"
    return _write_gate_payload(
        path=_review_path(outputs, "statistical_readiness_reviewer"),
        stage_id="statistical_readiness_reviewer",
        name="Statistical Readiness Reviewer",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=findings,
        evidence_paths=evidence,
        next_skill="report_package_generator.md" if verdict in {"pass", "conditional_pass"} else "systematics_and_workspace_generator.md",
    )


def write_blinding_and_visualization_review(outputs: Path) -> dict[str, Any]:
    blinding = read_json(outputs / "report" / "blinding_summary.json")
    verification = read_json(outputs / "report" / "verification_status.json")
    measurement = read_json(outputs / "fit" / FIT_ID / "measurement_dataset.json")
    plot_manifest = read_json(outputs / "report" / "plots" / "manifest.json")
    report_text = (outputs / "report" / "report.md").read_text()
    evidence = [
        outputs / "report" / "blinding_summary.json",
        outputs / "report" / "plots" / "manifest.json",
        outputs / "report" / "report.md",
        outputs / "fit" / FIT_ID / "measurement_dataset.json",
    ]
    required_plot_groups = {"objects", "events", "control_regions_prefit", "control_regions_postfit", "fits"}
    blinded_mode_ok = (
        blinding["blinded"]
        and blinding["plot_signal_window"]
        and not blinding["observed_significance_allowed"]
        and measurement["blinding_policy_applied"]
    )
    explicit_unblinded_mode_ok = (
        not blinding["blinded"]
        and not blinding["plot_signal_window"]
        and blinding["observed_significance_allowed"]
        and not measurement["blinding_policy_applied"]
    )
    assertion_results = {
        "assertion_1": "pass",
        "assertion_2": "pass" if _all_exist(evidence) and required_plot_groups.issubset(plot_manifest["plot_groups"]) else "fail",
        "assertion_3": "pass"
        if (blinded_mode_ok or explicit_unblinded_mode_ok)
        and verification["status"] == "ok"
        and "*Caption:*" in report_text
        else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_review_path(outputs, "blinding_and_visualization_reviewer"),
        stage_id="blinding_and_visualization_reviewer",
        name="Blinding and Visualization Reviewer",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[],
        evidence_paths=evidence,
        next_skill="reproducibility_and_handoff_reviewer.md" if verdict in {"pass", "conditional_pass"} else "report_package_generator.md",
    )


def write_data_mc_discrepancy_review(outputs: Path) -> dict[str, Any]:
    audit = read_json(outputs / "report" / "data_mc_discrepancy_audit.json")
    evidence = [
        outputs / "report" / "plots" / "manifest.json",
        outputs / "report" / "data_mc_discrepancy_audit.json",
        outputs / "report" / "data_mc_check_log.json",
        outputs / "report" / "cutflow_table.json",
        outputs / "report" / "yields_by_category.json",
        outputs / "normalization" / "norm_table.json",
        outputs / "report" / "mc_sample_selection.json",
    ]
    assertion_results = {
        "assertion_1": "pass",
        "assertion_2": "pass" if _all_exist(evidence) else "fail",
        "assertion_3": "pass" if audit["status"] in {"no_substantial_discrepancy", "discrepancy_investigated_no_bug_found"} else "fail",
    }
    if any(value != "pass" for value in assertion_results.values()):
        verdict = "block"
    elif audit["status"] == "no_substantial_discrepancy":
        verdict = "conditional_pass"
    else:
        verdict = "pass"
    return _write_gate_payload(
        path=_review_path(outputs, "data_mc_discrepancy_reviewer"),
        stage_id="data_mc_discrepancy_reviewer",
        name="Data-MC Discrepancy Reviewer",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[],
        evidence_paths=evidence,
        next_skill="reproducibility_and_handoff_reviewer.md" if verdict in {"pass", "conditional_pass"} else "failure_to_skill_inversion.md",
    )


def write_reproducibility_and_handoff_review(outputs: Path, *, max_events: int | None) -> dict[str, Any]:
    gate = read_json(outputs / "report" / "enforcement_handoff_gate.json")
    final_review = read_json(outputs / "report" / "final_report_review.json")
    smoke = read_json(outputs / "report" / "smoke_test_execution.json")
    checkpoint = read_json(outputs / "report" / "skill_checkpoint_status.json")
    evidence = [
        outputs / "report" / "run_manifest.json",
        outputs / "report" / "smoke_test_execution.json",
        outputs / "report" / "skill_refresh_log.jsonl",
        outputs / "report" / "skill_checkpoint_status.json",
        outputs / "report" / "enforcement_handoff_gate.json",
        outputs / "report" / "report.md",
        outputs.parent / "reports" / "final_analysis_report.md",
        outputs / "report" / "skill_extraction_summary.json",
    ]
    assertion_results = {
        "assertion_1": "pass",
        "assertion_2": "pass" if _all_exist(evidence) else "fail",
        "assertion_3": "pass"
        if gate["status"] == "ok" and max_events is None and final_review["handoff_ready"] and checkpoint["status"] == "pass" and smoke["status"] == "ok"
        else "fail",
    }
    findings = []
    if max_events is not None:
        findings.append("Partial-statistics smoke runs are not handoff-ready central results.")
    findings.extend(final_review.get("handoff_gaps", []))
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_review_path(outputs, "reproducibility_and_handoff_reviewer"),
        stage_id="reproducibility_and_handoff_reviewer",
        name="Reproducibility and Handoff Reviewer",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=findings,
        evidence_paths=evidence,
        next_skill="human" if verdict == "block" else "handoff_complete",
    )


def write_reviewer_outcomes_index(outputs: Path) -> dict[str, Any]:
    reviewers = []
    for slug in REVIEW_ORDER:
        path = _review_path(outputs, slug)
        if not path.exists():
            continue
        payload = read_json(path)
        info = REVIEW_STAGE_INFO[slug]
        reviewers.append(
            {
                "stage_number": info["stage_number"],
                "reviewer": slug,
                "artifact": str(path),
                "verdict": payload["verdict"],
                "gate_outcome": payload["gate_outcome"],
            }
        )
    bundle = {
        "status": "ok",
        "generated_at_utc": utcnow_iso(),
        "reviewers": reviewers,
    }
    write_json(bundle, outputs / "report" / "reviewer_outcomes.json")
    return bundle


def _reviewer_passes(outputs: Path, slug: str) -> bool:
    path = _review_path(outputs, slug)
    if not path.exists():
        return False
    return read_json(path)["verdict"] in {"pass", "conditional_pass"}


def write_spec_to_runtime_pipeline_gate(outputs: Path) -> dict[str, Any]:
    contract = read_json(outputs / "report" / "execution_contract.json")
    evidence = [
        outputs / "report" / "preflight_fact_check.json",
        outputs / "summary.normalized.json",
        outputs / "validation" / "diagnostics.json",
        outputs / "report" / "execution_contract.json",
        outputs / "report" / "execution_deviations.json",
        _review_path(outputs, "analysis_summary_reviewer"),
        _review_path(outputs, "preflight_fact_check_reviewer"),
    ]
    assertion_results = {
        "assertion_1": "pass" if _all_exist(evidence[:-2]) else "fail",
        "assertion_2": "pass" if _reviewer_passes(outputs, "analysis_summary_reviewer") and _reviewer_passes(outputs, "preflight_fact_check_reviewer") else "fail",
        "assertion_3": "pass"
        if contract.get("source_summary")
        and contract.get("inputs_root")
        and contract.get("outputs_root")
        and contract.get("requested_mode") in {"blinded", "unblinded"}
        and contract.get("fit_mass_range_gev") == [105.0, 160.0]
        else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_gate_path(outputs, "spec_to_runtime_pipeline"),
        stage_id="spec_to_runtime_pipeline",
        name="Spec-to-Runtime Pipeline",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[],
        evidence_paths=evidence,
        next_skill="sample_and_template_semantics_pipeline.md" if verdict in {"pass", "conditional_pass"} else "summary_loader_wrapper.md",
    )


def write_sample_and_template_semantics_pipeline_gate(outputs: Path) -> dict[str, Any]:
    contracts = read_json(outputs / "samples" / "sample_contracts.json")
    evidence = [
        outputs / "report" / "likelihood_intake_decision.json",
        outputs / "report" / "sample_strategy_decision.json",
        outputs / "samples" / "sample_contracts.json",
        outputs / "templates" / "data_driven_template_contracts.json",
        _review_path(outputs, "nominal_sample_and_normalization_reviewer"),
        _review_path(outputs, "likelihood_sample_role_reviewer"),
    ]
    assertion_results = {
        "assertion_1": "pass" if _all_exist(evidence[:4]) else "fail",
        "assertion_2": "pass" if _reviewer_passes(outputs, "nominal_sample_and_normalization_reviewer") and _reviewer_passes(outputs, "likelihood_sample_role_reviewer") else "fail",
        "assertion_3": "pass" if contracts["central_luminosity_fb"] == 36.1 and contracts["normalization_basis"] == "cross section x k-factor x filter efficiency x signed generator-weight sum" else "fail",
        "assertion_4": "pass"
        if any(sample.get("event_partitions") for sample in contracts["samples"] if sample["kind"] == "data")
        else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_gate_path(outputs, "sample_and_template_semantics_pipeline"),
        stage_id="sample_and_template_semantics_pipeline",
        name="Sample and Template Semantics Pipeline",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[],
        evidence_paths=evidence,
        next_skill="systematics_and_workspace_generator.md" if verdict in {"pass", "conditional_pass"} else "sample_strategy_inversion.md",
    )


def write_reporting_and_handoff_pipeline_gate(outputs: Path) -> dict[str, Any]:
    report_text = (outputs / "report" / "report.md").read_text()
    evidence = [
        outputs / "report" / "report.md",
        outputs / "report" / "plots" / "manifest.json",
        outputs / "report" / "data_mc_discrepancy_audit.json",
        outputs / "report" / "enforcement_handoff_gate.json",
        outputs / "report" / "skill_extraction_summary.json",
        _review_path(outputs, "blinding_and_visualization_reviewer"),
        _review_path(outputs, "data_mc_discrepancy_reviewer"),
        _review_path(outputs, "reproducibility_and_handoff_reviewer"),
    ]
    assertion_results = {
        "assertion_1": "pass" if _all_exist(evidence[:2]) and "*Caption:*" in report_text else "fail",
        "assertion_2": "pass" if _all_exist(evidence[2:5]) and read_json(outputs / "report" / "enforcement_handoff_gate.json")["status"] == "ok" else "fail",
        "assertion_3": "pass"
        if _reviewer_passes(outputs, "blinding_and_visualization_reviewer")
        and _reviewer_passes(outputs, "data_mc_discrepancy_reviewer")
        and _reviewer_passes(outputs, "reproducibility_and_handoff_reviewer")
        else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_gate_path(outputs, "reporting_and_handoff_pipeline"),
        stage_id="reporting_and_handoff_pipeline",
        name="Reporting and Handoff Pipeline",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[],
        evidence_paths=evidence,
        next_skill="handoff_complete" if verdict in {"pass", "conditional_pass"} else "reproducibility_and_handoff_reviewer.md",
    )


def write_hep_analysis_meta_pipeline_gate(outputs: Path) -> dict[str, Any]:
    stage_log = read_json(outputs / "report" / "stage_execution_log.json")
    contracts = read_json(outputs / "samples" / "sample_contracts.json")
    execution = read_json(outputs / "report" / "execution_contract.json")
    fit_result = read_json(outputs / "fit" / FIT_ID / "results.json")
    asimov = read_json(outputs / "fit" / FIT_ID / "significance_asimov.json")
    evidence = [
        outputs / "report" / "stage_execution_log.json",
        outputs / "report" / "reviewer_outcomes.json",
        outputs / "samples" / "sample_contracts.json",
        outputs / "templates" / "data_driven_template_contracts.json",
        outputs / "fit" / FIT_ID / "results.json",
        outputs / "fit" / FIT_ID / "significance_asimov.json",
    ]
    required_stage_fields = {
        "stage_id",
        "started_at_utc",
        "ended_at_utc",
        "inputs_used",
        "outputs_written",
        "assumptions",
        "deviations",
        "unresolved_issues",
        "reviewers_run",
        "review_outcomes",
        "blocking_reasons",
        "next_skill",
    }
    stage_fields_ok = all(required_stage_fields.issubset(stage) for stage in stage_log["stages"])
    completed_with_reviews = all(
        stage["status"] != "completed"
        or all(outcome in {"pass", "conditional_pass"} for outcome in stage["review_outcomes"].values())
        for stage in stage_log["stages"]
    )
    no_blocked_stages = all(stage["status"] != "blocked" for stage in stage_log["stages"])
    assertion_results = {
        "assertion_1": "pass" if stage_fields_ok else "fail",
        "assertion_2": "pass" if completed_with_reviews and no_blocked_stages else "fail",
        "assertion_3": "pass"
        if contracts["central_luminosity_fb"] == 36.1 and execution["requested_mode"] in {"blinded", "unblinded"}
        else "fail",
        "assertion_4": "pass"
        if fit_result.get("backend") == "pyroot_roofit"
        and asimov.get("mu_gen") == 1.0
        and asimov.get("generation_hypothesis") == "signal_plus_background"
        and asimov.get("fit_range") == [105.0, 160.0]
        else "fail",
    }
    verdict = "pass" if all(value == "pass" for value in assertion_results.values()) else "block"
    return _write_gate_payload(
        path=_gate_path(outputs, "hep_analysis_meta_pipeline"),
        stage_id="hep_analysis_meta_pipeline",
        name="HEP Analysis Meta Pipeline",
        assertion_results=assertion_results,
        verdict=verdict,
        findings=[],
        evidence_paths=evidence,
        next_skill="handoff_complete" if verdict in {"pass", "conditional_pass"} else "human",
    )
