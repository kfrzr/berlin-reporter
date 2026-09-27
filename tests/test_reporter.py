import email
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from berlin_reporter import config, photos, report
from berlin_reporter.mailer import build_message, deliver


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE_LOCATIONS", [])
    env = {
        "REPORTS_DIR": str(tmp_path / "reports"),
        "REPORTER_NAME": "Erika Mustermann",
        "REPORTER_ADDRESS": "Musterstraße 1, 10115 Berlin",
        "REPORTER_EMAIL": "erika@example.com",
        "DRY_RUN": "1",
        "GEOCODE": "0",
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return config.load_settings()


def _dms(value):
    d = int(value)
    m = int((value - d) * 60)
    s = round(((value - d) * 60 - m) * 60, 2)
    return (d, m, s)


@pytest.fixture
def photo(tmp_path):
    img = Image.new("RGB", (4000, 3000), "gray")
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = "2026:09:20 14:05:33"  # DateTimeOriginal
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", _dms(52.500123)
    gps[3], gps[4] = "E", _dms(13.418456)
    exif[274] = 6  # rotated
    path = tmp_path / "car.jpg"
    img.save(path, exif=exif.tobytes())
    return path


def test_metadata(photo):
    info = photos.read_metadata(photo)
    assert info.taken_at == "2026-09-20T14:05:33"
    assert info.latitude == pytest.approx(52.500123, abs=1e-4)
    assert info.longitude == pytest.approx(13.418456, abs=1e-4)


def test_attachment_is_upright_and_keeps_time(photo):
    data = photos.attachment_jpeg(photo)
    import io
    with Image.open(io.BytesIO(data)) as img:
        assert img.size[0] < img.size[1]  # orientation applied
        assert max(img.size) == 2560
        assert img.getexif().get_ifd(0x8769)[36867] == "2026:09:20 14:05:33"


def test_parking_draft_goes_to_bowi_and_sends_dry_run(settings, photo):
    draft = report.create_draft(
        settings, photos=[str(photo)], plate="b-ab 1234", vehicle_type="car", violation="radweg",
        time_start="2026-09-20T14:05", time_end="2026-09-20T14:12",
        address="Oranienstraße 10, 10999 Berlin", district="Friedrichshain-Kreuzberg",
        vehicle_make="VW Golf", vehicle_color="schwarz",
        obstruction="Radfahrende mussten auf die Fahrbahn ausweichen",
    )
    assert draft.route == "bowi_email"
    assert draft.plate == "B-AB 1234"
    text = report.body(draft, settings)
    assert "Tatzeit: 20.09.2026, 14:05 bis 14:12 Uhr" in text
    assert "Radweg" in text and "Erika Mustermann" in text and "Zeuge" in text

    msg = build_message(draft, settings, "anzeige@bowi.berlin.de")
    result = deliver(msg, settings, draft.id)
    assert result.startswith("dry_run")
    parsed = email.message_from_bytes((settings.outbox / f"{draft.id}.eml").read_bytes())
    assert parsed["To"] == "anzeige@bowi.berlin.de"
    assert parsed["Cc"] == "erika@example.com"
    assert [p.get_filename() for p in parsed.walk() if p.get_filename()] == [f"{draft.id}_foto1.jpg"]


def test_routing(settings, photo):
    common = dict(photos=[str(photo)], time_start="2026-09-20T14:05", address="Kottbusser Tor")
    assert report.create_draft(settings, plate="B-X 1", vehicle_type="car", violation="rotlicht", **common).route == "internetwache"
    assert report.create_draft(settings, plate="123 ABC", vehicle_type="rental_e_scooter", violation="gehweg", **common).route == "sharing_operator"
    assert report.create_draft(settings, plate="B-MC 77", vehicle_type="motorcycle", violation="gehweg", **common).route == "bowi_email"


def test_validation(settings, photo):
    with pytest.raises(report.ReportError):
        report.create_draft(settings, photos=[str(photo)], plate="", vehicle_type="car", violation="gehweg",
                            time_start="2026-09-20T14:05", address="x")
    future = (datetime.now() + timedelta(days=1)).isoformat(timespec="minutes")
    with pytest.raises(report.ReportError):
        report.create_draft(settings, photos=[str(photo)], plate="B-A 1", vehicle_type="car", violation="gehweg",
                            time_start=future, address="x")
    with pytest.raises(report.ReportError):
        report.create_draft(settings, photos=[str(photo)], plate="B-A 1", vehicle_type="car",
                            violation="sonstiges_parken", time_start="2026-09-20T14:05", address="x")


def test_warnings_and_duplicates(settings, photo):
    d = report.create_draft(settings, photos=[str(photo)], plate="XYZ", vehicle_type="car", violation="gehweg",
                            time_start="2026-09-20T14:05", address="x")
    assert any("does not look like" in w for w in d.warnings)
    assert any("second photo" in w for w in d.warnings)
    report.append_history(settings, d, "sent")
    d2 = report.create_draft(settings, photos=[str(photo)], plate="xyz", vehicle_type="car", violation="gehweg",
                             time_start="2026-09-20T18:00", address="x")
    assert any("already reported" in w for w in d2.warnings)


@pytest.mark.parametrize("plate", ["B-AB 1234", "B AB 1234", "M-X 1E", "LDS-K 42", "123 ABC", "LÖ-AB 12"])
def test_plate_formats(plate):
    assert report.plate_looks_valid(report.normalize_plate(plate))


from berlin_reporter import webform


@pytest.mark.parametrize("address,expected", [
    ("Oranienstraße 10a, 10999 Berlin", ("Oranienstraße", "10a", "10999", "Berlin")),
    ("Karl-Marx-Allee 34-36, 10178 Berlin", ("Karl-Marx-Allee", "34-36", "10178", "Berlin")),
    ("Straße des 17. Juni 135, 10623 Berlin", ("Straße des 17. Juni", "135", "10623", "Berlin")),
    ("Kottbusser Tor", ("Kottbusser Tor", None, None, None)),
])
def test_split_address(address, expected):
    a = webform.split_address(address)
    assert (a["street"], a["house_number"], a["postcode"], a["city"]) == expected


def test_web_payload(settings, photo):
    draft = report.create_draft(
        settings, photos=[str(photo)], plate="B-RL 42", vehicle_type="car", violation="rotlicht",
        time_start="2026-09-20T08:31", address="Frankfurter Allee 1, 10247 Berlin", district="Friedrichshain-Kreuzberg",
    )
    payload = webform.form_payload(draft, settings)
    assert payload["start_url"].startswith("https://www.internetwache-polizei-berlin.de")
    assert payload["reporter"]["first_name"] == "Erika" and payload["reporter"]["last_name"] == "Mustermann"
    assert payload["reporter"]["address_postcode"] == "10115"
    assert payload["incident"]["date"] == "20.09.2026" and payload["incident"]["time_from"] == "08:31"
    assert "B-RL 42" in payload["description_de"] and "Rotlichts" in payload["description_de"]
    assert len(payload["upload_files"]) == 1 and Path(payload["upload_files"][0]).is_file()
    assert Path(payload["upload_files"][0]).is_relative_to(settings.upload_dir)


def test_keychain_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE_LOCATIONS", [])
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    monkeypatch.delenv("REPORTER_NAME", raising=False)
    monkeypatch.setattr(config, "keyring_get", lambda k: {"REPORTER_NAME": "Aus Keychain"}.get(k, ""))
    assert config.load_settings().reporter_name == "Aus Keychain"
    monkeypatch.setenv("REPORTER_NAME", "Aus Env")
    assert config.load_settings().reporter_name == "Aus Env"
