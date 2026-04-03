# Labbook

## Executive Summary

### Done
- Repaired the missing workspace-local `.rootenv` shim so `./.codex/skills/hep-analysis-env-setup/scripts/check_repo_env.sh .` and skill-wrapped `pytest` pass under the required RooFit-primary runtime.
- Repaired the pipeline/reporting layer to emit explicit execution deviations, sample-semantics records, reviewer verdicts, pipeline gate artifacts, and fail-closed handoff behavior for partial-statistics smoke runs.
- Repaired the blinded Asimov statistics path so the expected-only self-fit now returns `mu ~= 1.0` and a non-zero expected discovery significance from the signal-plus-background Asimov data.
- Repaired the unblinded observed-data central fit and observed-significance calculation so both now use a summed per-category unbinned NLL instead of the old simultaneous `fitTo()` path.
- Executed a clean smoke run in `outputs_smoke_blinded_gatecheck` and a corrected full blinded analysis in `outputs_blinded_full`.
- Executed a corrected full unblinded analysis in `outputs_unblinded_full_fixed_20260403`.
- Verified final blinded handoff readiness from `outputs_blinded_full/report/final_handoff_state.json`, `outputs_blinded_full/report/reviewer_outcomes.json`, and `outputs_blinded_full/report/gates/hep_analysis_meta_pipeline.json`.

### Work In Progress
- No active code changes remain in progress, but both the blinded and unblinded statistical outputs are still reviewer-labeled `conditional_pass` or `warning` rather than pristine passes.
- The main open technical issues are the remaining non-zero RooFit/Minuit statuses and the spurious-signal model-selection cap in both blinded and unblinded statistical outputs.

### Next
- If a cleaner expected-only statistical result is required, investigate the spurious-signal model cap and the remaining non-zero Minuit/RooFit status diagnostics in `outputs_blinded_full/fit/FIT1/background_pdf_choice.json`, `outputs_blinded_full/fit/FIT1/results.json`, and `outputs_blinded_full/fit/FIT1/significance_asimov.json`.
- If the current unblinded result is acceptable, package or archive `outputs_unblinded_full_fixed_20260403` and the associated plot set under `outputs_unblinded_full_fixed_20260403/report/plots/`.
- If a cleaner unblinded statistical status is required, investigate the remaining non-zero Minuit/RooFit diagnostics in `outputs_unblinded_full_fixed_20260403/fit/FIT1/results.json` and `outputs_unblinded_full_fixed_20260403/fit/FIT1/significance.json`.

## Entries

### 2026-04-03 11:06 AM PDT — Repair pipeline and complete blinded run
- Inspected the repo against the bound HEP skills and found the first hard blocker in the runtime contract: the workspace-local `.rootenv` required by `hep-analysis-env-setup` was missing. Repaired this with a local `.rootenv` shim targeting the verified Python 3.11 + PyROOT stack already installed on the machine, then re-ran the environment check and wrapped tests successfully.
- Patched the reporting/pipeline layer so the run now writes explicit skill-compliant artifacts: `analysis/report/reviews.py`, updated `analysis/pipeline.py`, and updated `analysis/report/artifacts.py` now emit `execution_deviations`, sample intake and template contracts, reviewer verdict artifacts under `outputs*/report/reviewers/`, pipeline gate artifacts under `outputs*/report/gates/`, and stage logs with reviewer outcomes.
- Added a guard so smoke runs cannot masquerade as final central results: `write_final_review(..., max_events=...)` now blocks partial-statistics handoff, and the test suite in `tests/test_reporting_contracts.py` covers that path.
- Updated `pyproject.toml` to align the declared Python requirement with the verified runnable runtime (`>=3.11`).
- Produced a clean smoke reference in `outputs_smoke_blinded_gatecheck`. Its statistical reviewer is intentionally `conditional_pass` because the run is partial-statistics, while the reproducibility and reporting gates remain blocked by policy, not by missing artifacts.
- Executed the full blinded production run in `outputs_blinded_full`. The full run reached `handoff_ready: true` in `outputs_blinded_full/report/final_handoff_state.json`, with `reproducibility_and_handoff_reviewer` returning `pass` and the meta-pipeline gate returning `PASS`.
- The full blinded statistical stage is not pristine: `outputs_blinded_full/report/reviewers/statistical_readiness_reviewer.json` records `conditional_pass`, driven by capped spurious-signal model selection and non-zero RooFit statuses in the Asimov significance fits. The blinded run still keeps observed significance blocked, as required.

### 2026-04-03 11:40 AM PDT — Repair blinded Asimov statistics and rerun full handoff
- Investigated the user-reported physics inconsistency in the blinded expected-only stage and confirmed the previous implementation was wrong: fitting the signal-plus-background model back to signal-plus-background Asimov data did not return `mu = 1`, and the expected discovery test statistic collapsed to zero.
- Replaced the weighted bin-center Asimov approximation in `analysis/stats/fit.py` and `analysis/stats/significance.py` with an exact per-bin Asimov construction. The blinded fit and significance stages now use a summed per-category binned NLL with exact bin integrals and Minuit2 minimization, while preserving the PyROOT/RooFit backend contract.
- Added a regression test in `tests/test_stats_asimov.py` that checks the exact-Asimov fitter on a toy model, and re-ran the full test suite successfully (`7 passed`).
- Replayed the statistics stage in a debug output area first to verify the fix numerically, then reran the full blinded pipeline in `outputs_blinded_full`.
- The corrected production artifacts now show the expected-only self-fit behaving properly: `outputs_blinded_full/fit/FIT1/results.json` has `mu_hat = 0.9991665268 +/- 0.1400637556`, and `outputs_blinded_full/fit/FIT1/significance_asimov.json` has `mu_hat = 1.0000004115`, `q0 = 52.8003406291`, and `Z = 7.2663842886`.
- Final handoff remains ready after the rerun: `outputs_blinded_full/report/final_report_review.json` is `status: ok`, `outputs_blinded_full/report/final_handoff_state.json` is `status: ok`, and `outputs_blinded_full/report/gates/hep_analysis_meta_pipeline.json` remains `pass`.
- The remaining caveat is unchanged in class but not in central value: the statistical reviewer stays at `conditional_pass` because RooFit/Minuit statuses remain non-zero and the spurious-signal model-selection cap is still hit in all five categories.

### 2026-04-03 12:54 PM PDT — Propagate statistics repair to observed fit and observed significance
- Investigated the user-reported unblinded pathology and confirmed the previous repair had only touched the blinded Asimov branch. The observed central measurement fit still used the old simultaneous `fitTo()` path in `analysis/stats/fit.py`, and the observed significance stage still profiled `mu` through the old helper in `analysis/stats/significance.py`.
- Added a generic per-category NLL minimizer in `analysis/stats/fit.py`, then routed the observed central fit through a summed per-category unbinned NLL and kept the blinded expected-only stage on the exact binned Asimov NLL. The observed-significance calculation now also uses the summed per-category unbinned NLL with `mu >= 0` enforced for the one-sided discovery profile.
- Added a toy observed-data regression in `tests/test_stats_asimov.py` and reran the full test suite successfully (`8 passed`).
- Reran the full explicitly unblinded pipeline in `outputs_unblinded_full_fixed_20260403`. The repaired observed central fit now gives `mu_hat = 0.931272 +/- 0.141010`, and the observed significance gives `Z = 6.864755` with `q0 = 47.124858`.
- The key normalization pathology is gone in the fit payload: `outputs_unblinded_full_fixed_20260403/fit/FIT1/fit_plot_payload.json` sums to `228497.8855` events, matching the observed selected-event total (`228498`) instead of the old over-normalized result.
- The repaired unblinded fit plots are in `outputs_unblinded_full_fixed_20260403/report/plots/fits/`, with the combined observed fit at `outputs_unblinded_full_fixed_20260403/report/plots/fits/diphoton_mass_fit.png`.
- Repaired the unblinding-aware reviewer logic in `analysis/report/reviews.py`, refreshed the affected reviewer and gate artifacts on `outputs_unblinded_full_fixed_20260403`, and confirmed that `report/reviewers/blinding_and_visualization_reviewer.json` and `report/gates/hep_analysis_meta_pipeline.json` now both return `pass` for the explicit unblinded run.
- The remaining caveats are now statistical-quality warnings rather than gate-policy bugs: the statistical reviewer stays `conditional_pass` due non-zero RooFit/Minuit statuses and the spurious-signal cap, but the final handoff state and meta-pipeline gate both accept the repaired unblinded run.
