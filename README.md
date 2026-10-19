# GoogleFindMyTools

This repository includes some useful tools that reimplement parts of Google's Find My Device Network (now called Find Hub Network). Note that the code of this repo is still very experimental.

### What's possible?
Currently, it is possible to query Find My Device / Find Hub trackers and Android devices, read out their E2EE keys, and decrypt encrypted locations sent from the Find My Device / Find Hub network. You can also send register your own ESP32- or Zephyr-based trackers, as described below.

### How to use

> [!CAUTION]
> Before starting, ensure you have Chrome and Python updated.
> 
> **If Chrome is not up to date, the script will NOT work, guaranteed!**

- Clone this repository: `git clone` or download the ZIP file
- Change into the directory: `cd GoogleFindMyTools`
- Optional: Create venv: `python -m venv venv`
- Optional: Activate venv: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Linux & macOS)
- Install all required packages: `pip install -r requirements.txt`
- Install the latest version of Google Chrome: https://www.google.com/chrome/
- Start the program by running [main.py](main.py): `python main.py` or `python3 main.py`

### Správa tagů (interaktivní menu)

`python main.py` otevře přehledné menu se seznamem tagů (název, typ, skupina, kdy a kde byl naposledy viděn).

| Kde | Klávesa | Co udělá |
|---|---|---|
| seznam | `3` | otevře tag číslo 3 (detail, hledání, zvuk, správa) |
| seznam | `n 3` / `p 3` | rovnou najde polohu tagu 3 / rozpípá tag 3 |
| seznam | `klíče` | napsaná část názvu: jeden výsledek se otevře, víc se zobrazí jako filtr (diakritika nevadí) |
| seznam | `h` · `v` · `s` · `z` · `o` | hledat · najít polohu všech zobrazených · řazení · skryté tagy · obnovit seznam |
| detail | `n` · `p` / `t` · `h` · `e` · `m` | najít polohu · pípnout / ztišit · historie poloh · export CSV/KML · otevřít mapu |
| detail | `j` · `g` · `k` · `f` · `s` · `x` | přezdívka · skupina · poznámka · oblíbený · skrýt · smazat historii |

- Přezdívky, skupiny, poznámky, oblíbené, skryté tagy a **historie poloh** se ukládají jen lokálně do `TagManager/tag_data.json` (do Googlu se nic neposílá, soubor je v `.gitignore`).
- Každé hledání uloží nalezené polohy do historie; v seznamu je pak vidět „naposledy viděn“ a po dalším hledání i o kolik se tag přesunul.
- Export historie do `exports/`: CSV (Excel, Moje mapy) a KML (Google Earth, Moje mapy – body i trasa).
- Hledání polohy má časový limit (výchozí 60 s, `--timeout`), Ctrl+C přeruší jen probíhající akci.

Bez menu (např. pro skripty nebo Kasandru):

```
python main.py --list [--json]
python main.py --locate "klíče" [--json] [--timeout 90]
python main.py --classic          # původní jednoduché menu
```

Testy menu a správy tagů (bez sítě a bez přihlášení): `python -m unittest discover -s tests -t .`

### Authentication

On the first run, an authentication sequence is executed, which requires a computer with access to Google Chrome.

The authentication results are stored in `Auth/secrets.json`. If you intend to run this tool on a headless machine, you can just copy this file to avoid having to use Chrome.

### Known Issues
- "Your encryption data is locked on your device" is shown if you have never set up Find My Device on an Android device. Solution: Login with your Google Account on an Android device, go to Settings > Google > All Services > Find My Device > Find your offline devices > enable "With network in all areas" or "With network in high-traffic areas only". If "Find your offline devices" is not shown in Settings, you will need to download the Find My Device app from Google's Play Store, and pair a real Find My Device tracker with your device to force-enable the Find My Device network.
- No support for trackers using the P-256 curve and 32-Byte advertisements. Regular trackers don't seem to use this curve at all - I can only confirm that it is used with Sony's WH1000XM5 headphones.
- No support for the authentication process on ARM Linux
- If you receive "ssl.SSLCertVerificationError" when running the script, try to follow [this answer](https://stackoverflow.com/a/53310545).
- Please also consider the issues listed in the [README in the ESP32Firmware folder](ESP32Firmware/README.md) if you want to register custom trackers.

### Firmware for custom ESP32-based trackers
If you want to use an ESP32 as a custom Find My Device tracker, you can find the firmware in the folder ESP32Firmware. To register a new tracker, run main.py and press 'r' if you are asked to. Afterward, follow the instructions on-screen.

For more information, check the [README in the ESP32Firmware folder](ESP32Firmware/README.md).

### Firmware for custom Zephyr-based trackers
If you want to use a Zephyr-supported BLE device (e.g. nRF51/52) as a custom Find My Device tracker, you can find the firmware in the folder ZephyrFirmware. To register a new tracker, run main.py and press 'r' if you are asked to. Afterward, follow the instructions on-screen.

For more information, check the [README in the ZephyrFirmware folder](ZephyrFirmware/README.md).

### iOS App
You can also use my [iOS App](https://testflight.apple.com/join/rGqa2mTe) to access your Find My Device trackers on the go.
