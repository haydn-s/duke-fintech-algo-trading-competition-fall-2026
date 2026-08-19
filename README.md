# Duke University FinTech Algorithmic Trading Competition (Fall 2026)

A small, testable research and execution loop for the [Duke FinTech Trading
Competition](https://fintechtradingcompetition.com), Fall 2026. Paper trading
through Interactive Brokers.

## The objective function comes first

The competition does not rank on return. It ranks on Sharpe ratio computed
from end-of-day account NAV, with a risk-free rate fixed on day one:

```
R_p     = geometric mean of daily log returns of NAV
sigma_p = standard deviation of those returns
Sharpe  = (R_p - r_f) / sigma_p
```

Three properties of that formula drove every design decision here.

**Only end-of-day NAV is observed.** Intraday P&L is invisible to the score.
So there is no event loop, no message bus, no tick storage, and no
trade-level logging. One process runs once a day after the close, connects,
computes, trades, and exits. This is not a simplified version of the right
architecture; for this objective it is the right architecture.

**Sigma is measured over the entire competition, not a rolling window.** One
violent week in September permanently inflates the denominator of the
December Sharpe. You cannot un-observe a return. Volatility targeting is
therefore the load-bearing component, not a refinement -- see
`portfolio.vol_scaled`.

**Leverage is close to Sharpe-neutral; correlation is not.** Scaling every
position by `k` scales the numerator and the denominator together. What
actually raises the ratio is combining sleeves whose returns move
independently. The system is therefore built around running several
strategies simultaneously, with inverse-volatility allocation across them.

## Architecture

```
daily trigger (systemd timer, after the close)
      |
      +-- market data (daily bars, parquet cache)
      +-- broker state (NAV, positions, cash)
                |
        strategy sleeves        pure functions: (prices, asof) -> weights
                |
        allocator + risk        vol targeting, position caps, kill switch
                |
        rebalancer -> IBKR      diff weights against holdings, emit orders
                |
        NAV log + scorecard     the same math the judges use
```

### Strategies are pure functions returning weights, not orders

```python
def target_weights(self, prices: pd.DataFrame, asof: date) -> dict[str, float]:
    ...
```

A strategy does not know its capital, never touches a broker, places no
orders, and holds no state between calls. Sizing, leverage, and risk limits
live in exactly one place instead of being reimplemented inside every idea.
The consequence is that a strategy is testable with a hand-built DataFrame
and behaves identically in backtest and live.

### One broker protocol, two implementations

`SimBroker` replays history; `IBKRBroker` wraps a running IB Gateway. The
engine is byte-identical against both, so flipping one config flag is the
entire difference between a backtest and a live session. The code path that
gets validated is the code path that gets deployed.

### score.py is the metric everywhere

The competition's scoring math is reimplemented in `score.py` and used as the
backtest metric, the nightly report, and the promotion criterion for shadow
sleeves. Optimizing returns while being graded on Sharpe is an avoidable way
to lose. It is also the most heavily tested file in the repo, pinned against
the organizers' own published worked example.

### The shadow book

Every sleeve in the config computes weights daily, including sleeves
allocated zero capital. Unallocated sleeves are marked against real
subsequent prices into their own simulated NAV series. After six weeks a
shadow sleeve has genuine out-of-sample evidence behind it -- signals
generated before the prices that scored them existed. Promoting on that basis
is a decision; promoting on a backtest is a guess with a chart attached.

Cost: about forty lines and no capital at risk.

### nav_history.csv is committed daily

An append-only, timestamped record of account value, written before anyone
knows how the competition ends. It is what makes the final number credible to
someone reading this repository afterward.

## Layout

```
src/alphalab/
  score.py         competition scoring math -- the objective function
  engine.py        run_day(): the single shared trading-day code path
  portfolio.py     sleeve allocation and volatility targeting
  risk.py          position caps, exposure limits, drawdown kill switch
  rebalance.py     target weights -> orders (the only file that knows shares)
  shadow.py        out-of-sample tracking for unallocated sleeves
  backtest.py      replay a config over history, scored identically
  run.py           daily entrypoint
  config.py        typed loader; configs/live.yaml is the control surface
  data.py          daily bars with a local parquet cache
  strategies/      one file per idea
  brokers/         sim and IBKR behind one protocol
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,live]"
pytest
```

Live trading needs IB Gateway running and authenticated (paper account,
port 4002). Set `risk_free_annual_cmt_percent` in `configs/live.yaml` from
the Treasury's published 3-month CMT rate on the competition's first day and
then leave it alone -- it is fixed for the duration.

```bash
python -m alphalab.run --config configs/live.yaml --dry-run   # print orders only
python -m alphalab.run --config configs/live.yaml             # send them
```

Schedule with a systemd timer shortly after the close. Deliberately not
GitHub Actions: IB Gateway needs an authenticated session that does not
survive an ephemeral runner.

## Results

Populated as the competition runs.

## Disclaimer

Educational project. Paper trading only. Nothing here is investment advice,
and the strategies included are reference implementations of the interface
rather than claims that they make money.
