#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import json
import os
import time
from dataclasses import fields
from typing import Optional

from NovaApi.ExecuteAction.LocateTracker.decrypted_location import LocationRecord
from TagManager.models import TagMeta

DEFAULT_STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag_data.json")

# Enough for months of regular lookups, while keeping the file small
MAX_HISTORY_PER_TAG = 1000

_META_FIELDS = {f.name for f in fields(TagMeta)}


class TagStore:
    """Local JSON file with aliases, groups, notes, favorites and location history of tags."""

    def __init__(self, path: str = DEFAULT_STORE_FILE):
        self.path = path
        self.load_warning = None
        self._data = self._load()

    # --- file handling ------------------------------------------------------------

    def _load(self) -> dict:
        empty = {"version": 1, "tags": {}, "settings": {}}
        if not os.path.exists(self.path):
            return empty

        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                raise ValueError("unexpected content")
        except (OSError, ValueError) as e:
            # Keep the broken file for manual recovery instead of overwriting it
            backup = f"{self.path}.broken-{int(time.time())}"
            try:
                os.replace(self.path, backup)
                self.load_warning = f"Soubor s daty tagů byl poškozený ({e}). Záloha: {backup}"
            except OSError:
                self.load_warning = f"Soubor s daty tagů nejde načíst ({e})."
            return empty

        data.setdefault("version", 1)
        data.setdefault("tags", {})
        data.setdefault("settings", {})
        return data

    def save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temp_path = self.path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(self._data, file, ensure_ascii=False, indent=1)
        os.replace(temp_path, self.path)

    def _entry(self, canonic_id: str, create: bool = False) -> Optional[dict]:
        tags = self._data["tags"]
        if canonic_id not in tags and create:
            tags[canonic_id] = {}
        return tags.get(canonic_id)

    # --- metadata -----------------------------------------------------------------

    def get_meta(self, canonic_id: str) -> TagMeta:
        entry = self._entry(canonic_id) or {}
        return TagMeta(**{key: value for key, value in entry.items() if key in _META_FIELDS})

    def update_meta(self, canonic_id: str, **changes) -> TagMeta:
        unknown = set(changes) - _META_FIELDS
        if unknown:
            raise ValueError(f"Neznámé položky: {', '.join(sorted(unknown))}")

        entry = self._entry(canonic_id, create=True)
        entry.update(changes)
        self.save()
        return self.get_meta(canonic_id)

    def remember_name(self, canonic_id: str, google_name: str) -> None:
        """Keeps the Google name, so exported history stays readable even after the tag is removed."""
        entry = self._entry(canonic_id, create=True)
        if entry.get("google_name") != google_name:
            entry["google_name"] = google_name
            self.save()

    def groups(self) -> list:
        names = {entry.get("group", "") for entry in self._data["tags"].values()}
        return sorted((name for name in names if name), key=str.lower)

    # --- location history -----------------------------------------------------------

    def history(self, canonic_id: str) -> list:
        entry = self._entry(canonic_id) or {}
        return [LocationRecord.from_dict(item) for item in entry.get("history", [])]

    def add_locations(self, canonic_id: str, records) -> int:
        """Stores new location reports (duplicates are skipped). Returns how many were new."""
        entry = self._entry(canonic_id, create=True)
        history = entry.setdefault("history", [])
        known = {self._record_key(item) for item in history}

        added = 0
        for record in records:
            item = record.to_dict()
            key = self._record_key(item)
            if key in known:
                continue
            known.add(key)
            history.append(item)
            added += 1

        history.sort(key=lambda item: item.get("time", 0), reverse=True)
        del history[MAX_HISTORY_PER_TAG:]
        self.save()
        return added

    def clear_history(self, canonic_id: str) -> int:
        entry = self._entry(canonic_id)
        if not entry or not entry.get("history"):
            return 0
        count = len(entry["history"])
        entry["history"] = []
        self.save()
        return count

    def last_location(self, canonic_id: str, with_coordinates: bool = False) -> Optional[LocationRecord]:
        for record in self.history(canonic_id):
            if not with_coordinates or record.has_coordinates:
                return record
        return None

    @staticmethod
    def _record_key(item: dict) -> tuple:
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        return (
            item.get("time"),
            round(latitude, 6) if latitude is not None else None,
            round(longitude, 6) if longitude is not None else None,
            item.get("status"),
            item.get("name", ""),
        )

    # --- settings ---------------------------------------------------------------------

    def get_setting(self, name: str, default=None):
        return self._data["settings"].get(name, default)

    def set_setting(self, name: str, value) -> None:
        if self._data["settings"].get(name) != value:
            self._data["settings"][name] = value
            self.save()
