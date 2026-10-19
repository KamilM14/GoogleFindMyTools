#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import argparse
import sys

from TagManager.menu import DEFAULT_TIMEOUT_SECONDS, friendly_error


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="GoogleFindMyTools – hledání a správa Find My Device tagů. Bez parametrů spustí interaktivní menu.")
    parser.add_argument("--list", action="store_true", help="vypíše tagy a skončí")
    parser.add_argument("--locate", metavar="TAG", help="najde polohu tagu (číslo z --list, název, přezdívka nebo canonic ID)")
    parser.add_argument("--json", action="store_true", help="výstup --list / --locate ve formátu JSON")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help=f"jak dlouho čekat na odpověď tagu v sekundách (výchozí {DEFAULT_TIMEOUT_SECONDS})")
    parser.add_argument("--classic", action="store_true", help="původní jednoduché menu GoogleFindMyTools")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    # Characters the console cannot show are replaced instead of crashing (e.g. output redirected on Windows)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    args = parse_args(argv)

    if args.classic:
        from NovaApi.ListDevices.nbe_list_devices import list_devices
        try:
            list_devices()
        except KeyboardInterrupt:
            return 130
        except Exception as e:
            print("Chyba: " + friendly_error(e), file=sys.stderr)
            return 1
        return 0

    from TagManager.backend import FindMyBackend
    from TagManager.store import TagStore

    backend = FindMyBackend()
    store = TagStore()
    sort_mode = store.get_setting("sort", "favorite")

    if args.list or args.locate:
        from TagManager.cli import list_command, locate_command
        try:
            if args.list:
                return list_command(backend, store, sort_mode, args.json)
            return locate_command(backend, store, args.locate, sort_mode, args.timeout, args.json)
        except KeyboardInterrupt:
            return 130
        except Exception as e:
            print("Chyba: " + friendly_error(e), file=sys.stderr)
            return 1

    from TagManager.menu import TagMenu
    TagMenu(backend, store, timeout=args.timeout).run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
