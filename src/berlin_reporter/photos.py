"""Photo metadata (time, GPS), reverse geocoding, and resizing for email/preview."""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import httpx
from PIL import ExifTags, Image, ImageOps

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # HEIC photos (iPhone default) will not open without it
    pass

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769


@dataclass
class PhotoInfo:
    path: str
    taken_at: str | None  # local wall-clock time as ISO string (Berlin time on a Berlin phone)
    latitude: float | None
    longitude: float | None
    address: str | None = None
    district: str | None = None
    neighbourhood: str | None = None
    in_berlin: bool | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def list_photos(folder: Path, limit: int = 20) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_SUFFIXES]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _to_degrees(value, ref: str | None) -> float | None:
    try:
        d, m, s = (float(x) for x in value)
    except (TypeError, ValueError):
        return None
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W") else deg


def read_metadata(path: Path) -> PhotoInfo:
    with Image.open(path) as img:
        exif = img.getexif()
        sub = exif.get_ifd(_EXIF_IFD)
        gps = exif.get_ifd(_GPS_IFD)

    raw_time = sub.get(ExifTags.Base.DateTimeOriginal) or exif.get(ExifTags.Base.DateTime)
    taken_at = None
    if raw_time:
        try:
            taken_at = datetime.strptime(str(raw_time).strip("\x00 "), "%Y:%m:%d %H:%M:%S").isoformat()
        except ValueError:
            taken_at = None

    lat = lon = None
    if gps:
        lat = _to_degrees(gps.get(ExifTags.GPS.GPSLatitude), gps.get(ExifTags.GPS.GPSLatitudeRef))
        lon = _to_degrees(gps.get(ExifTags.GPS.GPSLongitude), gps.get(ExifTags.GPS.GPSLongitudeRef))

    return PhotoInfo(path=str(path), taken_at=taken_at, latitude=lat, longitude=lon)


def reverse_geocode(info: PhotoInfo, contact_email: str = "") -> PhotoInfo:
    """Fill address/district from GPS using OpenStreetMap Nominatim. Failures are non-fatal."""
    if info.latitude is None or info.longitude is None:
        return info
    ua = "berlin-reporter/0.1" + (f" ({contact_email})" if contact_email else "")
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={
                "lat": info.latitude,
                "lon": info.longitude,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 18,
                "accept-language": "de",
            },
            headers={"User-Agent": ua},
            timeout=10,
        )
        resp.raise_for_status()
        addr = resp.json().get("address", {})
    except (httpx.HTTPError, ValueError):
        return info

    street = addr.get("road") or addr.get("pedestrian") or addr.get("footway")
    number = addr.get("house_number")
    postcode = addr.get("postcode")
    city = addr.get("city") or addr.get("town") or addr.get("state")
    street_part = " ".join(x for x in (street, number) if x)
    city_part = " ".join(x for x in (postcode, city) if x)
    info.address = ", ".join(x for x in (street_part, city_part) if x) or None
    info.district = addr.get("borough") or addr.get("city_district")
    info.neighbourhood = addr.get("suburb") or addr.get("quarter")
    info.in_berlin = (addr.get("state") == "Berlin") or (addr.get("city") == "Berlin")
    return info


def _open_upright(path: Path) -> Image.Image:
    img = Image.open(path)
    return ImageOps.exif_transpose(img)


def preview_jpeg(path: Path, max_edge: int = 1568) -> bytes:
    """A JPEG small enough to show to the model (for reading plates and judging the scene)."""
    with _open_upright(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_edge, max_edge))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def attachment_jpeg(path: Path, max_edge: int = 2560, quality: int = 85) -> bytes:
    """Resize for email while keeping the original EXIF (capture time and GPS are evidence)."""
    with Image.open(path) as original:
        exif = original.getexif()
        img = ImageOps.exif_transpose(original).convert("RGB")
    # exif_transpose already rotated the pixels; reset the orientation tag to "normal".
    exif[ExifTags.Base.Orientation] = 1
    img.thumbnail((max_edge, max_edge))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, exif=exif.tobytes())
    return buf.getvalue()
