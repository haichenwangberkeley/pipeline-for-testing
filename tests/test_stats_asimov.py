import ROOT
import numpy as np

from analysis.stats.fit import build_exact_asimov_dataset, fit_exact_binned_category_nll_sum, fit_unbinned_category_nll_sum
from analysis.stats.models import MASS_RANGE_GEV, background_candidate, configure_mass_var, make_weighted_dataset

ROOT.gROOT.SetBatch(True)


def test_exact_binned_asimov_fit_recovers_unit_signal_strength():
    mass = configure_mass_var("mgg_toy")
    channel = ROOT.RooCategory("channel_toy", "channel_toy")
    channel.defineType("toy")
    shared_mu = ROOT.RooRealVar("mu_toy", "mu_toy", 1.0, 0.0, 10.0)

    mean = ROOT.RooRealVar("mean_toy", "mean_toy", 125.0)
    sigma = ROOT.RooRealVar("sigma_toy", "sigma_toy", 1.8, 0.1, 5.0)
    mean.setConstant(True)
    sigma.setConstant(True)
    signal_pdf = ROOT.RooGaussian("sigpdf_toy", "sigpdf_toy", mass, mean, sigma)

    background = background_candidate("toy", mass, "exponential")
    for param in background.params:
        param.setVal(-0.03)

    s_const = ROOT.RooRealVar("sconst_toy", "sconst_toy", 80.0)
    s_const.setConstant(True)
    nsig = ROOT.RooFormulaVar("nsig_toy", "@0*@1", ROOT.RooArgList(shared_mu, s_const))
    nbkg = ROOT.RooRealVar("nbkg_toy", "nbkg_toy", 1500.0, 0.0, 5000.0)
    model = ROOT.RooAddPdf(
        "model_toy",
        "model_toy",
        ROOT.RooArgList(signal_pdf, background.pdf),
        ROOT.RooArgList(nsig, nbkg),
    )

    category_context = {"toy": {"template_total_yield": 1500.0}}
    final_models = {
        "toy": {
            "model": model,
            "signal_pdf": signal_pdf,
            "background_pdf": background.pdf,
            "s_const": s_const,
            "nsig": nsig,
            "nbkg": nbkg,
        }
    }

    _, category_hists, _ = build_exact_asimov_dataset(
        category_context=category_context,
        final_models=final_models,
        common_mass=mass,
        channel=channel,
        dataset_name="asimov_toy",
    )
    free_fit = fit_exact_binned_category_nll_sum(
        final_models=final_models,
        category_datahists=category_hists,
        shared_mu=shared_mu,
        mu_value=None,
    )
    free_nll = float(free_fit["nll_value"])
    mu_hat = float(shared_mu.getVal())
    mu_uncertainty = float(shared_mu.getError())
    mu0_fit = fit_exact_binned_category_nll_sum(
        final_models=final_models,
        category_datahists=category_hists,
        shared_mu=shared_mu,
        mu_value=0.0,
    )

    q0 = max(2.0 * (float(mu0_fit["nll_value"]) - free_nll), 0.0)

    assert abs(mu_hat - 1.0) < 1e-3
    assert mu_uncertainty > 0.0
    assert q0 > 0.0


def _sample_truncated_gaussian(rng: np.random.Generator, mean: float, sigma: float, size: int) -> np.ndarray:
    samples: list[np.ndarray] = []
    total = 0
    while total < size:
        trial = rng.normal(mean, sigma, size=max(size - total, 16))
        accepted = trial[(trial >= MASS_RANGE_GEV[0]) & (trial <= MASS_RANGE_GEV[1])]
        if accepted.size == 0:
            continue
        samples.append(accepted[: size - total])
        total += min(accepted.size, size - total)
    return np.concatenate(samples)


def _sample_truncated_exponential(rng: np.random.Generator, tau: float, size: int) -> np.ndarray:
    width = MASS_RANGE_GEV[1] - MASS_RANGE_GEV[0]
    u = rng.uniform(0.0, 1.0, size=size)
    scale = np.exp(tau * width) - 1.0
    return MASS_RANGE_GEV[0] + np.log1p(u * scale) / tau


def test_unbinned_observed_fit_recovers_injected_signal_strength():
    rng = np.random.default_rng(12345)
    mass = configure_mass_var("mgg_obs_toy")
    shared_mu = ROOT.RooRealVar("mu_obs_toy", "mu_obs_toy", 1.0, 0.0, 10.0)

    mean = ROOT.RooRealVar("mean_obs_toy", "mean_obs_toy", 125.0)
    sigma = ROOT.RooRealVar("sigma_obs_toy", "sigma_obs_toy", 1.8, 0.1, 5.0)
    mean.setConstant(True)
    sigma.setConstant(True)
    signal_pdf = ROOT.RooGaussian("sigpdf_obs_toy", "sigpdf_obs_toy", mass, mean, sigma)

    background = background_candidate("obs_toy", mass, "exponential")
    tau = background.params[0]
    tau.setVal(-0.03)

    s_const = ROOT.RooRealVar("sconst_obs_toy", "sconst_obs_toy", 80.0)
    s_const.setConstant(True)
    nsig = ROOT.RooFormulaVar("nsig_obs_toy", "@0*@1", ROOT.RooArgList(shared_mu, s_const))
    nbkg = ROOT.RooRealVar("nbkg_obs_toy", "nbkg_obs_toy", 1500.0, 0.0, 5000.0)
    model = ROOT.RooAddPdf(
        "model_obs_toy",
        "model_obs_toy",
        ROOT.RooArgList(signal_pdf, background.pdf),
        ROOT.RooArgList(nsig, nbkg),
    )

    signal_masses = _sample_truncated_gaussian(rng, mean=125.0, sigma=1.8, size=80)
    background_masses = _sample_truncated_exponential(rng, tau=-0.03, size=1500)
    observed = np.concatenate([signal_masses, background_masses])
    rng.shuffle(observed)
    dataset = make_weighted_dataset("obs_toy_data", mass, observed)

    final_models = {
        "toy": {
            "model": model,
            "signal_pdf": signal_pdf,
            "background_pdf": background.pdf,
            "s_const": s_const,
            "nsig": nsig,
            "nbkg": nbkg,
        }
    }

    free_fit = fit_unbinned_category_nll_sum(
        final_models=final_models,
        category_datasets={"toy": dataset},
        shared_mu=shared_mu,
        mu_value=None,
    )
    free_nll = float(free_fit["nll_value"])
    mu_hat = float(shared_mu.getVal())
    mu_uncertainty = float(shared_mu.getError())
    mu0_fit = fit_unbinned_category_nll_sum(
        final_models=final_models,
        category_datasets={"toy": dataset},
        shared_mu=shared_mu,
        mu_value=0.0,
    )
    q0 = max(2.0 * (float(mu0_fit["nll_value"]) - free_nll), 0.0)

    assert abs(mu_hat - 1.0) < 0.35
    assert mu_uncertainty > 0.0
    assert q0 > 0.0
