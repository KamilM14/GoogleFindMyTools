#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import threading
import time

import gpsoauth

from Auth.aas_token_retrieval import get_aas_token
from Auth.fcm_receiver import FcmReceiver

# OAuth tokens are valid for about an hour. Requesting a new one for every API call
# makes each action noticeably slower, so they are kept in memory until shortly before expiry.
_FALLBACK_TOKEN_LIFETIME_SECONDS = 30 * 60
_EXPIRY_MARGIN_SECONDS = 60

_token_cache = {}
_token_cache_lock = threading.Lock()


class TokenRetrievalError(Exception):
    pass


def request_token(username, scope, play_services = False):

    cache_key = (username, scope, play_services)

    with _token_cache_lock:
        cached = _token_cache.get(cache_key)
        if cached is not None and cached[1] > time.time():
            return cached[0]

    aas_token = get_aas_token()
    android_id = FcmReceiver().get_android_id()
    request_app = 'com.google.android.gms' if play_services else 'com.google.android.apps.adm'

    auth_response = gpsoauth.perform_oauth(
        username, aas_token, android_id,
        service='oauth2:https://www.googleapis.com/auth/' + scope,
        app=request_app,
        client_sig='38918a453d07199354f8b19af05ec6562ced5788')

    if 'Auth' not in auth_response:
        error = auth_response.get('Error', 'unknown error')
        raise TokenRetrievalError(
            f"Could not get an OAuth token for scope '{scope}' ({error}). "
            "Your login has probably expired or was revoked. "
            "Delete the file 'Auth/secrets.json' and run the script again to log in.")

    token = auth_response['Auth']

    try:
        expires_at = int(auth_response['Expiry'])
    except (KeyError, ValueError):
        expires_at = int(time.time()) + _FALLBACK_TOKEN_LIFETIME_SECONDS

    with _token_cache_lock:
        _token_cache[cache_key] = (token, expires_at - _EXPIRY_MARGIN_SECONDS)

    return token


def invalidate_token_cache():
    with _token_cache_lock:
        _token_cache.clear()
