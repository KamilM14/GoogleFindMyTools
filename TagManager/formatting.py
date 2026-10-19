#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import datetime
import math
import time
import unicodedata
from typing import Optional

# Labels for ProtoDecoders.DeviceUpdate_pb2.SpotDeviceType
DEVICE_TYPE_LABELS = {
    0: "neznámý",
    1: "tag",
    2: "sluchátka",
    3: "klíče",
    4: "hodinky",
    5: "peněženka",
    7: "taška",
    8: "notebook",
    9: "auto",
    10: "ovladač",
    11: "odznak",
    12: "kolo",
    13: "fotoaparát",
    14: "kočka",
    15: "nabíječka",
    16: "oblečení",
    17: "pes",
    18: "zápisník",
    19: "pas",
    20: "telefon",
    21: "reproduktor",
    22: "tablet",
    23: "hračka",
    24: "deštník",
    25: "stylus",
    26: "sluchátka (pecky)",
}

# Labels for ProtoDecoders.Common_pb2.Status
STATUS_LABELS = {
    0: "pojmenované místo",
    1: "vlastní zařízení",
    2: "síť (cizí zařízení)",
    3: "síť (souhrn více hlášení)",
}


def plural(count: int, one: str, few: str, many: str) -> str:
    """Czech plural: 1 tag, 2 tagy, 5 tagů."""
    if count == 1:
        word = one
    elif 2 <= count <= 4:
        word = few
    else:
        word = many
    return f"{count} {word}"


def device_type_label(device_type: int) -> str:
    return DEVICE_TYPE_LABELS.get(device_type, f"typ {device_type}")


def status_label(status: int, is_own_report: bool = False) -> str:
    label = STATUS_LABELS.get(status, f"stav {status}")
    if is_own_report and status != 0:
        label += ", vlastní hlášení"
    return label


def normalize(text: Optional[str]) -> str:
    """Lower case without diacritics, so 'klice' finds 'Klíče'."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower().strip()


def format_datetime(timestamp: Optional[int]) -> str:
    if not timestamp:
        return "—"
    return datetime.datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M")


def format_date(timestamp: Optional[int]) -> str:
    if not timestamp:
        return "—"
    return datetime.datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")


def relative_time(timestamp: Optional[int], now: Optional[float] = None) -> str:
    if not timestamp:
        return "nikdy"
    now = time.time() if now is None else now
    seconds = int(now - timestamp)

    if seconds < 60:
        return "právě teď"
    minutes = seconds // 60
    if minutes < 60:
        return f"před {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"před {hours} h"
    days = hours // 24
    if days == 1:
        return "včera"
    if days < 31:
        return f"před {days} dny"
    return format_date(timestamp)


def format_coordinates(latitude: float, longitude: float) -> str:
    return f"{latitude:.5f}, {longitude:.5f}"


def format_accuracy(accuracy: Optional[float]) -> str:
    if not accuracy:
        return ""
    return f"±{accuracy:.0f} m"


def format_distance(meters: float) -> str:
    if meters < 1000:
        return f"{meters:.0f} m"
    return f"{meters / 1000:.1f} km".replace(".", ",")


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two points in meters (haversine formula)."""
    earth_radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 2 * earth_radius * math.asin(math.sqrt(a))


def maps_link(latitude: float, longitude: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"


def describe_location(record) -> str:
    """One-line description of a LocationRecord, e.g. '50.08123, 14.42012 ±12 m'."""
    if record.is_semantic or not record.has_coordinates:
        return record.name or "neznámé místo"
    accuracy = format_accuracy(record.accuracy)
    coordinates = format_coordinates(record.latitude, record.longitude)
    return f"{coordinates} {accuracy}".strip()
