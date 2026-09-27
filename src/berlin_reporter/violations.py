"""Catalog of reportable violations, and which Berlin authority handles each one."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    key: str
    authority: str
    channel: str  # "email" (sent by this server) or "web_form" (the user submits the prepared text)
    to: str | None = None
    urls: tuple[str, ...] = ()
    notes: str = ""


BOWI = Route(
    key="bowi_email",
    authority="Polizei Berlin, Zentrale Bußgeldstelle (Halt- und Parkverstöße)",
    channel="email",
    to="anzeige@bowi.berlin.de",
    notes=(
        "Berlin's central fine office accepts private reports of stopping and parking "
        "violations by email. You get no feedback on the outcome, and you may be "
        "called as a witness."
    ),
)

INTERNETWACHE = Route(
    key="internetwache",
    authority="Polizei Berlin, Internetwache",
    channel="web_form",
    urls=("https://www.internetwache-polizei-berlin.de/",),
    notes=(
        "Violations in moving traffic (red light, phone at the wheel, riding on the "
        "sidewalk, dangerous overtaking, ...) are not handled by the fine office's email "
        "inbox. Submit them through the police online station: choose "
        "'Anzeige erstatten' → traffic offence, paste the prepared text and upload the "
        "photos. Accidents, injuries or acute danger: call 110."
    ),
)

SHARING_OPERATOR = Route(
    key="sharing_operator",
    authority="Sharing operator (Tier/Dott, Lime, Bolt, Voi, ...) via their misparking form",
    channel="web_form",
    urls=(
        "https://www.jelbi.de/en/parking-violations-of-two-wheelers/",
        "https://www.scooter-melder.de/",
    ),
    notes=(
        "Rental e-scooters and bikes are usually removed fastest by the operator. The "
        "Jelbi (BVG) form and scooter-melder.de forward the report to the right operator. "
        "If the vehicle blocks a sidewalk or crossing for people with wheelchairs, "
        "strollers or visual impairments, it can additionally be reported to the fine "
        "office as a parking violation (use the plate on the insurance sticker)."
    ),
)

ROUTES = {r.key: r for r in (BOWI, INTERNETWACHE, SHARING_OPERATOR)}


@dataclass(frozen=True)
class Violation:
    key: str
    kind: str  # "parking" or "moving"
    label_en: str
    text_de: str  # used verbatim in the report


VIOLATIONS: dict[str, Violation] = {
    v.key: v
    for v in [
        # --- Halt- und Parkverstöße ---
        Violation("gehweg", "parking", "Parked on the sidewalk",
                  "Parken auf dem Gehweg"),
        Violation("radweg", "parking", "Stopped/parked on a bike lane or cycle track",
                  "Halten bzw. Parken auf einem Radweg / Radfahrstreifen"),
        Violation("schutzstreifen", "parking", "Parked on an advisory bike lane (dashed line)",
                  "Parken auf einem Schutzstreifen für den Radverkehr"),
        Violation("zweite_reihe", "parking", "Double parked",
                  "Parken in zweiter Reihe"),
        Violation("kreuzung", "parking", "Parked within 5 m of an intersection/junction",
                  "Parken im Kreuzungs- bzw. Einmündungsbereich (weniger als 5 m vor den Schnittpunkten der Fahrbahnkanten)"),
        Violation("fussgaengerueberweg", "parking", "Parked on or within 5 m before a zebra crossing",
                  "Parken auf bzw. weniger als 5 m vor einem Fußgängerüberweg"),
        Violation("bordsteinabsenkung", "parking", "Parked at a lowered curb (curb ramp)",
                  "Parken vor einer Bordsteinabsenkung"),
        Violation("haltestelle", "parking", "Parked at a bus/tram stop (within 15 m of the stop sign)",
                  "Parken im Bereich einer Haltestelle (weniger als 15 m vor oder hinter dem Haltestellenschild)"),
        Violation("halteverbot", "parking", "Stopped in an absolute no-stopping zone (sign 283)",
                  "Halten im absoluten Haltverbot (Zeichen 283)"),
        Violation("eingeschraenktes_halteverbot", "parking", "Parked in a restricted no-stopping zone (sign 286)",
                  "Parken im eingeschränkten Haltverbot (Zeichen 286)"),
        Violation("feuerwehrzufahrt", "parking", "Parked in a fire lane",
                  "Parken in einer Feuerwehrzufahrt"),
        Violation("grundstuecksausfahrt", "parking", "Blocking a driveway/garage exit",
                  "Parken vor bzw. gegenüber einer Grundstücksein- oder -ausfahrt"),
        Violation("behindertenparkplatz", "parking", "Parked in a disabled bay without permit",
                  "Parken auf einem Schwerbehindertenparkplatz ohne gültigen Parkausweis"),
        Violation("ladeplatz", "parking", "Parked at an EV charger without charging / not an EV",
                  "Parken auf einem Parkplatz für elektrisch betriebene Fahrzeuge ohne Ladevorgang bzw. ohne Berechtigung"),
        Violation("gruenflaeche", "parking", "Parked on a green space/median",
                  "Parken auf einer Grünfläche / einem Grünstreifen"),
        Violation("fussgaengerzone", "parking", "Parked in a pedestrian zone",
                  "Parken in einer Fußgängerzone"),
        Violation("sonstiges_parken", "parking", "Other stopping/parking violation (describe it)",
                  "Halt- bzw. Parkverstoß"),
        # --- Verstöße im fließenden Verkehr ---
        Violation("rotlicht", "moving", "Ran a red light",
                  "Missachtung des Rotlichts einer Lichtzeichenanlage"),
        Violation("handy", "moving", "Using a phone while driving/riding",
                  "Benutzung eines Mobiltelefons während der Fahrt"),
        Violation("gehweg_fahren", "moving", "Driving/riding on the sidewalk",
                  "Befahren des Gehwegs"),
        Violation("radweg_fahren", "moving", "Driving a motor vehicle on a bike lane",
                  "Befahren eines Radwegs / Radfahrstreifens mit einem Kraftfahrzeug"),
        Violation("falsche_richtung", "moving", "Wrong way down a one-way street",
                  "Befahren einer Einbahnstraße entgegen der vorgeschriebenen Fahrtrichtung"),
        Violation("ueberholabstand", "moving", "Overtook a cyclist with less than 1.5 m",
                  "Überholen eines Radfahrenden mit zu geringem Seitenabstand (innerorts mindestens 1,5 m)"),
        Violation("escooter_zu_zweit", "moving", "Two people riding one e-scooter",
                  "Fahren eines E-Scooters mit mehr als einer Person"),
        Violation("sonstiges_fahren", "moving", "Other moving violation (describe it)",
                  "Verkehrsordnungswidrigkeit im fließenden Verkehr"),
    ]
}

VEHICLE_TYPES_DE = {
    "car": "Pkw",
    "van": "Transporter",
    "truck": "Lkw",
    "motorcycle": "Motorrad",
    "moped": "Moped / Motorroller",
    "e_scooter": "E-Scooter (Privatfahrzeug)",
    "rental_e_scooter": "Leih-E-Scooter",
    "rental_bike": "Leih-(E-)Fahrrad",
}

RENTAL_TYPES = {"rental_e_scooter", "rental_bike"}


def route_for(violation_key: str, vehicle_type: str) -> Route:
    violation = VIOLATIONS[violation_key]
    if violation.kind == "moving":
        return INTERNETWACHE
    if vehicle_type in RENTAL_TYPES:
        return SHARING_OPERATOR
    return BOWI


def catalog() -> dict:
    return {
        "violations": [
            {"key": v.key, "kind": v.kind, "description": v.label_en}
            for v in VIOLATIONS.values()
        ],
        "vehicle_types": list(VEHICLE_TYPES_DE),
        "routing": {
            "parking by a car/van/truck/motorcycle/moped/private e-scooter": BOWI.authority + f" <{BOWI.to}>",
            "parking by a rental e-scooter/bike": SHARING_OPERATOR.authority,
            "any moving violation": INTERNETWACHE.authority,
        },
    }
