#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

from dataclasses import dataclass
from typing import Optional

from NovaApi.ExecuteAction.LocateTracker.decrypted_location import LocationRecord
from TagManager.formatting import device_type_label, normalize
from TagManager.models import TagInfo, TagMeta
from TagManager.store import TagStore

# (key, label) - the key is stored in the settings, the label is shown in the menu
SORT_MODES = [
    ("favorite", "oblíbené nahoře"),
    ("name", "podle názvu"),
    ("last_seen", "naposledy viděné nahoře"),
    ("group", "podle skupiny"),
]
SORT_LABELS = dict(SORT_MODES)
DEFAULT_SORT = "favorite"


@dataclass
class TagView:
    """A tag from Google combined with the local data about it."""

    info: TagInfo
    meta: TagMeta
    last_seen: Optional[LocationRecord]

    @property
    def canonic_id(self) -> str:
        return self.info.canonic_id

    @property
    def name(self) -> str:
        return self.meta.alias or self.info.google_name or "(bez názvu)"

    @property
    def search_text(self) -> str:
        parts = [
            self.name, self.info.google_name, self.meta.alias, self.meta.note, self.meta.group,
            device_type_label(self.info.device_type), self.info.manufacturer, self.info.model,
        ]
        return " ".join(normalize(part) for part in parts if part)


def build_view(store: TagStore, info: TagInfo) -> TagView:
    return TagView(info=info, meta=store.get_meta(info.canonic_id), last_seen=store.last_location(info.canonic_id))


def build_views(store: TagStore, tags, include_hidden: bool = False, filter_text: str = "", sort_mode: str = DEFAULT_SORT) -> list:
    views = [build_view(store, info) for info in tags]

    if not include_hidden:
        views = [view for view in views if not view.meta.hidden]

    words = normalize(filter_text).split()
    if words:
        views = [view for view in views if all(word in view.search_text for word in words)]

    return sort_views(views, sort_mode)


def sort_views(views, sort_mode: str) -> list:
    by_name = sorted(views, key=lambda view: normalize(view.name))

    if sort_mode == "name":
        return by_name
    if sort_mode == "last_seen":
        return sorted(by_name, key=lambda view: view.last_seen.time if view.last_seen else 0, reverse=True)
    if sort_mode == "group":
        # Tags without a group go last
        return sorted(by_name, key=lambda view: (not view.meta.group, normalize(view.meta.group)))
    return sorted(by_name, key=lambda view: not view.meta.favorite)


def find_views(views, query: str) -> list:
    """Finds tags by list number, canonic ID or name (exact match first, then partial)."""
    query = query.strip()
    if not query:
        return []

    if query.isdigit():
        index = int(query)
        return [views[index - 1]] if 1 <= index <= len(views) else []

    exact_id = [view for view in views if view.canonic_id == query]
    if exact_id:
        return exact_id

    wanted = normalize(query)
    exact_name = [view for view in views if wanted in (normalize(view.name), normalize(view.info.google_name))]
    if exact_name:
        return exact_name

    words = wanted.split()
    return [view for view in views if all(word in view.search_text for word in words)]
