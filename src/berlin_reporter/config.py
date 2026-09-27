"""Settings, read from environment variables, an optional .env file, and the OS keychain.

Lookup order per key: real environment variable → .env file → OS keychain
(macOS Keychain, Windows Credential Manager, Secret Service on Linux; service name
"berlin-reporter"). Store personal data in the keychain with `berlin-reporter-secrets set`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

KEYRING_SERVICE = "berlin-reporter"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Personal data and credentials that can live in the keychain instead of a file.
SECRET_KEYS = (
    "REPORTER_NAME",
    "REPORTER_ADDRESS",
    "REPORTER_EMAIL",
    "REPORTER_PHONE",
    "REPORTER_BIRTHDATE",
    "SMTP_USER",
    "SMTP_PASSWORD",
)

ENV_FILE_LOCATIONS = [
    Path.cwd() / ".env",
    PROJECT_ROOT / ".env",
    Path.home() / ".config" / "berlin-reporter" / ".env",
]


def _load_env_file() -> None:
    """Load KEY=VALUE lines from the first .env file found. Real env vars win."""
    for path in ENV_FILE_LOCATIONS:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)
        return


def keyring_get(key: str) -> str:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, key) or ""
    except Exception:  # no keyring backend available (headless Linux, CI, ...)
        return ""


def _get(key: str, default: str = "") -> str:
    value = os.environ.get(key, "")
    if value == "" and key in SECRET_KEYS:
        value = keyring_get(key)
    return value if value != "" else default


@dataclass(frozen=True)
class Settings:
    reporter_name: str
    reporter_address: str
    reporter_email: str
    reporter_phone: str
    reporter_birthdate: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    dry_run: bool
    geocode: bool
    reports_dir: Path
    upload_dir: Path

    @property
    def inbox(self) -> Path:
        return self.reports_dir / "inbox"

    @property
    def drafts(self) -> Path:
        return self.reports_dir / "drafts"

    @property
    def outbox(self) -> Path:
        return self.reports_dir / "outbox"

    @property
    def history_file(self) -> Path:
        return self.reports_dir / "history.jsonl"

    def missing_reporter_fields(self) -> list[str]:
        required = {
            "REPORTER_NAME": self.reporter_name,
            "REPORTER_ADDRESS": self.reporter_address,
            "REPORTER_EMAIL": self.reporter_email,
        }
        return [k for k, v in required.items() if not v]

    def missing_smtp_fields(self) -> list[str]:
        required = {
            "SMTP_HOST": self.smtp_host,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASSWORD": self.smtp_password,
        }
        return [k for k, v in required.items() if not v]


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def load_settings() -> Settings:
    _load_env_file()
    settings = Settings(
        reporter_name=_get("REPORTER_NAME").strip(),
        reporter_address=_get("REPORTER_ADDRESS").strip(),
        reporter_email=_get("REPORTER_EMAIL").strip(),
        reporter_phone=_get("REPORTER_PHONE").strip(),
        reporter_birthdate=_get("REPORTER_BIRTHDATE").strip(),
        smtp_host=_get("SMTP_HOST").strip(),
        smtp_port=int(_get("SMTP_PORT", "587")),
        smtp_user=_get("SMTP_USER").strip(),
        smtp_password=_get("SMTP_PASSWORD"),
        dry_run=_flag("DRY_RUN", True),
        geocode=_flag("GEOCODE", True),
        reports_dir=Path(_get("REPORTS_DIR", "~/berlin-reports")).expanduser(),
        # Inside the project by default, so the browser MCP (limited to workspace roots) can upload from it.
        upload_dir=Path(_get("UPLOAD_DIR", str(PROJECT_ROOT / ".uploads"))).expanduser(),
    )
    for d in (settings.inbox, settings.drafts, settings.outbox):
        d.mkdir(parents=True, exist_ok=True)
    return settings
