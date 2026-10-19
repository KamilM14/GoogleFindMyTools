#
#  Tests for TagManager (menu, správa tagů, historie, export).
#  Run from the repository root:  python -m unittest discover -s tests -v
#  They need no network and no Google login - a fake backend replaces Google.
#

import contextlib
import io
import json
import os
import tempfile
import time
import unittest
import xml.etree.ElementTree as ElementTree

from NovaApi.ExecuteAction.LocateTracker.decrypted_location import LocationRecord
from TagManager import cli, export
from TagManager.catalog import build_views, find_views
from TagManager.console import Console
from TagManager.formatting import distance_m, normalize, plural, relative_time, describe_location
from TagManager.menu import TagMenu, friendly_error
from TagManager.models import TagInfo
from TagManager.store import TagStore, MAX_HISTORY_PER_TAG

NOW = int(time.time())


class LocationTimeoutError(Exception):
    """Same name as the real exception, so the friendly message is used."""


def record(minutes_ago, latitude=50.08, longitude=14.42, status=2, name=""):
    if name:
        return LocationRecord(time=NOW - minutes_ago * 60, status=0, is_own_report=True, name=name)
    return LocationRecord(time=NOW - minutes_ago * 60, status=status, is_own_report=False,
                          latitude=latitude, longitude=longitude, altitude=0, accuracy=12.0)


class FakeBackend:

    def __init__(self, tags, locations=None):
        self.tags = tags
        self.locations = locations or {}
        self.calls = []

    def list_tags(self):
        self.calls.append(("list",))
        return list(self.tags)

    def locate(self, canonic_id, timeout):
        self.calls.append(("locate", canonic_id))
        result = self.locations.get(canonic_id, [])
        if isinstance(result, Exception):
            raise result
        return list(result)

    def start_sound(self, canonic_id):
        self.calls.append(("start_sound", canonic_id))

    def stop_sound(self, canonic_id):
        self.calls.append(("stop_sound", canonic_id))

    def register_tracker(self):
        self.calls.append(("register",))


def sample_tags():
    return [
        TagInfo(canonic_id="id-keys", google_name="Klíče", device_type=3, manufacturer="Chipolo", model="ONE Point"),
        TagInfo(canonic_id="id-bag", google_name="Batoh", device_type=7),
        TagInfo(canonic_id="id-bike", google_name="Kolo", device_type=12),
    ]


class StoreTestCase(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "tag_data.json")
        self.store = TagStore(self.path)

    def tearDown(self):
        self.directory.cleanup()


class FormattingTest(unittest.TestCase):

    def test_relative_time(self):
        self.assertEqual(relative_time(NOW - 10, now=NOW), "právě teď")
        self.assertEqual(relative_time(NOW - 5 * 60, now=NOW), "před 5 min")
        self.assertEqual(relative_time(NOW - 3 * 3600, now=NOW), "před 3 h")
        self.assertEqual(relative_time(NOW - 30 * 3600, now=NOW), "včera")
        self.assertEqual(relative_time(NOW - 4 * 86400, now=NOW), "před 4 dny")
        self.assertEqual(relative_time(None), "nikdy")

    def test_plural(self):
        self.assertEqual(plural(1, "tag", "tagy", "tagů"), "1 tag")
        self.assertEqual(plural(3, "tag", "tagy", "tagů"), "3 tagy")
        self.assertEqual(plural(0, "tag", "tagy", "tagů"), "0 tagů")
        self.assertEqual(plural(12, "tag", "tagy", "tagů"), "12 tagů")

    def test_normalize_removes_diacritics(self):
        self.assertEqual(normalize("  Klíče od AUTA "), "klice od auta")

    def test_distance(self):
        # Prague Old Town Square -> Prague Castle is roughly 1.5 km in a straight line
        meters = distance_m(50.0875, 14.4213, 50.0911, 14.4016)
        self.assertTrue(1300 < meters < 1700, meters)

    def test_describe_location(self):
        self.assertEqual(describe_location(record(1, 50.123456, 14.5)), "50.12346, 14.50000 ±12 m")
        self.assertEqual(describe_location(record(1, name="Domov")), "Domov")


class TagStoreTest(StoreTestCase):

    def test_meta_is_saved_and_reloaded(self):
        self.store.update_meta("id-keys", alias="Klíčky", favorite=True, group="Auto")
        reloaded = TagStore(self.path)
        meta = reloaded.get_meta("id-keys")
        self.assertEqual((meta.alias, meta.favorite, meta.group), ("Klíčky", True, "Auto"))
        self.assertEqual(reloaded.groups(), ["Auto"])

    def test_unknown_meta_field_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.update_meta("id-keys", colour="red")

    def test_history_deduplicates_and_sorts_newest_first(self):
        first = [record(60), record(10)]
        self.assertEqual(self.store.add_locations("id-keys", first), 2)
        self.assertEqual(self.store.add_locations("id-keys", [record(10), record(5)]), 1)

        times = [item.time for item in self.store.history("id-keys")]
        self.assertEqual(times, sorted(times, reverse=True))
        self.assertEqual(len(times), 3)
        self.assertEqual(self.store.last_location("id-keys").time, NOW - 300)

    def test_last_location_with_coordinates_skips_semantic(self):
        self.store.add_locations("id-keys", [record(1, name="Domov"), record(20)])
        self.assertEqual(self.store.last_location("id-keys").name, "Domov")
        self.assertEqual(self.store.last_location("id-keys", with_coordinates=True).time, NOW - 1200)

    def test_history_is_capped(self):
        many = [record(minute) for minute in range(MAX_HISTORY_PER_TAG + 20)]
        self.store.add_locations("id-keys", many)
        self.assertEqual(len(self.store.history("id-keys")), MAX_HISTORY_PER_TAG)
        self.assertEqual(self.store.history("id-keys")[0].time, NOW)

    def test_clear_history(self):
        self.store.add_locations("id-keys", [record(1), record(2)])
        self.assertEqual(self.store.clear_history("id-keys"), 2)
        self.assertEqual(self.store.history("id-keys"), [])

    def test_broken_file_is_backed_up(self):
        with open(self.path, "w", encoding="utf-8") as file:
            file.write("{ not json")
        store = TagStore(self.path)
        self.assertIsNotNone(store.load_warning)
        self.assertEqual(store.history("id-keys"), [])
        self.assertTrue(any(name.startswith("tag_data.json.broken-") for name in os.listdir(self.directory.name)))


class CatalogTest(StoreTestCase):

    def test_hidden_tags_and_search_without_diacritics(self):
        self.store.update_meta("id-bag", hidden=True)
        names = [view.name for view in build_views(self.store, sample_tags())]
        self.assertNotIn("Batoh", names)
        self.assertIn("Batoh", [view.name for view in build_views(self.store, sample_tags(), include_hidden=True)])

        found = build_views(self.store, sample_tags(), filter_text="klice")
        self.assertEqual([view.name for view in found], ["Klíče"])
        # Search also covers type, manufacturer and note
        self.assertEqual([view.name for view in build_views(self.store, sample_tags(), filter_text="chipolo")], ["Klíče"])

    def test_sort_modes(self):
        self.store.update_meta("id-bike", favorite=True)
        self.store.add_locations("id-bag", [record(1)])
        self.store.update_meta("id-keys", group="Auto")

        def names(mode):
            return [view.name for view in build_views(self.store, sample_tags(), sort_mode=mode)]

        self.assertEqual(names("favorite")[0], "Kolo")
        self.assertEqual(names("name"), ["Batoh", "Klíče", "Kolo"])
        self.assertEqual(names("last_seen")[0], "Batoh")
        self.assertEqual(names("group")[0], "Klíče")

    def test_alias_is_used_as_name_and_searchable(self):
        self.store.update_meta("id-bike", alias="Horské kolo")
        views = build_views(self.store, sample_tags(), sort_mode="name")
        self.assertIn("Horské kolo", [view.name for view in views])
        self.assertEqual([view.name for view in find_views(views, "horske")], ["Horské kolo"])

    def test_find_views(self):
        views = build_views(self.store, sample_tags(), sort_mode="name")
        self.assertEqual(find_views(views, "2")[0].name, "Klíče")
        self.assertEqual(find_views(views, "0"), [])
        self.assertEqual(find_views(views, "99"), [])
        self.assertEqual(find_views(views, "id-bike")[0].name, "Kolo")
        self.assertEqual(find_views(views, "KOLO")[0].name, "Kolo")
        # 'k' is in klíče, kolo and taška (the type of Batoh)
        self.assertEqual(len(find_views(views, "k")), 3)


class ExportTest(StoreTestCase):

    def test_csv_and_kml(self):
        records = [record(5, 50.1, 14.4), record(30, 50.2, 14.5), record(60, name="Domov")]
        csv_path = export.export_csv(records, os.path.join(self.directory.name, "out", "tag.csv"))
        kml_path = export.export_kml("Klíče & <spol>", records, os.path.join(self.directory.name, "out", "tag.kml"))

        with open(csv_path, encoding="utf-8-sig") as file:
            lines = file.read().splitlines()
        self.assertTrue(lines[0].startswith("cas,cas_unix,latitude,longitude"))
        self.assertEqual(len(lines), 4)
        self.assertIn("Domov", lines[3])

        root = ElementTree.parse(kml_path).getroot()
        namespace = {"k": "http://www.opengis.net/kml/2.2"}
        self.assertEqual(root.find("k:Document/k:name", namespace).text, "Klíče & <spol>")
        # Two points plus the line connecting them; the semantic location has no coordinates
        self.assertEqual(len(root.findall(".//k:Placemark", namespace)), 3)
        self.assertIsNotNone(root.find(".//k:LineString", namespace))

    def test_export_file_name_is_safe(self):
        path = export.export_file_path("Klíče / auto: 1", "csv", self.directory.name)
        self.assertTrue(os.path.basename(path).startswith("Klíče_auto_1_"))


class MenuTest(StoreTestCase):

    def run_menu(self, inputs, backend=None):
        backend = backend or FakeBackend(sample_tags())
        answers = iter(inputs)
        output = io.StringIO()
        opened = []

        def fake_input(prompt):
            output.write(prompt + "\n")
            try:
                return next(answers)
            except StopIteration:
                raise EOFError

        menu = TagMenu(backend, self.store, Console(fake_input, output, ansi=False),
                       open_url=lambda url: opened.append(url) or True,
                       export_dir=os.path.join(self.directory.name, "exports"))
        menu.run()
        return output.getvalue(), backend, opened

    def test_quit(self):
        output, _, _ = self.run_menu(["q"])
        self.assertIn("Klíče", output)
        self.assertIn("Na shledanou", output)

    def test_closed_input_ends_cleanly(self):
        output, _, _ = self.run_menu([])
        self.assertIn("Na shledanou", output)

    def test_invalid_numbers_do_not_crash(self):
        # '0' used to select the last tag, letters used to crash with ValueError
        output, backend, _ = self.run_menu(["0", "99", "n 0", "xyz", "q"])
        self.assertIn("v seznamu není", output)
        self.assertIn("Neznámý příkaz", output)
        self.assertNotIn(("locate", "id-bike"), backend.calls)

    def test_manage_tag_in_detail(self):
        # Sorted by name: 1 Batoh, 2 Klíče, 3 Kolo. Open 2, set alias, group, note, favorite, hide.
        self.store.set_setting("sort", "name")
        inputs = ["2", "j", "Klíčky od auta", "", "g", "Auto", "", "k", "visí na háčku", "", "f", "s", "", "q"]
        self.run_menu(inputs)

        meta = self.store.get_meta("id-keys")
        self.assertEqual(meta.alias, "Klíčky od auta")
        self.assertEqual(meta.group, "Auto")
        self.assertEqual(meta.note, "visí na háčku")
        self.assertTrue(meta.favorite)
        self.assertTrue(meta.hidden)

    def test_clear_alias_with_dash(self):
        self.store.update_meta("id-keys", alias="Staré")
        self.store.set_setting("sort", "name")
        # The alias is the displayed name, so the order is Batoh, Kolo, Staré
        self.run_menu(["3", "j", "-", "", "", "q"])
        self.assertEqual(self.store.get_meta("id-keys").alias, "")

    def test_choose_existing_group_by_number(self):
        self.store.update_meta("id-bag", group="Výlety")
        self.store.set_setting("sort", "name")
        self.run_menu(["3", "g", "1", "", "", "q"])
        self.assertEqual(self.store.get_meta("id-bike").group, "Výlety")

    def test_locate_saves_history_and_shows_link(self):
        backend = FakeBackend(sample_tags(), {"id-keys": [record(3, 50.1, 14.4), record(90, 50.2, 14.5)]})
        self.store.set_setting("sort", "name")
        output, backend, _ = self.run_menu(["n 2", "", "q"], backend)

        self.assertIn(("locate", "id-keys"), backend.calls)
        self.assertEqual(len(self.store.history("id-keys")), 2)
        self.assertIn("https://www.google.com/maps/search/?api=1&query=50.1,14.4", output)
        # The main list now shows when the tag was seen
        self.assertIn("před 3 min", output)

    def test_locate_reports_movement(self):
        self.store.add_locations("id-keys", [record(120, 50.0, 14.0)])
        backend = FakeBackend(sample_tags(), {"id-keys": [record(1, 50.0, 14.1)]})
        self.store.set_setting("sort", "name")
        output, _, _ = self.run_menu(["n2", "", "q"], backend)
        self.assertIn("přesunul o 7,1 km", output)

    def test_locate_error_returns_to_menu(self):
        backend = FakeBackend(sample_tags(), {"id-keys": LocationTimeoutError("No response")})
        self.store.set_setting("sort", "name")
        output, _, _ = self.run_menu(["n 2", "", "q"], backend)
        self.assertIn("Tag neodpověděl včas", output)
        self.assertIn("Na shledanou", output)

    def test_locate_all_continues_after_error(self):
        backend = FakeBackend(sample_tags(), {
            "id-keys": [record(3)],
            "id-bag": LocationTimeoutError("No response"),
            "id-bike": [record(8, 49.0, 16.0)],
        })
        output, backend, _ = self.run_menu(["v", "", "", "q"], backend)
        self.assertEqual(len([call for call in backend.calls if call[0] == "locate"]), 3)
        self.assertIn("nenalezen", output)
        self.assertEqual(len(self.store.history("id-bike")), 1)

    def test_play_sound_and_stop(self):
        self.store.set_setting("sort", "name")
        _, backend, _ = self.run_menu(["p 3", "", "", "q"])
        self.assertEqual(backend.calls[-2:], [("start_sound", "id-bike"), ("stop_sound", "id-bike")])

    def test_search_opens_single_match_and_filters_multiple(self):
        output, _, _ = self.run_menu(["klice", "", "k", "q"])
        self.assertIn("Název v Google:", output)
        # 'k' matches Klíče and Kolo -> becomes a filter
        self.assertIn("Filtr: „k“", output)

    def test_filter_and_clear(self):
        output, _, _ = self.run_menu(["h", "batoh", "h", "", "q"])
        self.assertIn("Filtr: „batoh“", output)

    def test_hidden_tags_toggle(self):
        self.store.update_meta("id-bag", hidden=True)
        output, _, _ = self.run_menu(["z", "q"])
        self.assertIn("+ 1 skrytý", output)
        self.assertIn("Batoh (skrytý)", output)
        self.assertTrue(self.store.get_setting("show_hidden"))

    def test_sort_is_remembered(self):
        self.run_menu(["s", "q"])
        self.assertEqual(TagStore(self.path).get_setting("sort"), "name")

    def test_history_export_and_map(self):
        self.store.add_locations("id-keys", [record(5, 50.1, 14.4), record(50, 50.2, 14.5)])
        self.store.set_setting("sort", "name")
        output, _, opened = self.run_menu(["2", "h", "", "e", "o", "", "m", "", "", "q"])

        self.assertIn("Historie poloh – Klíče (2 záznamy", output)
        export_dir = os.path.join(self.directory.name, "exports")
        self.assertEqual(sorted(name.rsplit(".", 1)[1] for name in os.listdir(export_dir)), ["csv", "kml"])
        self.assertEqual(opened, ["https://www.google.com/maps/search/?api=1&query=50.1,14.4"])

    def test_clear_history_needs_confirmation(self):
        self.store.add_locations("id-keys", [record(5)])
        self.store.set_setting("sort", "name")
        self.run_menu(["2", "x", "", "", "x", "a", "", "", "q"])
        self.assertEqual(self.store.history("id-keys"), [])

    def test_failed_loading_can_be_retried(self):
        class FlakyBackend(FakeBackend):
            def list_tags(self):
                self.calls.append(("list",))
                if len(self.calls) == 1:
                    raise ConnectionError("offline")
                return list(self.tags)

        output, backend, _ = self.run_menu(["", "q"], FlakyBackend(sample_tags()))
        self.assertIn("Nepodařilo se spojit s Googlem", output)
        self.assertIn("Klíče", output)

    def test_register_reloads_list(self):
        _, backend, _ = self.run_menu(["r", "a", "", "q"])
        self.assertIn(("register",), backend.calls)
        self.assertEqual(backend.calls.count(("list",)), 2)

    def test_friendly_error_keeps_detail(self):
        self.assertIn("No response", friendly_error(LocationTimeoutError("No response")))
        self.assertEqual(friendly_error(ValueError("boom")), "boom")


class CliTest(StoreTestCase):

    def test_list_json(self):
        self.store.update_meta("id-keys", favorite=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.list_command(FakeBackend(sample_tags()), self.store, "favorite", as_json=True)
        data = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(data[0]["name"], "Klíče")
        self.assertEqual(data[0]["type"], "klíče")

    def test_locate_json_and_ambiguous_name(self):
        backend = FakeBackend(sample_tags(), {"id-bike": [record(2, 49.0, 16.0)]})
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.locate_command(backend, self.store, "k", "name", 5, as_json=True), 2)
            self.assertEqual(cli.locate_command(backend, self.store, "kolo", "name", 5, as_json=True), 0)

        data = json.loads(output.getvalue())
        self.assertEqual(data["tag"]["name"], "Kolo")
        self.assertEqual(data["locations"][0]["latitude"], 49.0)
        self.assertIsNotNone(data["tag"]["last_seen"])


if __name__ == "__main__":
    unittest.main()
