#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import binascii
import requests
from bs4 import BeautifulSoup

from Auth.aas_token_retrieval import get_aas_token
from Auth.adm_token_retrieval import get_adm_token
from Auth.token_retrieval import invalidate_token_cache
from Auth.username_provider import get_username

REQUEST_TIMEOUT_SECONDS = 30


class NovaRequestError(Exception):
    def __init__(self, status_code, message):
        super().__init__(f"Nova API request failed (HTTP {status_code}): {message}")
        self.status_code = status_code


def nova_request(api_scope, hex_payload):
    url = "https://android.googleapis.com/nova/" + api_scope
    payload = binascii.unhexlify(hex_payload)

    response = _post(url, payload)

    # The cached ADM token may have expired or been revoked; retry once with a fresh one
    if response.status_code == 401:
        invalidate_token_cache()
        response = _post(url, payload)

    if response.status_code == 200:
        return response.content.hex()

    soup = BeautifulSoup(response.text, 'html.parser')
    message = soup.get_text().strip()
    print("[NovaRequest] Error: ", message)
    raise NovaRequestError(response.status_code, message)


def _post(url, payload):
    android_device_manager_oauth_token = get_adm_token(get_username())

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Authorization": "Bearer " + android_device_manager_oauth_token,
        "Accept-Language": "en-US",
        "User-Agent": "fmd/20006320; gzip"
    }

    return requests.post(url, headers=headers, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)


if __name__ == '__main__':
    print(get_aas_token())
