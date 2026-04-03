# Statistics Implementation Prompt

Use the prompt below when asking a future agent to implement or repair a blinded statistical interpretation procedure. It is intentionally analysis-agnostic and focuses on technical correctness, numerical stability, validation, and artifact consistency rather than any one physics channel.

## Prompt

Implement the blinded statistical interpretation exactly and defensibly. Follow these requirements in order:

1. Work from the authoritative specification and the actual processed model used in the repository.
   - Infer channels, categories, observables, regions, and parameter-sharing rules from the spec and artifacts instead of hard-coding analysis-specific assumptions.
   - Preserve the declared mapping between samples, templates, nuisance parameters, and parameters of interest.

2. Build the signal model only from the designated signal reference inputs.
   - Fit the signal-shape model using the signal reference sample or simulation specified by the analysis contract.
   - Freeze signal-shape parameters before the final statistical interpretation unless the contract explicitly requires them to float.
   - Keep the signal-yield parameterization transparent and physically interpretable.

3. Determine the background model only from the allowed background-constraining inputs.
   - Use the designated sidebands, control regions, or background-dominated data source rather than blinded signal-region data.
   - Scan only the allowed background-model families from the analysis contract.
   - Save the parameter snapshot for the selected background model so the final inference stage has a reproducible starting point.
   - Preserve any required model-selection diagnostics or goodness criteria as explicit artifacts.

4. Build the final per-channel or per-category signal-plus-background model with the intended shared parameters.
   - Use the parameter of interest exactly as specified by the contract.
   - If the signal yield is factored as a parameter of interest times a fixed expected yield, preserve that relationship explicitly.
   - Initialize floating background parameters from the background-only or control-region fit snapshot when required.
   - Let only the parameters authorized by the contract float in the final fit.

5. Enforce the blinding policy at the likelihood-construction stage, not just in the report.
   - In blinded expected-only mode, do not fit observed signal-region data.
   - In blinded mode, block observed significance or observed signal-region claims unless explicit unblinding is requested.
   - If the expected-only procedure uses a one-sided test statistic, enforce the corresponding physical parameter bounds during that stage.

6. Construct Asimov data from exact expected bin yields, not from bin-center approximations.
   - For each channel or category and each analysis bin, integrate the model over the full bin range to obtain the expected contribution.
   - Normalize each component to its intended yield before summing components.
   - Build the Asimov sample from those exact per-bin expectations.
   - Prefer a genuinely binned Asimov representation such as `RooDataHist` when the downstream likelihood is binned.
   - Record the Asimov construction mode explicitly in the artifacts.

7. Evaluate the expected-only likelihood in a way that matches the data representation.
   - If the Asimov sample is binned, build a binned likelihood from per-channel or per-category terms and combine them into a single total NLL.
   - Use bin-integrated PDF evaluation rather than point evaluation at bin centers.
   - Use offsetting or equivalent numerical-stability options when supported by the backend.
   - Minimize the total NLL with an explicit minimizer configuration and capture both backend-level and minimizer-level statuses.

8. Validate the central expected-only fit before accepting it.
   - A free fit to signal-plus-background Asimov data must recover the injected parameter-of-interest value within numerical precision.
   - The fitted uncertainty on the parameter of interest must be positive and finite.
   - Treat a failed Asimov self-fit as a statistical implementation bug, not a cosmetic warning.
   - If central values are correct but fit statuses are non-zero, preserve those diagnostics as warnings instead of hiding them.

9. Compute expected test statistics from the same exact construction used for the central expected-only fit.
   - Generate the Asimov sample under the intended injected hypothesis.
   - Evaluate the free fit and the constrained fit required by the chosen test statistic.
   - Compute the reported test statistic directly from the profiled NLL values.
   - For one-sided discovery-style tests, verify that the Asimov self-fit returns the injected signal strength and that the resulting significance is strictly positive when signal is injected.

10. Keep implementation, metadata, and outputs synchronized.
   - Make the recorded method description match the actual implementation.
   - Update fit-result artifacts, significance artifacts, construction metadata, and report text together.
   - Do not leave stale method labels, stale central values, or stale diagnostics from a previous run.
   - If the implementation changes from an approximate method to an exact method, update the artifact vocabulary accordingly.

11. Preserve reviewer and gate semantics.
   - Do not suppress legitimate warnings just to make a gate pass.
   - Propagate fit-quality problems, convergence problems, capped model-selection findings, and other readiness issues into the reviewer outputs.
   - Keep blocked observed quantities blocked in blinded mode.

12. Run end-to-end verification before handoff.
   - Re-run the relevant tests.
   - Re-run the full blinded pipeline or the full downstream chain needed to regenerate dependent reports and gates.
   - Inspect the final artifacts directly rather than trusting a summary layer alone.
   - Accept the implementation only if the Asimov self-fit is correct, the expected test statistic behaves physically, and all remaining warnings are documented rather than hidden.
