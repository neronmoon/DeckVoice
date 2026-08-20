#!/usr/bin/env python3
import os
import sys
import time
import json
import glob
from deckvoice.deck_hid import STEAM_DECK_BUTTON_BITS, raw_button_states

STATE_FILE = "/tmp/deckvoice_ptt"
PREVIEW_FILE = "/tmp/deckvoice_button_preview"
PID_FILE = "/tmp/deckvoice_listener.pid"
CONTROLLER_TYPE_FILE = "/tmp/deckvoice_controller_type"
CONFIG_DIR = os.environ.get(
    "DECKVOICE_CONFIG_DIR",
    os.path.expanduser("~/.config/deckvoice"),
)
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "button_config.json")

RAW_BUTTON_BITS = STEAM_DECK_BUTTON_BITS

STEAM_HID_INTERFACES = {
    "0003:000028DE:00001205": ("/input2",),
    "0003:000028DE:00001102": ("/input2",),
    "0003:000028DE:00001142": ("/input1", "/input2"),
}
STEAM_CONTROLLER_TYPES = {
    "0003:000028DE:00001205": "steam_deck",
    "0003:000028DE:00001102": "steam_controller_wired",
    "0003:000028DE:00001142": "steam_controller_wireless",
}


def write_button_preview(name, pressed):
    if pressed or name == "None":
        with open(PREVIEW_FILE, "w") as f:
            f.write(name if pressed else "None")
    print(f"Button preview: {name} {'pressed' if pressed else 'released'}", flush=True)


def load_button_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                buttons = config.get("buttons", ["L1", "R1"])
                if isinstance(buttons, list) and len(buttons) > 0:
                    return buttons
    except Exception as e:
        print(f"Error loading config: {e}, using defaults", flush=True)
    return ["L1", "R1"]


def find_steam_deck_hidraw():
    for path in glob.glob("/dev/hidraw*"):
        name = os.path.basename(path)
        uevent_path = f"/sys/class/hidraw/{name}/device/uevent"
        try:
            with open(uevent_path, "r") as f:
                properties = dict(
                    line.rstrip().split("=", 1)
                    for line in f
                    if "=" in line
                )
            hid_id = properties.get("HID_ID")
            interface_suffixes = STEAM_HID_INTERFACES.get(hid_id, ())
            if properties.get("HID_PHYS", "").endswith(interface_suffixes):
                with open(CONTROLLER_TYPE_FILE, "w") as controller_file:
                    controller_file.write(STEAM_CONTROLLER_TYPES[hid_id])
                return path
        except (OSError, ValueError):
            continue
    return None


def main():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    with open(STATE_FILE, "w") as f:
        f.write("0")
    write_button_preview("None", False)

    print(f"Controller listener starting (PID {os.getpid()})...", flush=True)

    button_names = load_button_config()
    button_info = []
    for btn_name in button_names:
        if btn_name not in RAW_BUTTON_BITS:
            print(f"ERROR: Invalid button: {btn_name}", flush=True)
            sys.exit(1)
        button_info.append({"name": btn_name, "pressed": False})

    combo_str = "+".join([btn["name"] for btn in button_info])
    print(f"Button combo: {combo_str}", flush=True)

    combo_active = False

    def update_combo():
        nonlocal combo_active
        all_pressed = all(btn["pressed"] for btn in button_info)
        if all_pressed and not combo_active:
            combo_active = True
            print(f"{combo_str} COMBO: pressed", flush=True)
            with open(STATE_FILE, "w") as f:
                f.write("1")
        elif not all_pressed and combo_active:
            combo_active = False
            print(f"{combo_str} COMBO: released", flush=True)
            with open(STATE_FILE, "w") as f:
                f.write("0")

    def listen_hidraw():
        previous_states = {name: False for name in RAW_BUTTON_BITS}
        while True:
            path = find_steam_deck_hidraw()
            if not path:
                print("Supported Valve raw HID interface not found; retrying...", flush=True)
                time.sleep(2)
                continue
            print(f"Listening for raw Valve controller controls on: {path}", flush=True)
            try:
                with open(path, "r+b", buffering=0) as device:
                    received_report = False
                    while True:
                        report = device.read(64)
                        if not report:
                            raise OSError("empty HID report")
                        if not received_report:
                            print(f"Received first raw HID report ({len(report)} bytes)", flush=True)
                            received_report = True
                        states = raw_button_states(report)
                        if states is None:
                            continue
                        for name in RAW_BUTTON_BITS:
                            pressed = states.get(name, False)
                            if pressed != previous_states[name]:
                                previous_states[name] = pressed
                                write_button_preview(name, pressed)
                        changed = False
                        for btn in button_info:
                            pressed = states.get(btn["name"], False)
                            if pressed != btn["pressed"]:
                                btn["pressed"] = pressed
                                changed = True
                        if changed:
                            update_combo()
            except (OSError, IOError) as e:
                print(f"Raw HID disconnected: {e}; retrying...", flush=True)
                for btn in button_info:
                    btn["pressed"] = False
                update_combo()
                time.sleep(1)

    try:
        listen_hidraw()
    except KeyboardInterrupt:
        pass
    finally:
        for path in (STATE_FILE, PID_FILE, PREVIEW_FILE, CONTROLLER_TYPE_FILE):
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    main()
