import logging

import pytest

from alphalab.credentials import (
    Credentials,
    CredentialsError,
    load_env_file,
    parse_env_file,
)

IBKR_VARS = ("IBKR_ACCOUNT", "IBKR_USERNAME", "IBKR_PASSWORD")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Credentials read os.environ, so no test may inherit another's values."""
    for var in IBKR_VARS:
        monkeypatch.delenv(var, raising=False)


def write_env(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_parses_comments_blank_lines_quotes_and_export(tmp_path):
    path = write_env(
        tmp_path,
        """
        # a comment
        IBKR_ACCOUNT=DU1234567

        export IBKR_USERNAME=someone
        IBKR_PASSWORD="quoted secret"
        SINGLE='single quoted'
        """.replace("        ", ""),
    )
    assert parse_env_file(path) == {
        "IBKR_ACCOUNT": "DU1234567",
        "IBKR_USERNAME": "someone",
        "IBKR_PASSWORD": "quoted secret",
        "SINGLE": "single quoted",
    }


def test_values_containing_equals_survive(tmp_path):
    path = write_env(tmp_path, "IBKR_PASSWORD=a=b=c\n")
    assert parse_env_file(path)["IBKR_PASSWORD"] == "a=b=c"


def test_hash_inside_a_value_is_not_a_comment(tmp_path):
    """Only whole-line comments. Brokerage passwords contain # regularly."""
    path = write_env(tmp_path, "IBKR_PASSWORD=pa#ss#word\n")
    assert parse_env_file(path)["IBKR_PASSWORD"] == "pa#ss#word"


def test_quotes_preserve_surrounding_whitespace(tmp_path):
    path = write_env(tmp_path, 'IBKR_PASSWORD="  padded  "\n')
    assert parse_env_file(path)["IBKR_PASSWORD"] == "  padded  "


def test_empty_value_reads_as_unset(tmp_path):
    path = write_env(tmp_path, "IBKR_ACCOUNT=DU1234567\nIBKR_USERNAME=\n")
    assert Credentials.load(path).username is None


def test_malformed_line_names_the_line_number(tmp_path):
    path = write_env(tmp_path, "IBKR_ACCOUNT=DU1\nthis is not an assignment\n")
    with pytest.raises(CredentialsError, match=":2:"):
        parse_env_file(path)


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "absent") == {}


def test_real_environment_beats_the_file(tmp_path, monkeypatch):
    """A systemd EnvironmentFile= must win over whatever is checked out."""
    monkeypatch.setenv("IBKR_ACCOUNT", "DU_from_environment")
    path = write_env(tmp_path, "IBKR_ACCOUNT=DU_from_file\n")

    load_env_file(path)
    assert Credentials.load(path).account == "DU_from_environment"

    load_env_file(path, override=True)
    assert Credentials.load(path).account == "DU_from_file"


def test_loads_account_and_optional_login(tmp_path):
    path = write_env(
        tmp_path, "IBKR_ACCOUNT=DU1234567\nIBKR_USERNAME=u\nIBKR_PASSWORD=p\n"
    )
    creds = Credentials.load(path)
    assert creds.account == "DU1234567"
    assert creds.can_automate_login


def test_login_is_optional(tmp_path):
    """Typing the gateway password by hand is a supported setup, not an error."""
    creds = Credentials.load(write_env(tmp_path, "IBKR_ACCOUNT=DU1234567\n"))
    assert (creds.username, creds.password) == (None, None)
    assert not creds.can_automate_login


def test_missing_account_points_at_the_fix(tmp_path):
    with pytest.raises(CredentialsError, match="IBKR_ACCOUNT is not set"):
        Credentials.load(write_env(tmp_path, "# nothing here\n"))


@pytest.mark.parametrize("account", ["U1234567", "F1234567", "1234567"])
def test_live_accounts_are_refused(tmp_path, account):
    """The competition is paper-only. Catch it here, not at the first order."""
    with pytest.raises(CredentialsError, match="not a paper account"):
        Credentials.load(write_env(tmp_path, f"IBKR_ACCOUNT={account}\n"))


def test_advisor_paper_accounts_are_accepted(tmp_path):
    assert Credentials.load(write_env(tmp_path, "IBKR_ACCOUNT=DF1234567\n")).account


def test_repr_does_not_leak_the_password(tmp_path):
    """This object shows up in tracebacks and log lines."""
    path = write_env(
        tmp_path,
        "IBKR_ACCOUNT=DU1234567\nIBKR_USERNAME=alice\nIBKR_PASSWORD=hunter2\n",
    )
    rendered = repr(Credentials.load(path))
    assert "hunter2" not in rendered
    assert "alice" not in rendered
    assert "DU1234567" in rendered


def test_world_readable_env_file_warns_but_still_loads(tmp_path, caplog):
    path = write_env(tmp_path, "IBKR_ACCOUNT=DU1234567\n")
    path.chmod(0o644)
    with caplog.at_level(logging.WARNING, logger="alphalab"):
        creds = Credentials.load(path)
    assert creds.account == "DU1234567"
    assert "chmod 600" in caplog.text


def test_owner_only_env_file_is_quiet(tmp_path, caplog):
    path = write_env(tmp_path, "IBKR_ACCOUNT=DU1234567\n")
    path.chmod(0o600)
    with caplog.at_level(logging.WARNING, logger="alphalab"):
        Credentials.load(path)
    assert caplog.text == ""
