"""MCP server: report illegally parked or driven vehicles in Berlin from a photo."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from . import photos as photo_mod
from .config import load_settings
from .mailer import build_message, deliver
from .report import Draft, ReportError, append_history, create_draft, read_history, render
from .violations import ROUTES, catalog

mcp = FastMCP(
    "berlin-reporter",
    instructions=(
        "Drafts and submits reports of traffic and parking violations in Berlin. Workflow: "
        "inspect_photo → draft_report → show the draft to the user → submit_report only after "
        "the user explicitly confirms. Never guess a license plate: if it is not clearly legible "
        "in the photo, ask the user."
    ),
)


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def setup_status() -> str:
    """Check whether reporter identity and SMTP are configured, and where files live."""
    s = load_settings()
    return _json({
        "reporter_missing": s.missing_reporter_fields(),
        "smtp_missing": s.missing_smtp_fields(),
        "dry_run": s.dry_run,
        "reports_dir": str(s.reports_dir),
        "inbox": str(s.inbox),
        "hint": "Fill in .env (see .env.example). DRY_RUN=1 saves .eml files to the outbox instead of sending.",
    })


@mcp.tool()
def list_inbox_photos(limit: int = 10) -> str:
    """List the newest photos in the inbox folder (~/berlin-reports/inbox by default)."""
    s = load_settings()
    return _json([
        {"path": str(p), "modified": p.stat().st_mtime} for p in photo_mod.list_photos(s.inbox, limit)
    ])


@mcp.tool()
def inspect_photo(path: str) -> list:
    """Show a photo and read its capture time and GPS location (reverse-geocoded to a Berlin address and district).

    Look at the returned image to read the license plate, identify the vehicle type, make and
    color, and judge what the violation is. Phones often strip GPS when a photo is shared; if
    location or time is missing, ask the user.
    """
    s = load_settings()
    p = Path(path).expanduser()
    if not p.is_file():
        raise ValueError(f"Photo not found: {path}")
    info = photo_mod.read_metadata(p)
    if s.geocode:
        info = photo_mod.reverse_geocode(info, s.reporter_email)
    return [Image(data=photo_mod.preview_jpeg(p), format="jpeg"), _json(info.to_dict())]


@mcp.tool()
def list_violation_types() -> str:
    """List violation keys, vehicle types, and which authority each combination goes to."""
    return _json(catalog())


@mcp.tool()
def draft_report(
    photos: list[str],
    plate: str,
    vehicle_type: str,
    violation: str,
    time_start: str,
    address: str,
    time_end: str | None = None,
    district: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    vehicle_make: str | None = None,
    vehicle_color: str | None = None,
    details: str | None = None,
    obstruction: str | None = None,
    operator: str | None = None,
) -> str:
    """Create a report draft and pick the responsible authority. Nothing is sent.

    Args:
        photos: Paths to the evidence photos (plate should be legible in at least one).
        plate: License plate exactly as on the vehicle, e.g. "B-AB 1234". Insurance plate for e-scooters.
        vehicle_type: car | van | truck | motorcycle | moped | e_scooter | rental_e_scooter | rental_bike
        violation: Key from list_violation_types, e.g. "radweg", "gehweg", "zweite_reihe", "rotlicht".
        time_start: When observed, ISO 8601 local Berlin time, e.g. "2026-09-27T14:05".
        address: Street + house number, or the nearest intersection.
        time_end: Later observation time (parking: a second photo some minutes later strengthens the case).
        district: Berlin Bezirk, e.g. "Friedrichshain-Kreuzberg".
        latitude, longitude: From photo GPS if available.
        vehicle_make, vehicle_color: e.g. "VW Golf", "schwarz". Written into the report in German.
        details: Extra facts in German (what exactly happened). Required for "sonstiges_*" violations.
        obstruction: In German, who was blocked or endangered, e.g. "Radfahrende mussten auf die Fahrbahn ausweichen".
        operator: For rental vehicles, e.g. "Tier", "Lime", "Bolt", "Voi".
    """
    s = load_settings()
    try:
        draft = create_draft(
            s,
            photos=photos,
            plate=plate,
            vehicle_type=vehicle_type,
            violation=violation,
            time_start=time_start,
            address=address,
            time_end=time_end,
            district=district,
            latitude=latitude,
            longitude=longitude,
            vehicle_make=vehicle_make,
            vehicle_color=vehicle_color,
            details=details,
            obstruction=obstruction,
            operator=operator,
        )
    except ReportError as exc:
        raise ValueError(str(exc)) from exc
    result = render(draft, s)
    missing = s.missing_reporter_fields()
    if missing:
        result["warnings"].append(f"Reporter identity not configured ({', '.join(missing)}); cannot submit yet.")
    return _json(result)


@mcp.tool()
def submit_report(draft_id: str, user_confirmed: bool) -> str:
    """Submit a draft to the authority. Only call after showing the draft and getting an explicit yes.

    Email routes (parking violations → Bußgeldstelle) are sent by SMTP with the photos attached and
    the user in CC. Web-form routes (moving violations → Internetwache; rental scooters → operator)
    cannot be sent automatically: this returns the text and link for the user to submit, and logs it.
    """
    if not user_confirmed:
        raise ValueError("The user has not confirmed. Show the draft and ask before submitting.")
    s = load_settings()
    try:
        draft = Draft.load(s, draft_id)
    except ReportError as exc:
        raise ValueError(str(exc)) from exc
    if draft.status in ("sent", "handed_off"):
        raise ValueError(f"Draft {draft_id} was already submitted ({draft.status}).")
    missing = s.missing_reporter_fields()
    if missing:
        raise ValueError(f"Configure {', '.join(missing)} in .env first; anonymous reports are not processed.")

    route = ROUTES[draft.route]
    if route.channel == "email":
        if not s.dry_run and s.missing_smtp_fields():
            raise ValueError(f"Configure {', '.join(s.missing_smtp_fields())} in .env to send email.")
        msg = build_message(draft, s, route.to)
        outcome = deliver(msg, s, draft.id)
        draft.status = "dry_run" if s.dry_run else "sent"
        draft.save(s)
        append_history(s, draft, draft.status)
        return _json({"status": draft.status, "detail": outcome, "authority": route.authority})

    draft.status = "handed_off"
    draft.save(s)
    append_history(s, draft, "handed_off")
    rendered = render(draft, s)
    return _json({
        "status": "handed_off",
        "detail": "This authority only takes reports through a web form. Give the user the link, "
                  "the text to paste and the photo paths to upload.",
        "authority": route.authority,
        "urls": list(route.urls),
        "notes": route.notes,
        "subject": rendered["subject"],
        "text": rendered["body"],
        "photos": draft.photos,
    })


@mcp.tool()
def report_history(limit: int = 20) -> str:
    """List recently submitted reports (newest first)."""
    return _json(read_history(load_settings(), limit))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
