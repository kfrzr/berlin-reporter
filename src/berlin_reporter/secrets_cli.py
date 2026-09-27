"""Store personal data and SMTP credentials in the OS keychain instead of a file.

    berlin-reporter-secrets set           # prompts for every value
    berlin-reporter-secrets set SMTP_PASSWORD
    berlin-reporter-secrets show          # which keys are stored (values masked)
    berlin-reporter-secrets delete REPORTER_PHONE
"""

from __future__ import annotations

import getpass
import sys

import keyring
from keyring.errors import NoKeyringError, PasswordDeleteError

from .config import KEYRING_SERVICE, SECRET_KEYS

PROMPTS = {
    "REPORTER_NAME": "Full name (Vorname Nachname)",
    "REPORTER_ADDRESS": "Postal address (Straße Nr, PLZ Ort)",
    "REPORTER_EMAIL": "Email",
    "REPORTER_PHONE": "Phone (optional)",
    "REPORTER_BIRTHDATE": "Birth date DD.MM.YYYY (optional; some police forms require it)",
    "SMTP_USER": "SMTP username",
    "SMTP_PASSWORD": "SMTP password / app password",
}


def _mask(value: str) -> str:
    return "(not set)" if not value else value[:2] + "…" + f" ({len(value)} chars)"


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except NoKeyringError:
        print("No OS keychain is available on this system. Put the values in .env instead "
              "(it is gitignored), or install a keyring backend (see https://pypi.org/project/keyring).")
        return 1


def _run(argv: list[str] | None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] not in {"set", "show", "delete"}:
        print(__doc__)
        return 2
    cmd, keys = args[0], [k.upper() for k in args[1:]] or list(SECRET_KEYS)
    unknown = [k for k in keys if k not in SECRET_KEYS]
    if unknown:
        print(f"Unknown key(s): {', '.join(unknown)}. Valid: {', '.join(SECRET_KEYS)}")
        return 2

    if cmd == "show":
        for k in keys:
            print(f"{k:20} {_mask(keyring.get_password(KEYRING_SERVICE, k) or '')}")
    elif cmd == "delete":
        for k in keys:
            try:
                keyring.delete_password(KEYRING_SERVICE, k)
                print(f"deleted {k}")
            except PasswordDeleteError:
                pass
    else:
        print(f"Saving to the {keyring.get_keyring().name} under service '{KEYRING_SERVICE}'. Enter to skip.")
        for k in keys:
            read = getpass.getpass if k == "SMTP_PASSWORD" else input
            value = read(f"{PROMPTS[k]}: ").strip()
            if value:
                keyring.set_password(KEYRING_SERVICE, k, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
