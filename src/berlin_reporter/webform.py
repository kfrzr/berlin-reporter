"""Structured data for filling an authority's web form in a browser (via the Playwright MCP)."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from .config import Settings
from .photos import attachment_jpeg
from .report import Draft
from .violations import ROUTES, VEHICLE_TYPES_DE, VIOLATIONS

_ADDRESS_RE = re.compile(r"^\s*(?P<street>.+?)\s+(?P<number>\d+\s*[a-zA-Z]?(?:\s*[-/]\s*\d+\s*[a-zA-Z]?)?)?\s*,\s*(?P<postcode>\d{5})\s+(?P<city>.+?)\s*$")
_STREET_ONLY_RE = re.compile(r"^\s*(?P<street>.*?[^\d\s])\s+(?P<number>\d+\s*[a-zA-Z]?)\s*$")


def split_address(address: str) -> dict:
    """'Oranienstraße 10a, 10999 Berlin' → street/house_number/postcode/city. Unparsed parts stay in `full`."""
    out = {"full": address, "street": None, "house_number": None, "postcode": None, "city": None}
    m = _ADDRESS_RE.match(address)
    if m:
        street, number = m["street"], m["number"]
        if not number:
            sm = _STREET_ONLY_RE.match(street)
            if sm:
                street, number = sm["street"], sm["number"]
        out.update(street=street, house_number=number, postcode=m["postcode"], city=m["city"])
        return out
    first = address.split(",")[0]
    sm = _STREET_ONLY_RE.match(first)
    if sm:
        out.update(street=sm["street"], house_number=sm["number"])
    else:
        out["street"] = first.strip() or None
    pm = re.search(r"\b(\d{5})\s+([^,]+)", address)
    if pm:
        out.update(postcode=pm[1], city=pm[2].strip())
    return out


def split_name(name: str) -> dict:
    parts = name.split()
    if len(parts) < 2:
        return {"full": name, "first_name": None, "last_name": name or None}
    return {"full": name, "first_name": " ".join(parts[:-1]), "last_name": parts[-1]}


def sachverhalt(draft: Draft) -> str:
    """Short factual description in German for a form's free-text field."""
    v = VIOLATIONS[draft.violation]
    start = datetime.fromisoformat(draft.time_start)
    when = f"Am {start:%d.%m.%Y} um {start:%H:%M} Uhr"
    if draft.time_end:
        end = datetime.fromisoformat(draft.time_end)
        when = (f"Am {start:%d.%m.%Y} von {start:%H:%M} bis {end:%H:%M} Uhr" if end.date() == start.date()
                else f"Vom {start:%d.%m.%Y %H:%M} bis {end:%d.%m.%Y %H:%M} Uhr")
    vehicle = VEHICLE_TYPES_DE[draft.vehicle_type]
    extra = ", ".join(x for x in (draft.vehicle_make, draft.vehicle_color) if x)
    if extra:
        vehicle += f" ({extra})"
    who = f"das Fahrzeug {vehicle} mit dem Kennzeichen {draft.plate}" if draft.plate else f"ein {vehicle}"
    if draft.operator:
        who += f" des Anbieters {draft.operator}"
    place = draft.address + (f" (Bezirk {draft.district})" if draft.district else "")
    text = [f"{when} beobachtete ich in {place} folgenden Verstoß durch {who}: {v.text_de}."]
    if draft.details:
        text.append(draft.details.rstrip(".") + ".")
    if draft.obstruction:
        text.append(f"Behinderung/Gefährdung: {draft.obstruction.rstrip('.')}.")
    n = len(draft.photos)
    text.append(f"{n} von mir aufgenommene{'s Foto liegt' if n == 1 else ' Fotos liegen'} bei. "
                "Ich habe den Verstoß selbst beobachtet und bin bereit, als Zeuge bzw. Zeugin auszusagen.")
    return " ".join(text)


def stage_uploads(draft: Draft, settings: Settings) -> list[str]:
    """Write upload-ready JPEGs (HEIC converted, resized, upright) where the browser may read them."""
    folder = settings.upload_dir / draft.id
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    paths = []
    for i, photo in enumerate(draft.photos, start=1):
        target = folder / f"foto{i}.jpg"
        target.write_bytes(attachment_jpeg(Path(photo), max_edge=2048, quality=82))
        paths.append(str(target))
    return paths


def form_payload(draft: Draft, settings: Settings) -> dict:
    route = ROUTES[draft.route]
    start = datetime.fromisoformat(draft.time_start)
    end = datetime.fromisoformat(draft.time_end) if draft.time_end else None
    v = VIOLATIONS[draft.violation]
    return {
        "draft_id": draft.id,
        "authority": route.authority,
        "start_url": route.urls[0],
        "alternative_urls": list(route.urls[1:]),
        "form_hints": route.form_hints,
        "reporter": {
            **split_name(settings.reporter_name),
            **{f"address_{k}": v for k, v in split_address(settings.reporter_address).items()},
            "email": settings.reporter_email,
            "phone": settings.reporter_phone or None,
            "birthdate": settings.reporter_birthdate or None,
        },
        "incident": {
            "date": f"{start:%d.%m.%Y}",
            "date_iso": start.date().isoformat(),
            "time_from": f"{start:%H:%M}",
            "time_to": f"{end:%H:%M}" if end else None,
            **{f"location_{k}": v for k, v in split_address(draft.address).items()},
            "district": draft.district,
            "latitude": draft.latitude,
            "longitude": draft.longitude,
            "violation_de": v.text_de,
            "kind": "Halt-/Parkverstoß" if v.kind == "parking" else "Verkehrsordnungswidrigkeit im fließenden Verkehr",
        },
        "vehicle": {
            "plate": draft.plate or None,
            "type_de": VEHICLE_TYPES_DE[draft.vehicle_type],
            "make": draft.vehicle_make,
            "color": draft.vehicle_color,
            "operator": draft.operator,
        },
        "description_de": sachverhalt(draft),
        "upload_files": stage_uploads(draft, settings),
    }
