"""
Correlated mean-reverting jump-diffusion simulator for hub prices (Phase 1).

Discretized log-OU process with jumps, per hub i, step size dt (in years):

    ln S_{t+1} = ln S_t + theta_i * (ln Sbar_i - ln S_t) * dt
                 + sigma_i * sqrt(dt) * eps_t
                 + J_t

eps_t are jointly correlated standard normal shocks across hubs (via
Cholesky decomposition of a correlation matrix); J_t is, with
probability jump_prob_i per step, drawn from N(jump_mu_i, jump_sigma_i^2)
and otherwise zero.

calibrate_from_prices() fits (s_bar, theta, sigma, jump_prob, jump_mu,
jump_sigma) to a real historical price series by simple moment matching:
an AR(1) fit on log levels gives theta/s_bar, then returns beyond
`jump_sigma_threshold` standard deviations are flagged as jumps and
fit separately, so day-to-day sigma isn't inflated by rare events. This
is the calibration path for hubs with real data (Henry Hub here).

For hubs without an accessible historical series (TTF, JKM, freight in
this project -- see docs/DATA_ACCESS.md), build a HubParams by hand from
published summary statistics instead of calling calibrate_from_prices();
HubParams.source records which path was used.
"""

import dataclasses
from dataclasses import dataclass, field

import numpy as np


@dataclass
class HubParams:
    name: str
    s_bar: float  # long-run mean price level (not log)
    theta: float  # mean-reversion speed, per year
    sigma: float  # diffusion volatility, annualized (applied as sigma*sqrt(dt) per step)
    jump_prob: float  # probability of a jump per step
    jump_mu: float  # mean jump size, in log-return units
    jump_sigma: float  # std of jump size, in log-return units
    dt: float  # step size in years (e.g. 1/252 daily)
    source: str = "assumed"  # "calibrated" (fit to real data) or "assumed" (public stats)
    notes: str = ""


def rescale_dt(params: HubParams, new_dt: float) -> HubParams:
    """
    Re-express a calibrated HubParams at a different step size. theta and
    sigma are continuous-time (annualized) rates and carry over unchanged;
    jump_prob is "probability per step", so it's rescaled to keep the
    implied *annual* jump rate (jump_prob / dt) constant. Useful for
    simulating at a finer resolution (e.g. weekly) than the data was
    calibrated at (monthly) -- see notebooks/05_optionality.ipynb.
    """
    scale = new_dt / params.dt
    return dataclasses.replace(params, dt=new_dt, jump_prob=params.jump_prob * scale)


def calibrate_from_prices(
    prices: np.ndarray,
    dt: float,
    jump_sigma_threshold: float = 3.0,
    name: str = "hub",
) -> HubParams:
    """Moment-match an OU-with-jumps model to a historical price series.

    `prices` must be strictly positive, chronologically ordered levels
    (drop non-positive/missing values before calling this -- see
    notebooks/02_calibrate_and_simulate.ipynb for the Henry Hub example,
    which has one zero-value data anomaly to filter first).
    """
    prices = np.asarray(prices, dtype=float)
    if np.any(prices <= 0):
        raise ValueError("prices must be strictly positive; filter non-positive values first")

    x = np.log(prices)
    x0, x1 = x[:-1], x[1:]

    # AR(1): x1 = a + b*x0 + residual  =>  theta = (1-b)/dt, s_bar = exp(a/(1-b))
    b, a = np.polyfit(x0, x1, 1)
    theta = (1.0 - b) / dt
    s_bar = float(np.exp(a / (1.0 - b))) if abs(1.0 - b) > 1e-12 else float(np.exp(x.mean()))

    residuals = x1 - (a + b * x0)
    resid_std_raw = residuals.std(ddof=1)
    jump_mask = np.abs(residuals - residuals.mean()) > jump_sigma_threshold * resid_std_raw

    normal_resid = residuals[~jump_mask]
    sigma = float(normal_resid.std(ddof=1) / np.sqrt(dt))
    jump_prob = float(jump_mask.mean())

    if jump_mask.sum() >= 2:
        jump_mu = float(residuals[jump_mask].mean())
        jump_sigma = float(residuals[jump_mask].std(ddof=1))
    else:
        jump_mu, jump_sigma = 0.0, 0.0

    return HubParams(
        name=name,
        s_bar=s_bar,
        theta=theta,
        sigma=sigma,
        jump_prob=jump_prob,
        jump_mu=jump_mu,
        jump_sigma=jump_sigma,
        dt=dt,
        source="calibrated",
        notes=f"AR(1)-fit to {len(prices)} observations; {int(jump_mask.sum())} steps flagged as jumps",
    )


def build_correlation_matrix(names: list[str], pairwise: dict[tuple[str, str], float]) -> np.ndarray:
    """Build a correlation matrix from a dict of {(name_i, name_j): corr}. Diagonal is 1."""
    n = len(names)
    idx = {name: i for i, name in enumerate(names)}
    corr = np.eye(n)
    for (i_name, j_name), rho in pairwise.items():
        i, j = idx[i_name], idx[j_name]
        corr[i, j] = corr[j, i] = rho
    return corr


def simulate_paths(
    hub_params: list[HubParams],
    corr_matrix: np.ndarray,
    n_paths: int,
    n_steps: int,
    start_prices: dict[str, float],
    seed: int | None = None,
) -> dict[str, np.ndarray]:
    """Simulate correlated price paths for all hubs.

    Returns {hub_name: array of shape (n_paths, n_steps+1)} of price levels
    (column 0 is start_prices).
    """
    dt = hub_params[0].dt
    if not all(abs(h.dt - dt) < 1e-12 for h in hub_params):
        raise ValueError("all hub_params must share the same dt")

    rng = np.random.default_rng(seed)
    n_hubs = len(hub_params)
    chol = np.linalg.cholesky(corr_matrix)

    log_paths = np.zeros((n_hubs, n_paths, n_steps + 1))
    for i, h in enumerate(hub_params):
        log_paths[i, :, 0] = np.log(start_prices[h.name])

    log_s_bar = np.array([np.log(h.s_bar) for h in hub_params])
    theta = np.array([h.theta for h in hub_params])
    sigma = np.array([h.sigma for h in hub_params])

    for t in range(n_steps):
        z = rng.standard_normal((n_paths, n_hubs))
        corr_z = z @ chol.T  # (n_paths, n_hubs), correlated standard normals

        x_t = log_paths[:, :, t]  # (n_hubs, n_paths)
        drift = theta[:, None] * (log_s_bar[:, None] - x_t) * dt
        diffusion = sigma[:, None] * np.sqrt(dt) * corr_z.T

        jumps = np.zeros((n_hubs, n_paths))
        for i, h in enumerate(hub_params):
            occurs = rng.random(n_paths) < h.jump_prob
            jumps[i, occurs] = rng.normal(h.jump_mu, h.jump_sigma, occurs.sum())

        log_paths[:, :, t + 1] = x_t + drift + diffusion + jumps

    return {h.name: np.exp(log_paths[i]) for i, h in enumerate(hub_params)}


def coverage_check(
    historical_prices: np.ndarray,
    params: HubParams,
    horizon_steps: int,
    n_paths: int = 2000,
    alpha: float = 0.1,
    stride: int | None = None,
    seed: int = 0,
) -> float:
    """
    Rolling calibration check: from each start point in `historical_prices`,
    simulate `n_paths` single-hub paths `horizon_steps` ahead and check
    whether the realized future price falls inside the empirical
    (alpha/2, 1-alpha/2) quantile band. Returns the fraction inside --
    should be close to (1 - alpha) if the calibration is reasonable.
    """
    prices = np.asarray(historical_prices, dtype=float)
    rng = np.random.default_rng(seed)
    n = len(prices)
    stride = stride or max(1, horizon_steps // 4)

    inside = []
    for s in range(0, n - horizon_steps, stride):
        x0 = np.log(prices[s])
        x = np.full(n_paths, x0)
        for _ in range(horizon_steps):
            z = rng.standard_normal(n_paths)
            drift = params.theta * (np.log(params.s_bar) - x) * params.dt
            diffusion = params.sigma * np.sqrt(params.dt) * z
            occurs = rng.random(n_paths) < params.jump_prob
            jump = np.where(occurs, rng.normal(params.jump_mu, params.jump_sigma, n_paths), 0.0)
            x = x + drift + diffusion + jump
        lo, hi = np.quantile(np.exp(x), [alpha / 2, 1 - alpha / 2])
        realized = prices[s + horizon_steps]
        inside.append(lo <= realized <= hi)

    return float(np.mean(inside))
