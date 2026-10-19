#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

from Auth.fcm_receiver import FcmReceiver
from NovaApi.ExecuteAction.nbe_execute_action import create_action_request, serialize_action_request
from NovaApi.nova_request import nova_request
from NovaApi.scopes import NOVA_ACTION_API_SCOPE
from ProtoDecoders import DeviceUpdate_pb2

def create_sound_request(should_start, canonic_device_id, gcm_registration_id):

    action_request = create_action_request(canonic_device_id, gcm_registration_id)

    if should_start:
        action_request.action.startSound.component = DeviceUpdate_pb2.DeviceComponent.DEVICE_COMPONENT_UNSPECIFIED
    else:
        action_request.action.stopSound.component = DeviceUpdate_pb2.DeviceComponent.DEVICE_COMPONENT_UNSPECIFIED

    return serialize_action_request(action_request)


def send_sound_request(should_start, canonic_device_id):
    """Asks the tracker to start or stop ringing. The tracker must be in Bluetooth range of one of your Android devices."""

    fcm_token = FcmReceiver().get_fcm_token()
    hex_payload = create_sound_request(should_start, canonic_device_id, fcm_token)
    nova_request(NOVA_ACTION_API_SCOPE, hex_payload)
