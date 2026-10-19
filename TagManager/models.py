#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

from dataclasses import dataclass, field


@dataclass
class SharedAccess:
    email: str
    is_owner: bool = False
    this_account: bool = False


@dataclass
class TagInfo:
    """A tracker as reported by Google (read-only data from the device list)."""

    canonic_id: str
    google_name: str
    device_type: int = 0
    manufacturer: str = ""
    model: str = ""
    pair_date: int = 0
    is_mcu: bool = False
    image_url: str = ""
    shared_with: list = field(default_factory=list)


@dataclass
class TagMeta:
    """Local data the user keeps about a tracker. Never sent to Google."""

    alias: str = ""
    note: str = ""
    group: str = ""
    favorite: bool = False
    hidden: bool = False
