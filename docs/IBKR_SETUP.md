# IBKR paper trading setup

Everything needed to get `python -m alphalab.run` talking to a paper account.
Budget an hour, most of it waiting on IBKR rather than working.

Read this once before starting, because step 1 has a fork in it that is
annoying to undo.

## The one thing to understand first

The Python API does not log in. `ib_async` opens a socket to an IB Gateway
process that is **already authenticated** and speaks to it. Nothing in this
repository ever sees your IBKR password.

That has three consequences that shape the rest of this document:

- The gateway has to be running before the daily job fires.
- Host, port, and client id are not secrets, so they live in
  `configs/live.yaml` where you can read them in a diff.
- The only value this repo strictly needs kept out of git is your paper
  account id, in `.env`.

## 1. Create the paper account

Two routes. They differ in market data, which is the part that bites later.

**Route A -- paper account attached to a real IBKR account.** Open an IBKR
account normally, then in Client Portal go to Settings → Account Settings and
create the paper trading account. You get a separate paper username and set
its own password.

**Route B -- standalone paper account.** IBKR offers a free trial paper
account from ibkr.com without funding or full onboarding. Faster, no identity
verification, no money involved.

Route A is the better choice here, and the reason is market data. A
standalone paper account carries no market data subscription, and this
codebase prices every symbol on every rebalance (`rebalance.orders_from_weights`
calls `last_price` per symbol). No quotes means the daily run fails partway
through rather than trading. A paper account attached to a funded account
inherits that account's market data subscriptions. See
[section 6](#6-market-data-the-part-that-actually-breaks).

Paper accounts start at $1,000,000 of simulated equity by default. You can
reset the balance from Client Portal, which is also how you recover from a
strategy bug that blows the account up in week one.

## 2. Find your account id

Log into Client Portal with the **paper** username. The account id is shown
top-right. It looks like `DU1234567`.

Paper ids begin with `DU` (or `DF` for advisor paper). Live ids begin with `U`
or `F`. `alphalab.credentials` refuses anything that is not a paper prefix, so
a live id cannot be used by accident — the run stops at startup rather than
at the first order.

## 3. Install IB Gateway

Download **IB Gateway** (not TWS) from IBKR's software page. Gateway is the
same API endpoint without the trading GUI: less memory, fewer dialogs, and
nothing that can pop a modal in front of an unattended job.

Start it and choose **Paper Trading** as the mode at the login screen. Log in
with the paper username from step 1.

## 4. Turn on the API

In IB Gateway: **Configure → Settings → API → Settings**.

| Setting | Value | Why |
|---|---|---|
| Enable ActiveX and Socket Clients | ✅ on | Without this nothing can connect. |
| Socket port | `4002` | Gateway paper. Matches `configs/live.yaml`. |
| Trusted IPs | `127.0.0.1` | The job runs on the same host. |
| Read-Only API | ✅ **leave on for now** | Blocks order placement at the gateway. |
| Master API client ID | blank | The repo connects with client id 17. |

Leave **Read-Only API on** until you have watched a full day of proposed
orders. It is a second, independent lock on top of `dry_run: true` in
`configs/live.yaml`, and it lives on the other side of the socket where a bug
in this repository cannot reach it. Turn it off only when you flip `dry_run`.

Port reference, since mixing these up produces a confusing silence:

| | Paper | Live |
|---|---|---|
| IB Gateway | **4002** | 4001 |
| TWS | 7497 | 7496 |

## 5. Store the account id

```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env          # set IBKR_ACCOUNT=DU...
```

`.env` is gitignored; `.env.example` is the tracked template. Confirm it:

```bash
git check-ignore -v .env      # prints the matching .gitignore rule
git status --short            # .env must not appear
```

Leave `IBKR_USERNAME` and `IBKR_PASSWORD` commented out if you start the
gateway by hand. A stored brokerage password that nothing reads back is a
liability with no upside. Only fill them in if you set up IBC
([section 8](#8-optional-unattended-login-with-ibc)).

Values already in the environment win over the file, so a systemd unit can
supply them with `EnvironmentFile=` and nothing here changes.

## 6. Market data, the part that actually breaks

`last_price` calls `reqMktData` and raises `no usable price for SYMBOL` when
nothing comes back. Every rebalance prices every symbol, so this is not a
cosmetic failure — the run dies.

If you have no subscription, one of:

- **Subscribe.** Client Portal → Settings → Market Data Subscriptions. US
  equities for the ETFs in `configs/live.yaml` costs a few dollars a month,
  and a paper account attached to a live account inherits the entitlement.
- **Use delayed data.** Call `ib.reqMarketDataType(3)` once after connecting.
  Delayed quotes are 15 minutes stale, which is harmless for a job that runs
  after the close and sizes orders off daily bars, but note the repo does not
  do this today — you would be adding a line to `IBKRBroker.connect`.

Historical bars (`data.fetch_from_ibkr`, `whatToShow="ADJUSTED_LAST"`) are a
separate entitlement from streaming quotes and generally work where quotes do.

## 7. Verify

```bash
python -m alphalab.preflight
```

Read-only, safe to rerun, and it cannot place an order. It checks, in the
order these things fail:

1. `.env` exists and names a paper account
2. a gateway is listening on the configured port
3. that gateway actually serves your account id — a typo here otherwise shows
   up as a mysteriously empty portfolio rather than an error
4. NAV and positions come back
5. market data returns a quote

Expected output on a fresh paper account:

```
INFO    credentials  Credentials(account='DU1234567', login credentials unset)
INFO                 (no stored login -- start the gateway by hand)
INFO    gateway      127.0.0.1:4002 serves ['DU1234567']
INFO    NAV          1000000.00
INFO    positions    0 open
INFO    market data  SPY last 512.34
INFO    all checks passed -- dry_run is True in configs/live.yaml
```

Then a full dry run, which computes real orders and prints them without
sending:

```bash
python -m alphalab.run --config configs/live.yaml --dry-run
```

## 8. Optional: unattended login with IBC

The gateway logs itself out daily and needs re-authentication. If you are
scheduling the run with a systemd timer, something has to type the password.
[IBC](https://github.com/IbcAlpha/IBC) does that.

IBC reads a `config.ini` containing `IbLoginId`, `IbPassword`, and
`TradingMode=paper`. That file is a plaintext brokerage password on disk —
`ibc/config.ini` is gitignored here, but treat the whole path as sensitive
and `chmod 600` it.

Also set **Configure → Settings → Lock and Exit → Auto restart** in the
gateway. Auto restart keeps the session alive across the daily bounce without
re-entering credentials; it still expires after about a week, so a fully
unattended setup wants IBC regardless.

Point the timer at a time after the close (16:00 ET) that does not collide
with the gateway's restart window.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `ConnectionRefusedError` | Gateway not running, or the port is 4001/7497 rather than 4002. |
| Connects, then hangs | Client id 17 already in use by another session. Change `ibkr.client_id`. |
| `IBKR_ACCOUNT ... is not a paper account` | A live id in `.env`. This is the guard working. |
| `is not served by this gateway` | Typo in the id, or the gateway is logged into a different session. |
| `no usable price for SPY` | No market data subscription. See section 6. |
| Orders computed but never appear | `dry_run: true`, or Read-Only API still on at the gateway. Both are deliberate. |
