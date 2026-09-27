"""Build, store and render violation reports."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .config import Settings
from .violations import RENTAL_TYPES, ROUTES, VEHICLE_TYPES_DE, VIOLATIONS, route_for

# German plates: district code (1-3 letters incl. umlauts), 1-2 letters, 1-4 digits, optional E/H suffix.
# Insurance plates on e-scooters/mopeds are 3 digits + 3 letters (e.g. 123 ABC).
_PLATE_RE = re.compile(r"^[A-ZÄÖÜ]{1,3}[- ]?[A-Z]{1,2} ?\d{1,4}[EH]?$")
_INSURANCE_PLATE_RE = re.compile(r"^\d{2,3} ?[A-Z]{3}$")


class ReportError(ValueError):
    pass


def normalize_plate(plate: str) -> str:
    return re.sub(r"\s+", " ", plate.strip().upper().replace("–", "-"))


def plate_looks_valid(plate: str) -> bool:
    p = plate.replace("-", " ").replace("  ", " ")
    compact = p.replace(" ", "")
    return bool(_PLATE_RE.match(p) or _PLATE_RE.match(compact) or _INSURANCE_PLATE_RE.match(p))


@dataclass
class Draft:
    id: str
    created_at: str
    route: str
    violation: str
    vehicle_type: str
    plate: str
    photos: list[str]
    time_start: str
    time_end: str | None
    address: str
    district: str | None
    latitude: float | None
    longitude: float | None
    vehicle_make: str | None
    vehicle_color: str | None
    details: str | None
    obstruction: str | None
    operator: str | None
    warnings: list[str] = field(default_factory=list)
    status: str = "draft"  # draft | dry_run | form_pending | sent

    def save(self, settings: Settings) -> Path:
        path = settings.drafts / f"{self.id}.json"
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, settings: Settings, draft_id: str) -> "Draft":
        path = settings.drafts / f"{draft_id}.json"
        if not path.is_file():
            raise ReportError(f"No draft with id {draft_id!r}")
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def _parse_time(value: str, name: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReportError(f"{name} must be ISO 8601, e.g. 2026-09-27T14:05 (got {value!r})") from exc


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y, %H:%M Uhr")


def _previous_reports(settings: Settings, plate: str, day: str) -> list[dict]:
    if not settings.history_file.is_file():
        return []
    hits = []
    for line in settings.history_file.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("plate") == plate and str(entry.get("time_start", "")).startswith(day):
            hits.append(entry)
    return hits


def create_draft(
    settings: Settings,
    *,
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
) -> Draft:
    if violation not in VIOLATIONS:
        raise ReportError(f"Unknown violation {violation!r}. Valid: {', '.join(VIOLATIONS)}")
    if vehicle_type not in VEHICLE_TYPES_DE:
        raise ReportError(f"Unknown vehicle_type {vehicle_type!r}. Valid: {', '.join(VEHICLE_TYPES_DE)}")
    if not photos:
        raise ReportError("At least one photo is required as evidence.")
    resolved = []
    for p in photos:
        path = Path(p).expanduser()
        if not path.is_file():
            raise ReportError(f"Photo not found: {p}")
        resolved.append(str(path.resolve()))
    if not address.strip():
        raise ReportError("address is required (street and house number or nearest intersection).")
    if violation.startswith("sonstiges") and not (details and details.strip()):
        raise ReportError("For 'sonstiges_*' violations, describe what happened in `details`.")

    start = _parse_time(time_start, "time_start")
    end = _parse_time(time_end, "time_end") if time_end else None
    if end and end < start:
        raise ReportError("time_end is before time_start.")
    if start > datetime.now():
        raise ReportError("time_start is in the future.")

    plate_n = normalize_plate(plate)
    warnings: list[str] = []
    if not plate_n and vehicle_type not in RENTAL_TYPES:
        raise ReportError("A license plate is required; the authority cannot act without one.")
    if plate_n and not plate_looks_valid(plate_n):
        warnings.append(f"Plate {plate_n!r} does not look like a German plate. Double-check it against the photo.")
    if VIOLATIONS[violation].kind == "parking" and not end:
        warnings.append(
            "Only one observation time given. For parking violations, a second photo a few minutes "
            "later (time_end) shows the vehicle was parked, not just briefly stopping."
        )
    if (datetime.now() - start).days > 14:
        warnings.append("The violation is more than 2 weeks old. Report promptly; old reports are often dropped.")
    earlier = _previous_reports(settings, plate_n, start.date().isoformat())
    if earlier:
        warnings.append(f"You already reported {plate_n} on this day ({len(earlier)}x). Is this a duplicate?")

    route = route_for(violation, vehicle_type)
    draft = Draft(
        id=f"{start:%Y%m%d-%H%M}-{re.sub(r'[^A-Z0-9]', '', plate_n) or 'NOPLATE'}-{uuid.uuid4().hex[:4]}",
        created_at=datetime.now().isoformat(timespec="seconds"),
        route=route.key,
        violation=violation,
        vehicle_type=vehicle_type,
        plate=plate_n,
        photos=resolved,
        time_start=start.isoformat(timespec="minutes"),
        time_end=end.isoformat(timespec="minutes") if end else None,
        address=address.strip(),
        district=district,
        latitude=latitude,
        longitude=longitude,
        vehicle_make=vehicle_make,
        vehicle_color=vehicle_color,
        details=details,
        obstruction=obstruction,
        operator=operator,
        warnings=warnings,
    )
    draft.save(settings)
    return draft


def subject(draft: Draft) -> str:
    v = VIOLATIONS[draft.violation]
    kind = "Halt-/Parkverstoß" if v.kind == "parking" else "Verkehrsordnungswidrigkeit"
    start = datetime.fromisoformat(draft.time_start)
    plate = draft.plate or "ohne Kennzeichen"
    return f"Anzeige {kind} – {plate} – {start:%d.%m.%Y %H:%M} – {draft.address}"


def body(draft: Draft, settings: Settings) -> str:
    v = VIOLATIONS[draft.violation]
    start = datetime.fromisoformat(draft.time_start)
    lines = [
        "Sehr geehrte Damen und Herren,",
        "",
        "hiermit zeige ich die folgende Verkehrsordnungswidrigkeit an und bitte um deren Verfolgung.",
        "",
        f"Kennzeichen: {draft.plate or '–'}",
    ]
    vehicle = VEHICLE_TYPES_DE[draft.vehicle_type]
    extra = ", ".join(x for x in (draft.vehicle_make, draft.vehicle_color) if x)
    lines.append(f"Fahrzeug: {vehicle}" + (f" ({extra})" if extra else ""))
    if draft.operator:
        lines.append(f"Anbieter: {draft.operator}")

    if draft.time_end:
        end = datetime.fromisoformat(draft.time_end)
        if end.date() == start.date():
            lines.append(f"Tatzeit: {start:%d.%m.%Y}, {start:%H:%M} bis {end:%H:%M} Uhr")
        else:
            lines.append(f"Tatzeit: {_fmt_dt(start)} bis {_fmt_dt(end)}")
    else:
        lines.append(f"Tatzeit: {_fmt_dt(start)}")

    place = draft.address + (f" (Bezirk {draft.district})" if draft.district else "")
    lines.append(f"Tatort: {place}")
    if draft.latitude is not None and draft.longitude is not None:
        lines.append(f"Koordinaten: {draft.latitude:.6f}, {draft.longitude:.6f}")

    lines.append(f"Verstoß: {v.text_de}")
    if draft.details:
        lines.append(f"Beschreibung: {draft.details}")
    if draft.obstruction:
        lines.append(f"Behinderung/Gefährdung: {draft.obstruction}")
    n = len(draft.photos)
    lines += [
        f"Beweismittel: {n} Foto{'s' if n != 1 else ''} im Anhang (von mir selbst aufgenommen)",
        "",
        "Ich habe den Verstoß selbst beobachtet und bin bereit, als Zeuge bzw. Zeugin auszusagen.",
        "",
        "Angaben zur anzeigenden Person:",
        f"Name: {settings.reporter_name}",
        f"Anschrift: {settings.reporter_address}",
        f"E-Mail: {settings.reporter_email}",
    ]
    if settings.reporter_phone:
        lines.append(f"Telefon: {settings.reporter_phone}")
    lines += ["", "Mit freundlichen Grüßen", settings.reporter_name]
    return "\n".join(lines)


def render(draft: Draft, settings: Settings) -> dict:
    route = ROUTES[draft.route]
    return {
        "draft_id": draft.id,
        "send_to": {
            "authority": route.authority,
            "channel": route.channel,
            "email": route.to,
            "urls": list(route.urls),
            "notes": route.notes,
        },
        "subject": subject(draft),
        "body": body(draft, settings),
        "photos": draft.photos,
        "warnings": draft.warnings,
        "status": draft.status,
    }


def append_history(settings: Settings, draft: Draft, result: str, **extra) -> None:
    entry = {
        "draft_id": draft.id,
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "result": result,
        "route": draft.route,
        "plate": draft.plate,
        "violation": draft.violation,
        "time_start": draft.time_start,
        "address": draft.address,
        **{k: v for k, v in extra.items() if v},
    }
    with settings.history_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_history(settings: Settings, limit: int = 20) -> list[dict]:
    if not settings.history_file.is_file():
        return []
    lines = settings.history_file.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out
