#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

from dataclasses import dataclass, asdict
from typing import Optional


class WrappedLocation:
    def __init__(self, decrypted_location, time, accuracy, status, is_own_report, name):
        self.time = time
        self.status = status
        self.decrypted_location = decrypted_location
        self.is_own_report = is_own_report
        self.accuracy = accuracy
        self.name = name


# Values of Common_pb2.Status, duplicated so this module does not depend on protobuf
STATUS_SEMANTIC = 0
STATUS_NAMES = {
    0: "SEMANTIC",
    1: "LAST_KNOWN",
    2: "CROWDSOURCED",
    3: "AGGREGATED",
}


@dataclass
class LocationRecord:
    """A decrypted location report, ready to be displayed or stored."""

    time: int
    status: int
    is_own_report: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[int] = None
    accuracy: Optional[float] = None
    # Name of the place for semantic reports (e.g. "Home"), which have no coordinates
    name: str = ""

    @property
    def is_semantic(self) -> bool:
        return self.status == STATUS_SEMANTIC

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def status_name(self) -> str:
        return STATUS_NAMES.get(self.status, str(self.status))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LocationRecord":
        fields = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in fields})
