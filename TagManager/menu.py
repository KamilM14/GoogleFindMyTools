#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import re
import webbrowser

from TagManager import export
from TagManager.catalog import SORT_MODES, SORT_LABELS, DEFAULT_SORT, TagView, build_view, build_views, find_views
from TagManager.console import Console, truncate
from TagManager.formatting import (
    describe_location, device_type_label, distance_m, format_date, format_datetime,
    format_distance, maps_link, plural, relative_time, status_label,
)

DEFAULT_TIMEOUT_SECONDS = 60
HISTORY_ROWS = 30

# Known errors explained in plain words; matched by class name so this module does not import the network code
FRIENDLY_ERRORS = {
    "LocationTimeoutError": "Tag neodpověděl včas. Nejspíš je teď mimo dosah sítě Najdi moje zařízení – zkus to později.",
    "TokenRetrievalError": "Přihlášení ke Googlu vypršelo. Smaž soubor Auth/secrets.json a spusť program znovu.",
    "NovaRequestError": "Google odmítl požadavek.",
    "SpotRequestError": "Google odmítl požadavek.",
    "ConnectionError": "Nepodařilo se spojit s Googlem. Zkontroluj připojení k internetu.",
    "ConnectTimeout": "Nepodařilo se spojit s Googlem. Zkontroluj připojení k internetu.",
    "ReadTimeout": "Google neodpověděl včas. Zkus to znovu.",
    "IdentityKeyError": "Klíč tohoto tagu nejde dešifrovat.",
}


def friendly_error(error: Exception) -> str:
    detail = str(error).strip()
    for cls in type(error).__mro__:
        if cls.__name__ in FRIENDLY_ERRORS:
            message = FRIENDLY_ERRORS[cls.__name__]
            return f"{message}\n  ({detail})" if detail else message
    return detail or type(error).__name__


class TagMenu:

    def __init__(self, backend, store, console: Console = None, timeout: int = DEFAULT_TIMEOUT_SECONDS,
                 open_url=webbrowser.open, export_dir: str = export.DEFAULT_EXPORT_DIR):
        self.backend = backend
        self.store = store
        self.console = console or Console()
        self.timeout = timeout
        self.open_url = open_url
        self.export_dir = export_dir
        self.tags = []
        self.filter_text = ""
        self._visible = []
        self._flash = []

    # --- settings remembered between runs --------------------------------------------

    @property
    def sort_mode(self) -> str:
        mode = self.store.get_setting("sort", DEFAULT_SORT)
        return mode if mode in SORT_LABELS else DEFAULT_SORT

    @property
    def show_hidden(self) -> bool:
        return bool(self.store.get_setting("show_hidden", False))

    # --- main loop -----------------------------------------------------------------------

    def run(self) -> None:
        if self.store.load_warning:
            self.flash("warning", self.store.load_warning)

        try:
            if not self.load_tags():
                return

            while True:
                self.render_main()
                choice = self.console.ask("Volba (? = nápověda):")
                if self.handle_main(choice) is False:
                    break
        except KeyboardInterrupt:
            self.console.print("")

        self.console.print("Na shledanou!")

    def load_tags(self) -> bool:
        while True:
            self.console.info("Načítám seznam tagů z Google…")
            try:
                self.tags = self.backend.list_tags()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                self.console.error("Seznam tagů se nepodařilo načíst: " + friendly_error(e))
                if self.console.confirm("Zkusit to znovu?", default=True):
                    continue
                return False

            for tag in self.tags:
                self.store.remember_name(tag.canonic_id, tag.google_name)
            return True

    def flash(self, kind: str, text: str) -> None:
        """A message shown once above the menu on the next screen."""
        self._flash.append((kind, text))

    def _show_flash(self) -> None:
        for kind, text in self._flash:
            getattr(self.console, kind)(text)
        self._flash = []

    def _run_action(self, action, *args, pause: bool = True):
        """Runs one menu action. Errors and Ctrl+C return to the menu instead of ending the program."""
        try:
            return action(*args)
        except KeyboardInterrupt:
            self.console.print("")
            self.console.warning("Přerušeno.")
        except Exception as e:
            self.console.error("Chyba: " + friendly_error(e))
        finally:
            if pause:
                try:
                    self.console.pause()
                except KeyboardInterrupt:
                    pass
        return None

    # --- main screen -------------------------------------------------------------------------

    def visible_views(self) -> list:
        return build_views(self.store, self.tags, self.show_hidden, self.filter_text, self.sort_mode)

    def render_main(self) -> None:
        c = self.console
        self._visible = self.visible_views()
        hidden_count = sum(1 for tag in self.tags if self.store.get_meta(tag.canonic_id).hidden)

        c.clear()
        c.title("GoogleFindMyTools · správa tagů", plural(len(self.tags), "tag", "tagy", "tagů"))

        if self.filter_text:
            c.print(c.yellow(f" Filtr: „{self.filter_text}“") + c.dim("  (h a Enter = zrušit filtr)"))

        c.print("")
        if self._visible:
            self._print_tag_table(self._visible)
        elif self.tags:
            c.warning(" Žádný tag neodpovídá filtru." if self.filter_text else " Všechny tagy jsou skryté (z = zobrazit).")
        else:
            c.warning(" Na tomto účtu nejsou žádné tagy. Přidej tag v aplikaci Najdi moje zařízení, nebo zaregistruj vlastní (r).")

        if hidden_count and not self.show_hidden:
            c.print(c.dim(f" + {plural(hidden_count, 'skrytý', 'skryté', 'skrytých')} (z = zobrazit)"))

        c.print("")
        c.menu([
            ("číslo", "detail a správa tagu"),
            ("n č", "najít polohu tagu"),
            ("p č", "pípnout (přehrát zvuk)"),
            ("h", "hledat / filtrovat"),
            ("v", "najít polohu všech zobrazených"),
            ("s", "řazení: " + SORT_LABELS[self.sort_mode]),
            ("z", "schovat skryté" if self.show_hidden else "zobrazit skryté"),
            ("o", "obnovit seznam z Google"),
            ("r", "registrovat vlastní tracker"),
            ("?", "nápověda"),
            ("q", "konec"),
        ])
        c.print("")
        self._show_flash()

    def _print_tag_table(self, views) -> None:
        c = self.console
        show_group = any(view.meta.group for view in views)

        headers = ["#", "", "Název", "Typ"] + (["Skupina"] if show_group else []) + ["Naposledy viděn", "Kde"]
        rows = []
        for number, view in enumerate(views, start=1):
            name = truncate(view.name, 24)
            if view.meta.hidden:
                name = c.dim(name + " (skrytý)")
            elif view.meta.favorite:
                name = c.bold(name)

            last = view.last_seen
            row = [
                str(number),
                c.yellow("*") if view.meta.favorite else "",
                name,
                truncate(device_type_label(view.info.device_type), 12),
            ]
            if show_group:
                row.append(truncate(view.meta.group, 14))
            row.append(relative_time(last.time) if last else c.dim("—"))
            row.append(truncate(describe_location(last), 32) if last else "")
            rows.append(row)

        c.table(headers, rows, align=[">", "<", "<", "<"] + (["<"] if show_group else []) + ["<", "<"])

    def handle_main(self, choice: str):
        """Handles one input on the main screen. Returns False to quit."""
        text = choice.strip()
        lowered = text.lower()

        if not text:
            return True
        if lowered in ("q", "konec", "exit", "quit"):
            return False
        if text.isdigit():
            view = self._view_by_number(text)
            if view:
                self.tag_detail(view)
            return True

        action = re.fullmatch(r"([np])\s*(\d*)", lowered)
        if action:
            number = action.group(2) or self.console.ask("Číslo tagu:")
            view = self._view_by_number(number)
            if view:
                if action.group(1) == "n":
                    self._run_action(self.locate, view)
                else:
                    self._run_action(self.play_sound, view)
            return True

        if lowered == "h" or lowered.startswith("h ") or text.startswith("/"):
            query = text[1:].strip()
            if not query and lowered == "h":
                query = self.console.ask("Hledat (název, přezdívka, skupina, poznámka, typ; Enter = zrušit filtr):")
            self.filter_text = query
            return True
        if lowered == "s":
            keys = [key for key, _ in SORT_MODES]
            next_mode = keys[(keys.index(self.sort_mode) + 1) % len(keys)]
            self.store.set_setting("sort", next_mode)
            self.flash("info", "Řazení: " + SORT_LABELS[next_mode])
            return True
        if lowered == "z":
            self.store.set_setting("show_hidden", not self.show_hidden)
            return True
        if lowered == "v":
            self._run_action(self.locate_all, list(self._visible))
            return True
        if lowered == "o":
            self._run_action(self.load_tags, pause=False)
            return True
        if lowered == "r":
            self._run_action(self.register_tracker)
            return True
        if lowered in ("?", "help", "napoveda", "nápověda"):
            self.show_help()
            return True

        # Anything else is a search: one match opens the tag directly, more matches become a filter
        matches = find_views(self._visible, text)
        if len(matches) == 1:
            self.tag_detail(matches[0])
        elif matches:
            self.filter_text = text
        else:
            self.flash("warning", f"Neznámý příkaz ani tag: „{text}“. Nápovědu zobrazíš klávesou ?")
        return True

    def _view_by_number(self, number: str):
        number = number.strip()
        if number.isdigit() and 1 <= int(number) <= len(self._visible):
            return self._visible[int(number) - 1]
        if self._visible:
            self.flash("warning", f"Tag číslo „{number}“ v seznamu není. Zadej číslo 1–{len(self._visible)}.")
        else:
            self.flash("warning", "Seznam je prázdný.")
        return None

    # --- tag detail -----------------------------------------------------------------------------

    def tag_detail(self, view: TagView) -> None:
        while True:
            # Reload, the local data may have changed
            view = build_view(self.store, view.info)
            self.render_detail(view)

            choice = self.console.ask("Volba (Enter = zpět na seznam):").lower()
            if choice in ("", "b", "q", "zpet", "zpět"):
                return

            actions = {
                "n": self.locate,
                "p": self.play_sound,
                "t": self.stop_sound,
                "h": self.show_history,
                "e": self.export_history,
                "m": self.open_map,
                "j": self.rename,
                "g": self.set_group,
                "k": self.edit_note,
                "x": self.clear_history,
            }
            if choice in actions:
                self._run_action(actions[choice], view)
            elif choice == "f":
                meta = self.store.update_meta(view.canonic_id, favorite=not view.meta.favorite)
                self.flash("success", "Přidáno do oblíbených." if meta.favorite else "Odebráno z oblíbených.")
            elif choice == "s":
                meta = self.store.update_meta(view.canonic_id, hidden=not view.meta.hidden)
                self.flash("success", "Tag je skrytý v seznamu (z na hlavní obrazovce ho zase ukáže)." if meta.hidden else "Tag se znovu zobrazuje v seznamu.")
            else:
                self.flash("warning", f"Neznámá volba „{choice}“.")

    def render_detail(self, view: TagView) -> None:
        c = self.console
        info, meta, last = view.info, view.meta, view.last_seen

        c.clear()
        c.title(("* " if meta.favorite else "") + view.name, device_type_label(info.device_type))

        def line(label, value):
            c.print(f" {c.dim(label.ljust(18))}{value}")

        line("Název v Google:", info.google_name or "—")
        line("Přezdívka:", meta.alias or c.dim("— (j = nastavit)"))
        line("Skupina:", meta.group or c.dim("— (g = nastavit)"))
        line("Poznámka:", meta.note or c.dim("— (k = napsat)"))
        maker = " / ".join(part for part in (info.manufacturer, info.model) if part)
        line("Výrobce / model:", maker or "—")
        if info.pair_date:
            line("Spárováno:", format_date(info.pair_date))
        if info.is_mcu:
            line("Druh:", "vlastní tracker (ESP32/Zephyr)")
        if info.shared_with:
            shared = ", ".join(
                access.email + (" (vlastník)" if access.is_owner else "") + (" – ty" if access.this_account else "")
                for access in info.shared_with
            )
            line("Přístup mají:", shared)
        line("Stav v seznamu:", "skrytý" if meta.hidden else ("oblíbený" if meta.favorite else "běžný"))
        line("Canonic ID:", c.dim(info.canonic_id))

        c.print("")
        if last:
            line("Naposledy viděn:", f"{relative_time(last.time)} ({format_datetime(last.time)})")
            line("Kde:", describe_location(last))
            if last.has_coordinates:
                line("Mapa:", maps_link(last.latitude, last.longitude))
        else:
            line("Naposledy viděn:", c.dim("zatím nehledán (n = najít polohu)"))
        line("Historie poloh:", plural(len(self.store.history(view.canonic_id)), "záznam", "záznamy", "záznamů"))

        c.print("")
        c.menu([
            ("n", "najít polohu teď"),
            ("h", "historie poloh"),
            ("p", "pípnout (přehrát zvuk)"),
            ("e", "export historie (CSV / KML)"),
            ("t", "zastavit zvuk"),
            ("m", "otevřít poslední polohu v mapě"),
            ("j", "přezdívka"),
            ("g", "skupina"),
            ("k", "poznámka"),
            ("f", "odebrat z oblíbených" if meta.favorite else "přidat do oblíbených"),
            ("s", "znovu zobrazovat v seznamu" if meta.hidden else "skrýt v seznamu"),
            ("x", "smazat historii poloh"),
        ])
        c.print("")
        self._show_flash()

    # --- actions ------------------------------------------------------------------------------------

    def locate(self, view: TagView):
        c = self.console
        previous = self.store.last_location(view.canonic_id, with_coordinates=True)

        c.info(f"Hledám polohu tagu {view.name}… (nejvýš {self.timeout} s, Ctrl+C = zrušit)")
        records = self.backend.locate(view.canonic_id, self.timeout)
        added = self.store.add_locations(view.canonic_id, records)

        if not records:
            c.warning("Google o poloze tohoto tagu zatím nic neví (žádná hlášení).")
            return records

        c.success(f"Nalezeno poloh: {len(records)}" + (f", nových v historii: {added}" if added else ", vše už bylo v historii"))
        c.print("")
        self._print_location_table(records[:10])

        newest = next((record for record in records if record.has_coordinates), None)
        if newest:
            c.print("")
            c.print(" Mapa: " + c.cyan(maps_link(newest.latitude, newest.longitude)))
            if previous and previous.time < newest.time:
                moved = distance_m(previous.latitude, previous.longitude, newest.latitude, newest.longitude)
                c.print(f" Od předchozí známé polohy ({relative_time(previous.time)}) se přesunul o {format_distance(moved)}.")
        return records

    def locate_all(self, views):
        c = self.console
        if not views:
            c.warning("Seznam je prázdný – není co hledat.")
            return
        if len(views) > 1 and not c.confirm(f"Najít polohu {len(views)} tagů? Každý může trvat až {self.timeout} s.", default=True):
            return

        results = []
        for number, view in enumerate(views, start=1):
            c.info(f"[{number}/{len(views)}] {view.name}…")
            try:
                records = self.backend.locate(view.canonic_id, self.timeout)
                self.store.add_locations(view.canonic_id, records)
                newest = next((record for record in records if record.has_coordinates), records[0] if records else None)
                results.append((view, newest, None if newest else "žádná hlášení"))
            except KeyboardInterrupt:
                c.warning("Přerušeno – zbývající tagy přeskočeny.")
                break
            except Exception as e:
                results.append((view, None, friendly_error(e).splitlines()[0]))

        c.print("")
        rows = []
        for view, newest, error in results:
            if newest:
                rows.append([view.name, relative_time(newest.time), describe_location(newest)])
            else:
                rows.append([view.name, c.red("nenalezen"), c.dim(error or "")])
        c.table(["Tag", "Kdy", "Kde / proč ne"], rows)

    def play_sound(self, view: TagView):
        c = self.console
        self.backend.start_sound(view.canonic_id)
        c.success(f"Požadavek odeslán – {view.name} by měl začít pípat.")
        c.print(c.dim(" Tag pípá jen v dosahu Bluetooth některého tvého telefonu s Androidem a přihlášeným účtem."))
        if c.confirm("Až ho najdeš, potvrď a zvuk se vypne. Vypnout zvuk?", default=True):
            self.backend.stop_sound(view.canonic_id)
            c.success("Zvuk vypnut.")

    def stop_sound(self, view: TagView):
        self.backend.stop_sound(view.canonic_id)
        self.console.success("Požadavek na vypnutí zvuku odeslán.")

    def show_history(self, view: TagView):
        c = self.console
        records = self.store.history(view.canonic_id)
        if not records:
            c.warning("Historie je prázdná. Polohy se ukládají při každém hledání (n).")
            return

        c.section(f"Historie poloh – {view.name} ({plural(len(records), 'záznam', 'záznamy', 'záznamů')}, nejnovější nahoře)")
        self._print_location_table(records[:HISTORY_ROWS], with_movement=True, all_records=records)
        if len(records) > HISTORY_ROWS:
            c.print(c.dim(f" … a dalších {len(records) - HISTORY_ROWS} starších. Celou historii uložíš exportem (e)."))

    def _print_location_table(self, records, with_movement: bool = False, all_records=None) -> None:
        all_records = all_records or records
        headers = ["#", "Kdy", "Před", "Kde", "Zdroj"] + (["Posun"] if with_movement else [])
        rows = []
        for index, record in enumerate(records):
            row = [
                str(index + 1),
                format_datetime(record.time),
                relative_time(record.time),
                describe_location(record),
                status_label(record.status, record.is_own_report),
            ]
            if with_movement:
                older = next((item for item in all_records[index + 1:] if item.has_coordinates), None)
                if record.has_coordinates and older:
                    row.append(format_distance(distance_m(older.latitude, older.longitude, record.latitude, record.longitude)))
                else:
                    row.append("")
            rows.append(row)
        self.console.table(headers, rows, align=[">", "<", "<", "<", "<"] + ([">"] if with_movement else []))

    def export_history(self, view: TagView):
        c = self.console
        records = self.store.history(view.canonic_id)
        if not records:
            c.warning("Historie je prázdná, není co exportovat. Nejdřív najdi polohu (n).")
            return

        choice = c.ask("Formát: c = CSV (Excel, Moje mapy), k = KML (Google Earth, Moje mapy), o = oba:").lower()
        formats = {"c": ["csv"], "k": ["kml"], "o": ["csv", "kml"]}.get(choice)
        if not formats:
            c.warning("Export zrušen.")
            return

        for extension in formats:
            path = export.export_file_path(view.name, extension, self.export_dir)
            if extension == "csv":
                export.export_csv(records, path)
            else:
                export.export_kml(view.name, records, path)
            c.success(f"Uloženo: {path}")

    def open_map(self, view: TagView):
        last = self.store.last_location(view.canonic_id, with_coordinates=True)
        if not last:
            self.console.warning("Poloha zatím není známá. Nejdřív ji najdi (n).")
            return
        link = maps_link(last.latitude, last.longitude)
        self.console.print(f"Otevírám {link}")
        if not self.open_url(link):
            self.console.warning("Prohlížeč se nepodařilo otevřít, zkopíruj si odkaz výše.")

    def rename(self, view: TagView):
        c = self.console
        c.print(c.dim(f" Přezdívka se ukládá jen v tomto programu, v Google zůstane název „{view.info.google_name}“."))
        value = self._ask_text("Nová přezdívka", view.meta.alias)
        if value is not None:
            self.store.update_meta(view.canonic_id, alias=value)
            c.success(f"Přezdívka nastavena: {value}" if value else "Přezdívka smazána, používá se název z Google.")

    def set_group(self, view: TagView):
        c = self.console
        groups = self.store.groups()
        if groups:
            c.print(" Existující skupiny: " + ", ".join(f"{c.yellow(str(i))} {name}" for i, name in enumerate(groups, start=1)))
        value = self._ask_text("Skupina (číslo existující nebo nový název)", view.meta.group)
        if value is None:
            return
        if value.isdigit() and 1 <= int(value) <= len(groups):
            value = groups[int(value) - 1]
        self.store.update_meta(view.canonic_id, group=value)
        c.success(f"Skupina: {value}" if value else "Tag už není v žádné skupině.")

    def edit_note(self, view: TagView):
        value = self._ask_text("Poznámka", view.meta.note)
        if value is not None:
            self.store.update_meta(view.canonic_id, note=value)
            self.console.success("Poznámka uložena." if value else "Poznámka smazána.")

    def _ask_text(self, label: str, current: str):
        """Returns the new text, '' to clear it, or None to keep the current value."""
        hint = f"Enter = ponechat „{current}“, - = smazat" if current else "Enter = nechat prázdné"
        value = self.console.ask(f"{label} ({hint}):")
        if value == "-":
            return ""
        return value or None

    def clear_history(self, view: TagView):
        c = self.console
        count = len(self.store.history(view.canonic_id))
        if not count:
            c.warning("Historie už je prázdná.")
            return
        if c.confirm(f"Opravdu smazat {count} uložených poloh tagu {view.name}?", default=False):
            self.store.clear_history(view.canonic_id)
            c.success("Historie smazána.")

    def register_tracker(self):
        c = self.console
        c.print("Zaregistruje nový vlastní tracker (ESP32 nebo Zephyr) do tvého účtu Google.")
        c.print(c.dim("Pak budeš potřebovat zobrazený Advertisement Key – nahraješ ho do firmwaru (viz ESP32Firmware/README.md)."))
        if not c.confirm("Pokračovat?", default=False):
            return
        self.backend.register_tracker()
        self.load_tags()

    def show_help(self) -> None:
        c = self.console
        c.clear()
        c.title("Nápověda")
        c.print("""
 Hlavní obrazovka
   3            otevře tag číslo 3 – detail, hledání, zvuk a správa
   n 3 / p 3    rovnou najde polohu tagu 3 / rozpípá tag 3
   klíče        napiš část názvu – jeden výsledek se rovnou otevře,
                víc výsledků se zobrazí jako filtr (diakritika nevadí)
   h            hledat / filtrovat; h a Enter filtr zruší
   v            najde polohu všech tagů, které jsou právě vidět
   s            přepíná řazení (oblíbené, název, naposledy viděné, skupina)
   z            zobrazí / schová skryté tagy

 Správa tagu (v detailu)
   j  přezdívka   g  skupina   k  poznámka   f  oblíbený   s  skrýt
   Tyto údaje se ukládají jen u tebe (TagManager/tag_data.json),
   do Googlu se nic neposílá.

 Historie poloh
   Každé hledání uloží nalezené polohy. V detailu tagu je h (historie),
   e (export do CSV nebo KML pro Google Earth / Moje mapy) a m (mapa).

 Kdykoli
   Ctrl+C přeruší probíhající akci, q ukončí program.
""")
        try:
            c.pause()
        except KeyboardInterrupt:
            pass
