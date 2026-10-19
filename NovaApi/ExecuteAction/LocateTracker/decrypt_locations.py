#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import datetime
import hashlib

from FMDNCrypto.foreign_tracker_cryptor import decrypt
from KeyBackup.cloud_key_decryptor import decrypt_eik, decrypt_aes_gcm
from NovaApi.ExecuteAction.LocateTracker.decrypted_location import LocationRecord
from ProtoDecoders import DeviceUpdate_pb2
from ProtoDecoders import Common_pb2
from ProtoDecoders.DeviceUpdate_pb2 import DeviceRegistration
from ProtoDecoders.decoder import parse_device_update_protobuf
from SpotApi.CreateBleDevice.config import mcu_fast_pair_model_id
from SpotApi.CreateBleDevice.util import flip_bits
from SpotApi.GetEidInfoForE2eeDevices.get_eid_info_request import get_eid_info
from SpotApi.GetEidInfoForE2eeDevices.get_owner_key import get_owner_key


class IdentityKeyError(Exception):
    """The identity key of a tracker could not be decrypted with the current owner key."""


def create_google_maps_link(latitude, longitude):
    try:
        latitude = float(latitude)
        longitude = float(longitude)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Invalid latitude or longitude values.")
    except ValueError as e:
        return f"Error: {e}" #more descriptive error message for the user
    base_url = "https://www.google.com/maps/search/?api=1"
    query_params = f"query={latitude},{longitude}"

    return f"{base_url}&{query_params}"

# Indicates if the device is a custom microcontroller
def is_mcu_tracker(device_registration: DeviceRegistration) -> bool:
    return device_registration.fastPairModelId == mcu_fast_pair_model_id


def retrieve_identity_key(device_registration: DeviceRegistration) -> bytes:
    is_mcu = is_mcu_tracker(device_registration)
    encrypted_user_secrets = device_registration.encryptedUserSecrets

    encrypted_identity_key = flip_bits(
        encrypted_user_secrets.encryptedIdentityKey,
        is_mcu)
    owner_key = get_owner_key()

    try:
        identity_key = decrypt_eik(owner_key, encrypted_identity_key)
        return identity_key
    except Exception as e:

        e2eeData = get_eid_info()
        current_owner_key_version = e2eeData.encryptedOwnerKeyAndMetadata.ownerKeyVersion

        # Raise instead of exit(1), so one broken tracker does not terminate the whole program
        if encrypted_user_secrets.ownerKeyVersion < current_owner_key_version:
            raise IdentityKeyError(f"Failed to decrypt E2EE data. This tracker was encrypted with owner key version {encrypted_user_secrets.ownerKeyVersion}, but the current owner key version is {current_owner_key_version}.\nThis happens if you reset your end-to-end-encrypted data in the past.\nThe tracker cannot be decrypted anymore, and it is recommended to remove it in the Find My Device app.") from e
        else:
            raise IdentityKeyError(f"Failed to decrypt identity key encrypted with owner key version {encrypted_user_secrets.ownerKeyVersion}, current owner key version is {current_owner_key_version}.\nThis may happen if you reset your end-to-end-encrypted data. To resolve this issue, open the folder 'Auth' and delete the file 'secrets.json'.") from e


def decrypt_location_records(device_update_protobuf) -> list[LocationRecord]:
    """Decrypts all location reports of a device update, newest first."""

    device_registration = device_update_protobuf.deviceMetadata.information.deviceRegistration

    identity_key = retrieve_identity_key(device_registration)
    locations_proto = device_update_protobuf.deviceMetadata.information.locationInformation.reports.recentLocationAndNetworkLocations
    is_mcu = is_mcu_tracker(device_registration)

    # At All Areas Reports or Own Reports
    recent_location = locations_proto.recentLocation
    recent_location_time = locations_proto.recentLocationTimestamp

    # High Traffic Reports
    network_locations = list(locations_proto.networkLocations)
    network_locations_time = list(locations_proto.networkLocationTimestamps)

    if locations_proto.HasField("recentLocation"):
        network_locations.append(recent_location)
        network_locations_time.append(recent_location_time)

    records = []
    for loc, time in zip(network_locations, network_locations_time):

        if loc.status == Common_pb2.Status.SEMANTIC:
            records.append(LocationRecord(
                time=int(time.seconds),
                status=loc.status,
                is_own_report=True,
                name=loc.semanticLocation.locationName
            ))
            continue

        # A single report that cannot be decrypted should not hide all the others
        try:
            encrypted_location = loc.geoLocation.encryptedReport.encryptedLocation
            public_key_random = loc.geoLocation.encryptedReport.publicKeyRandom

            if public_key_random == b"":  # Own Report
                identity_key_hash = hashlib.sha256(identity_key).digest()
                decrypted_location = decrypt_aes_gcm(identity_key_hash, encrypted_location)
            else:
                time_offset = 0 if is_mcu else loc.geoLocation.deviceTimeOffset
                decrypted_location = decrypt(identity_key, encrypted_location, public_key_random, time_offset)

            proto_loc = DeviceUpdate_pb2.Location()
            proto_loc.ParseFromString(decrypted_location)
        except Exception as e:
            print(f"[DecryptLocations] Skipping a location report that could not be decrypted: {e}")
            continue

        records.append(LocationRecord(
            time=int(time.seconds),
            status=loc.status,
            is_own_report=loc.geoLocation.encryptedReport.isOwnReport,
            latitude=proto_loc.latitude / 1e7,
            longitude=proto_loc.longitude / 1e7,
            altitude=proto_loc.altitude,
            accuracy=round(loc.geoLocation.accuracy, 1),
        ))

    records.sort(key=lambda record: record.time, reverse=True)
    return records


def decrypt_location_response_locations(device_update_protobuf):

    records = decrypt_location_records(device_update_protobuf)

    print("-" * 40)
    print("[DecryptLocations] Decrypted Locations:")

    if not records:
        print("No locations found.")
        return

    for loc in records:

        if loc.is_semantic:
            print(f"Semantic Location: {loc.name}")

        else:
            print(f"Latitude: {loc.latitude}")
            print(f"Longitude: {loc.longitude}")
            print(f"Altitude: {loc.altitude}")
            print(f"Accuracy: {loc.accuracy} m")
            print(f"Google Maps Link: {create_google_maps_link(loc.latitude, loc.longitude)}")

        print(f"Time: {datetime.datetime.fromtimestamp(loc.time).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Status: {loc.status_name}")
        print(f"Is Own Report: {loc.is_own_report}")
        print("-" * 40)

    return records


if __name__ == '__main__':
    res = parse_device_update_protobuf("")
    decrypt_location_response_locations(res)
