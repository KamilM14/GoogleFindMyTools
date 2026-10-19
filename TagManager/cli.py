#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import contextlib
import json
import sys

from TagManager.catalog import build_view, build_views, find_views
from TagManager.formatting import describe_location, device_type_label, format_datetime, maps_link, relative_time, status_label


def _location_json(record) -> dict:
    data = record.to_dict()
    data["status_label"] = status_label(record.status, record.is_own_report)
    if record.has_coordinates:
        data["maps_link"] = maps_link(record.latitude, record.longitude)
    return data


def _tag_json(number: int, view) -> dict:
    return {
        "number": number,
        "name": view.name,
        "google_name": view.info.google_name,
        "alias": view.meta.alias,
        "group": view.meta.group,
        "note": view.meta.note,
        "favorite": view.meta.favorite,
        "hidden": view.meta.hidden,
        "type": device_type_label(view.info.device_type),
        "canonic_id": view.canonic_id,
        "last_seen": _location_json(view.last_seen) if view.last_seen else None,
    }


@contextlib.contextmanager
def _quiet_stdout(enabled: bool):
    """In JSON mode, log lines of the library go to stderr, so stdout stays valid JSON."""
    if not enabled:
        yield
        return
    with contextlib.redirect_stdout(sys.stderr):
        yield


def list_command(backend, store, sort_mode: str, as_json: bool) -> int:
    with _quiet_stdout(as_json):
        tags = backend.list_tags()
    views = build_views(store, tags, include_hidden=True, sort_mode=sort_mode)

    if as_json:
        print(json.dumps([_tag_json(number, view) for number, view in enumerate(views, start=1)], ensure_ascii=False, indent=2))
        return 0

    for number, view in enumerate(views, start=1):
        flags = ("*" if view.meta.favorite else " ") + ("S" if view.meta.hidden else " ")
        last = f"{relative_time(view.last_seen.time)}: {describe_location(view.last_seen)}" if view.last_seen else "—"
        print(f"{number:>3} {flags} {view.name:<24} {device_type_label(view.info.device_type):<12} {last}")
    return 0


def locate_command(backend, store, query: str, sort_mode: str, timeout: int, as_json: bool) -> int:
    with _quiet_stdout(as_json):
        tags = backend.list_tags()
    views = build_views(store, tags, include_hidden=True, sort_mode=sort_mode)
    matches = find_views(views, query)

    if len(matches) != 1:
        names = ", ".join(view.name for view in matches)
        message = f"Tag „{query}“ nenalezen." if not matches else f"„{query}“ odpovídá více tagům: {names}. Upřesni název."
        print(message, file=sys.stderr)
        return 2

    view = matches[0]
    with _quiet_stdout(as_json):
        records = backend.locate(view.canonic_id, timeout)
    store.add_locations(view.canonic_id, records)

    if as_json:
        number = views.index(view) + 1
        view = build_view(store, view.info)
        print(json.dumps({"tag": _tag_json(number, view), "locations": [_location_json(record) for record in records]}, ensure_ascii=False, indent=2))
        return 0

    print(f"{view.name}: nalezeno poloh {len(records)}")
    for record in records:
        line = f"  {format_datetime(record.time)}  {describe_location(record)}  [{status_label(record.status, record.is_own_report)}]"
        if record.has_coordinates:
            line += f"  {maps_link(record.latitude, record.longitude)}"
        print(line)
    return 0
