# Run Blinded And Unblinded Analysis

This is a terminal runbook for a human operator.

## 1. Clone And Select The Branch

Recommended repaired branch:

```bash
git clone https://github.com/haichenwangberkeley/pipeline-for-testing.git
cd pipeline-for-testing
git checkout repair/observed-stats-fixes-20260403
```

If you want the original pipeline instead:

```bash
git checkout main
```

## 2. Verify The Environment

```bash
./.codex/skills/hep-analysis-env-setup/scripts/check_repo_env.sh .
```

Optional test run:

```bash
./.codex/skills/hep-analysis-env-setup/scripts/run_in_repo_env.sh . -- .rootenv/bin/pytest -q
```

## 3. Run The Full Blinded Analysis

Use a fresh output directory so you do not overwrite existing products.

```bash
./.codex/skills/hep-analysis-env-setup/scripts/run_in_repo_env.sh . -- \
  .rootenv/bin/python -m analysis.cli run \
  --summary analysis/Higgs-to-diphoton.json \
  --inputs input-data \
  --outputs outputs_blinded_rerun
```

## 4. Inspect The Blinded Truth Artifacts

Central blinded fit:

```bash
cat outputs_blinded_rerun/fit/FIT1/results.json
```

Expected significance:

```bash
cat outputs_blinded_rerun/fit/FIT1/significance_asimov.json
```

Blinded report:

```bash
cat outputs_blinded_rerun/report/report.md
```

## 5. Run The Full Unblinded Analysis

This is the explicit unblinding command.

```bash
./.codex/skills/hep-analysis-env-setup/scripts/run_in_repo_env.sh . -- \
  .rootenv/bin/python -m analysis.cli run \
  --summary analysis/Higgs-to-diphoton.json \
  --inputs input-data \
  --outputs outputs_unblinded_rerun \
  --unblind-observed-significance
```

## 6. Inspect The Unblinded Truth Artifacts

Observed central fit:

```bash
cat outputs_unblinded_rerun/fit/FIT1/results.json
```

Observed significance:

```bash
cat outputs_unblinded_rerun/fit/FIT1/significance.json
```

Unblinded report:

```bash
cat outputs_unblinded_rerun/report/report.md
```

## 7. Inspect The Main Fit Plots

Blinded combined fit plot:

```bash
ls outputs_blinded_rerun/report/plots/fits/diphoton_mass_fit.*
```

Unblinded combined fit plot:

```bash
ls outputs_unblinded_rerun/report/plots/fits/diphoton_mass_fit.*
```

Category-level fit plots:

```bash
ls outputs_unblinded_rerun/report/plots/fits/
```

## 8. Check Reviewer And Gate Artifacts

Blinded run:

```bash
cat outputs_blinded_rerun/report/reviewers/statistical_readiness_reviewer.json
cat outputs_blinded_rerun/report/gates/hep_analysis_meta_pipeline.json
cat outputs_blinded_rerun/report/final_handoff_state.json
```

Unblinded run:

```bash
cat outputs_unblinded_rerun/report/reviewers/statistical_readiness_reviewer.json
cat outputs_unblinded_rerun/report/reviewers/blinding_and_visualization_reviewer.json
cat outputs_unblinded_rerun/report/gates/hep_analysis_meta_pipeline.json
cat outputs_unblinded_rerun/report/final_handoff_state.json
```

## 9. Expected Truth Values For Comparison

Repaired blinded expected-only truth:

```text
mu = 0.9991665268102753 +/- 0.14006375556981565
mu_hat_asimov = 1.0000004115176528 +/- 0.1413579119027894
q0_asimov = 52.80034062911661
Z_asimov = 7.266384288565848
```

Repaired unblinded observed truth:

```text
mu = 0.931271995657155 +/- 0.14101015627790825
mu_hat_observed_significance = 0.9347390287344728 +/- 0.13854442200965084
q0_observed = 47.12485814653337
Z_observed = 6.864754776868098
```
