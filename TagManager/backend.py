#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

from TagManager.models import TagInfo, SharedAccess


class FindMyBackend:
    """Connection to Google Find My Device. The menu only talks to this class,
    so it can be tested with a fake backend without network or protobuf."""

    def list_tags(self) -> list:
        from NovaApi.ListDevices.nbe_list_devices import get_device_list

        return tags_from_device_list(get_device_list())

    def locate(self, canonic_id: str, timeout: int) -> list:
        from NovaApi.ExecuteAction.LocateTracker.decrypt_locations import decrypt_location_records
        from NovaApi.ExecuteAction.LocateTracker.location_request import request_location_update

        device_update = request_location_update(canonic_id, timeout)
        return decrypt_location_records(device_update)

    def start_sound(self, canonic_id: str) -> None:
        from NovaApi.ExecuteAction.PlaySound.sound_request import send_sound_request

        send_sound_request(True, canonic_id)

    def stop_sound(self, canonic_id: str) -> None:
        from NovaApi.ExecuteAction.PlaySound.sound_request import send_sound_request

        send_sound_request(False, canonic_id)

    def register_tracker(self) -> None:
        from SpotApi.CreateBleDevice.create_ble_device import register_esp32

        register_esp32()


def tags_from_device_list(device_list) -> list:
    from ProtoDecoders import DeviceUpdate_pb2
    from SpotApi.CreateBleDevice.config import mcu_fast_pair_model_id

    tags = []
    for device in device_list.deviceMetadata:
        if device.identifierInformation.type == DeviceUpdate_pb2.IDENTIFIER_ANDROID:
            canonic_ids = device.identifierInformation.phoneInformation.canonicIds.canonicId
        else:
            canonic_ids = device.identifierInformation.canonicIds.canonicId

        registration = device.information.deviceRegistration
        shared_with = [
            SharedAccess(email=access.email, is_owner=access.isOwner, this_account=access.thisAccount)
            for access in device.information.accessInformation
            if access.email
        ]

        for canonic_id in canonic_ids:
            tags.append(TagInfo(
                canonic_id=canonic_id.id,
                google_name=device.userDefinedDeviceName,
                device_type=registration.deviceTypeInformation.deviceType,
                manufacturer=registration.manufacturer,
                model=registration.model,
                pair_date=registration.pairDate,
                is_mcu=registration.fastPairModelId == mcu_fast_pair_model_id,
                image_url=device.imageInformation.imageUrl,
                shared_with=shared_with,
            ))
    return tags
