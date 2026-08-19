# Design decisions

Short records of choices that were not obvious, and what would change them.

## 1. No event loop

**Context.** The competition observes end-of-day NAV and nothing else.
Intraday drawdowns are invisible to the score.

**Decision.** A single process, triggered once daily after the close.

**Consequences.** No message bus, no daemon, no tick storage, no trade-level
logging. Roughly an order of magnitude less code, and the failure mode is a
cron job that did not run rather than a silently wedged consumer.

**What would change it.** A scoring change to intraday marks, or a strategy
whose edge decays within the day.

## 2. Strategies emit weights, not orders

**Context.** The alternative is strategies that place their own orders.

**Decision.** `(prices, asof) -> {symbol: weight}`, pure, stateless.

**Consequences.** Sizing and risk exist once instead of N times. Strategies
are unit-testable without a broker. Backtest and live share one path. The
cost is that a strategy cannot express order-level intent -- no limit prices,
no execution algorithms. At daily frequency on liquid instruments that costs
little.

## 3. Volatility targeting sits outside the strategies

**Context.** Sigma is computed over the full competition, so early
volatility is permanent.

**Decision.** A wrapper scales combined weights toward a target realized
volatility, capped by max leverage.

**Consequences.** Any strategy composes with it. When history is too short to
estimate volatility it is a no-op, which is the right failure mode early on.

## 4. score.py replicates the published method, including its quirks

**Context.** The organizers apply the geometric-mean formula to returns that
are already logarithmic, and verify a log return with `V * (1 + r)` rather
than `V * exp(r)`.

**Decision.** Replicate what they publish rather than what is conventional.

**Consequences.** Backtest numbers and leaderboard position are directly
comparable. The difference is negligible at daily magnitudes but it is not
zero, and being scored on a metric you did not optimize is avoidable. Both
quirks are documented in `score.py` and pinned in `tests/test_score.py`.

## 5. The shadow book

**Context.** Backtests overfit. Six weeks into a three-month competition
there is real information about which sleeves are working, but acting on a
backtest is guessing.

**Decision.** Unallocated sleeves compute weights daily and are marked
against subsequent real prices.

**Consequences.** Promotion decisions rest on out-of-sample evidence. Costs
about forty lines and no capital.

## 6. Whole shares and a no-trade band

**Context.** Weight drift of a fraction of a percent otherwise generates
orders every day.

**Decision.** Skip rebalances below 0.5% of NAV; round to whole shares.

**Consequences.** Commission and slippage stop grinding down the numerator
for exposure changes too small to matter.

## 7. Credentials live in .env, not in the config file

**Context.** `configs/live.yaml` is the control surface and is tracked, so it
is the obvious place to put an account id and the wrong one. Meanwhile the
repository had no `.gitignore` at all, so a single `git add .` would have
committed the price cache and anything else lying around.

**Decision.** Split by secrecy rather than by topic. Host, port, and client id
stay in `configs/live.yaml`: they are not secret, and being able to read them
in a diff is worth something. The paper account id -- and the login, if IBC is
automating the gateway -- go in `.env`, which is gitignored, with `.env.example`
tracked as the template. Environment variables win over the file so a systemd
`EnvironmentFile=` needs no code change.

**Consequences.** A twelve-line stdlib parser instead of a dependency, because
a live run failing over a dotenv release's quote handling is not a trade worth
making. `Credentials.__repr__` is redacted, since the object lands in
tracebacks. Non-paper account ids are refused at startup: the competition is
paper-only, and finding out at the first order is worse than finding out at
import.

**What would change it.** A secret manager already in the deployment, or a
broker whose API actually authenticates rather than attaching to an
authenticated session.
