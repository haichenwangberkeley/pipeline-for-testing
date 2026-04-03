# Statistics Caveats Prompt

Use the prompt below when handing the Higgs-to-diphoton statistics stage to a future agent.

## Prompt

You are implementing the blinded statistical interpretation for the Higgs-to-diphoton analysis. Do not repeat these failure modes:

- Do not build the signal-plus-background Asimov dataset as a weighted `RooDataSet` made from bin-center samples of the PDFs. That approximation broke the self-fit and produced the wrong `mu` and `q0`.
- Do not assume `RooSimultaneous.fitTo()` on weighted or generated binned Asimov data will preserve the expected self-consistency check. In this workflow it did not.
- Do not allow negative signal strength in the blinded expected-only Asimov fit. If `mu < 0` is allowed, `n_sig = mu * s_const` can go negative, which creates nonphysical yields and can drive the one-sided discovery test statistic to `q0 = 0`.
- Do not approximate per-bin expected counts from PDF values at bin centers when the acceptance test is “fit S+B to S+B Asimov and recover `mu = 1`.” Use exact bin integrals.
- Do not trust pipeline gates alone as proof that the statistics are correct. Explicitly verify that a free fit to S+B Asimov returns `mu ~= 1` and that the fixed-`mu=0` profile fit gives `q0 > 0`.
- Do not unblind observed significance unless it is explicitly requested. In blinded mode, observed significance must remain blocked and the central claim must come from the expected-only Asimov procedure.
- Do not hide remaining RooFit or Minuit warnings. If the central values are physically correct but fit statuses are non-zero, preserve those diagnostics as warning-class findings.
- Do not forget that the background-function selection and spurious-signal checks are part of the interpretation contract. If the complexity cap is reached, document it explicitly.

Before you conclude the job, confirm all of the following:

- The blinded central fit uses S+B Asimov data, not observed signal-region data.
- The S+B Asimov self-fit returns `mu` consistent with `1.0`.
- The expected discovery significance from the same Asimov construction is non-zero.
- The report text and JSON artifacts quote the corrected values, not stale ones from a previous failed run.
