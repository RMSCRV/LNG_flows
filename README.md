# LNG Flows

**[Dashboard](lngflows.streamlit.app)** 

A stylized LNG trading model: simulate correlated hub prices, calculate netbacks across a small physical network, and optimize cargo allocation — naive vs. expected-value vs. risk-aware. Interactive dashboard where you can shock prices, capacity, and shipping routes and watch the optimal allocation reshuffle in real time.


- **Price simulator** — a correlated mean-reverting jump-diffusion model across five hubs (Henry Hub, TTF, JKM, and Atlantic/Pacific freight), calibrated on real historical data. Prices revert toward a long-run average but can jump on shocks, and hubs move together the way real gas and freight markets do.

- **Netback calculator** — for any origin-destination pair, works out what a cargo is actually worth after shipping, liquefaction, and other costs are subtracted from the destination price. The "best" market on a headline price basis often isn't the best once shipping cost is priced in.

- **Optimisation engine** — three strategies solve the same cargo allocation problem and are compared head-to-head on identical simulated scenarios:
  - *Naive*: always ship to whichever destination has the highest headline price, ignoring capacity.
  - *Expected-value*: a linear program that maximizes expected profit subject to liquefaction, storage, and vessel capacity.
  - *Risk-aware*: the same optimization, but penalized for downside risk (CVaR), trading some expected value for a safer worst case.

- **Stress tests** — push the network with demand spikes, shipping route disruptions (e.g. a canal closure), and capacity outages, then watch how each strategy's allocation and performance holds up.

- **Take-or-pay floors** — origins can carry a minimum contracted volume they must ship regardless of price, the way real long-term LNG contracts work, so the optimizer sometimes has to accept a worse deal rather than sit out a bad month.

- **Dashboard** — a live map of the network with adjustable shocks for prices, freight rates, capacity, and routes. Every control shows the resulting shift in allocation, expected value, and risk exposure immediately, so you can build intuition for how the whole system responds under stress.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run dashboard/app.py