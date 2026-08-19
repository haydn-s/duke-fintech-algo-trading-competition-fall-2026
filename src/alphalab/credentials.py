"""IBKR credentials, loaded from an untracked .env file.

Worth being precise about what IBKR actually authenticates, because it is not
what the name "credentials" suggests. The Python API does not log in. It opens
a socket to an IB Gateway (or TWS) process that is *already* authenticated, so
``ib_async`` never sees a username or a password -- only host, port, and a
client id. Those three are not secret and live in ``configs/live.yaml``.

That leaves two things this module is responsible for:

``IBKR_ACCOUNT``
    The paper account id, ``DU`` followed by digits. Required. IBKR reports
    positions and NAV per account, and one login can carry several, so
    ``IBKRBroker`` passes it explicitly rather than trusting whichever account
    the gateway happens to consider the default.

``IBKR_USERNAME`` / ``IBKR_PASSWORD``
    Optional, and only meaningful if you automate the gateway login with IBC.
    If you type the login into the gateway window yourself each morning,
    leave both unset -- storing a brokerage password you never read back is a
    liability with no upside.

Environment variables take precedence over the file, so a systemd unit can
supply them via ``EnvironmentFile=`` and nothing has to change here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

LOG = logging.getLogger("alphalab")

DEFAULT_ENV_PATH = Path(".env")

# IBKR paper accounts: DU for individuals, DF for advisor/institution paper.
# Live accounts are U/F and are rejected -- see Credentials.load.
PAPER_PREFIXES = ("DU", "DF")


class CredentialsError(RuntimeError):
    """Raised when credentials are missing, malformed, or not a paper account."""


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse a ``KEY=value`` file into a dict. Does not touch ``os.environ``.

    Deliberately a dozen lines of stdlib rather than a dependency: the format
    is ``KEY=value``, and a live-trading run failing because a dotenv release
    changed its quote handling is not a trade worth making.
    """
    text = Path(path).read_text()
    values: dict[str, str] = {}

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            raise CredentialsError(f"{path}:{lineno}: expected KEY=value, got {raw!r}")

        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value

    return values


def load_env_file(
    path: str | Path = DEFAULT_ENV_PATH, *, override: bool = False
) -> dict[str, str]:
    """Merge a .env file into ``os.environ``. A missing file is not an error.

    Existing environment variables win unless ``override`` is set, so a
    systemd ``EnvironmentFile=`` or a shell export beats the checked-out file.
    """
    path = Path(path)
    if not path.exists():
        return {}

    _warn_if_world_readable(path)
    values = parse_env_file(path)
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return values


def _warn_if_world_readable(path: Path) -> None:
    """Warn if anyone but the owner can read the file. Warn, not fail.

    A refusal to run would be the wrong call: this is advisory on shared
    machines and meaningless on some filesystems, and halting the daily run
    over a permission bit would cost a trading day to fix a warning.
    """
    try:
        mode = path.stat().st_mode
    except OSError:  # pragma: no cover - platform dependent
        return
    if mode & 0o077:
        LOG.warning(
            "%s is readable beyond its owner (mode %o). Run: chmod 600 %s",
            path,
            mode & 0o777,
            path,
        )


@dataclass(frozen=True)
class Credentials:
    """What the daily run needs beyond the non-secret gateway address."""

    account: str
    username: str | None = None
    password: str | None = None

    @property
    def can_automate_login(self) -> bool:
        """True when IBC has enough to open the gateway session unattended."""
        return bool(self.username and self.password)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_ENV_PATH) -> Credentials:
        """Read credentials from the environment, falling back to ``path``."""
        load_env_file(path)

        account = os.environ.get("IBKR_ACCOUNT", "").strip()
        if not account:
            raise CredentialsError(
                "IBKR_ACCOUNT is not set. Copy .env.example to .env and fill in "
                "your paper account id (it looks like DU1234567 and is shown in "
                "the top-right of Client Portal). See docs/IBKR_SETUP.md."
            )

        if not account.startswith(PAPER_PREFIXES):
            raise CredentialsError(
                f"IBKR_ACCOUNT={account!r} is not a paper account. Paper ids start "
                f"with {' or '.join(PAPER_PREFIXES)}; live ids do not. This is a "
                "paper-trading competition, so the live account is refused here "
                "rather than discovered at the first order."
            )

        return cls(
            account=account,
            username=os.environ.get("IBKR_USERNAME") or None,
            password=os.environ.get("IBKR_PASSWORD") or None,
        )

    def __repr__(self) -> str:
        """Redacted on purpose -- this object ends up in tracebacks and logs."""
        secrets = "set" if self.can_automate_login else "unset"
        return f"Credentials(account={self.account!r}, login credentials {secrets})"
