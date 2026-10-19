#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import csv
import datetime
import os
import re
from xml.sax.saxutils import escape

from TagManager.formatting import format_datetime, maps_link, status_label

DEFAULT_EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")


def export_file_path(tag_name: str, extension: str, directory: str = DEFAULT_EXPORT_DIR) -> str:
    safe_name = re.sub(r"[^\w\-]+", "_", tag_name, flags=re.UNICODE).strip("_") or "tag"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(directory, f"{safe_name}_{stamp}.{extension}")


def export_csv(records, path: str) -> str:
    """CSV with a header row; opens in Excel and can be imported into Google My Maps."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # utf-8-sig, so Excel recognises the encoding of Czech characters
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["cas", "cas_unix", "latitude", "longitude", "vyska_m", "presnost_m", "zdroj", "misto", "odkaz"])
        for record in records:
            has_coordinates = record.has_coordinates
            writer.writerow([
                format_datetime(record.time),
                record.time,
                record.latitude if has_coordinates else "",
                record.longitude if has_coordinates else "",
                record.altitude if has_coordinates else "",
                record.accuracy if has_coordinates else "",
                status_label(record.status, record.is_own_report),
                record.name,
                maps_link(record.latitude, record.longitude) if has_coordinates else "",
            ])
    return path


def export_kml(tag_name: str, records, path: str) -> str:
    """KML with one point per location and a line connecting them in time order (Google Earth / My Maps)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    located = sorted((record for record in records if record.has_coordinates), key=lambda record: record.time)

    placemarks = []
    for record in located:
        description = f"{status_label(record.status, record.is_own_report)}"
        if record.accuracy:
            description += f", přesnost ±{record.accuracy:.0f} m"
        placemarks.append(
            "    <Placemark>\n"
            f"      <name>{escape(format_datetime(record.time))}</name>\n"
            f"      <description>{escape(description)}</description>\n"
            f"      <TimeStamp><when>{_iso_utc(record.time)}</when></TimeStamp>\n"
            f"      <Point><coordinates>{record.longitude},{record.latitude},0</coordinates></Point>\n"
            "    </Placemark>"
        )

    if len(located) > 1:
        coordinates = " ".join(f"{record.longitude},{record.latitude},0" for record in located)
        placemarks.append(
            "    <Placemark>\n"
            "      <name>Trasa</name>\n"
            f"      <LineString><tessellate>1</tessellate><coordinates>{coordinates}</coordinates></LineString>\n"
            "    </Placemark>"
        )

    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Document>\n"
        f"    <name>{escape(tag_name)}</name>\n"
        + "\n".join(placemarks) + "\n"
        "  </Document>\n"
        "</kml>\n"
    )

    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
    return path


def _iso_utc(timestamp: int) -> str:
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
