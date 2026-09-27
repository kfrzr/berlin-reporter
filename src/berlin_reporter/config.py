"""Settings, read from environment variables and an optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE_LOCATIONS = [
    Path.cwd() / ".env",
    Path(__file__).resolve().parents[2] / ".env",
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


@dataclass(frozen=True)
class Settings:
    reporter_name: str
    reporter_address: str
    reporter_email: str
    reporter_phone: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    dry_run: bool
    geocode: bool
    reports_dir: Path

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
    env = os.environ.get
    settings = Settings(
        reporter_name=env("REPORTER_NAME", "").strip(),
        reporter_address=env("REPORTER_ADDRESS", "").strip(),
        reporter_email=env("REPORTER_EMAIL", "").strip(),
        reporter_phone=env("REPORTER_PHONE", "").strip(),
        smtp_host=env("SMTP_HOST", "").strip(),
        smtp_port=int(env("SMTP_PORT", "587") or 587),
        smtp_user=env("SMTP_USER", "").strip(),
        smtp_password=env("SMTP_PASSWORD", ""),
        dry_run=_flag("DRY_RUN", True),
        geocode=_flag("GEOCODE", True),
        reports_dir=Path(env("REPORTS_DIR", "~/berlin-reports")).expanduser(),
    )
    for d in (settings.inbox, settings.drafts, settings.outbox):
        d.mkdir(parents=True, exist_ok=True)
    return settings
