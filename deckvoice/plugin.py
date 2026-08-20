import json
import logging
import os
import shutil
import subprocess
import threading
import time
import traceback

try:
    import certifi
    CA_FILE = certifi.where()
except ImportError:
    CA_FILE = None

try:
    import decky
except ImportError:
    import decky_plugin as decky

from deckvoice.voice_service import (
    WHISPER_LANGUAGE_NAMES,
    WHISPER_LANGUAGES,
    WHISPER_MODELS,
    YDOTOOL_SOCKET,
    VoiceService,
)

logger = logging.getLogger()
plugin_path = os.environ["DECKY_PLUGIN_DIR"]

decky_user_home = getattr(decky, "DECKY_USER_HOME", "/home/deck")
CONFIG_DIR = getattr(
    decky,
    "DECKY_SETTINGS_DIR",
    os.path.join(decky_user_home, "homebrew", "settings", "DeckVoice"),
)
os.makedirs(CONFIG_DIR, exist_ok=True)
BUTTON_CONFIG_FILE = os.path.join(CONFIG_DIR, "button_config.json")
MODELS_DIR = os.path.join(CONFIG_DIR, "models")

STATE_FILE = "/tmp/deckvoice_ptt"
PREVIEW_FILE = "/tmp/deckvoice_button_preview"
PID_FILE = "/tmp/deckvoice_listener.pid"
CONTROLLER_TYPE_FILE = "/tmp/deckvoice_controller_type"

PRESETS_FILE = os.path.join(plugin_path, "game_presets.json")
if not os.path.exists(PRESETS_FILE):
    PRESETS_FILE = os.path.join(plugin_path, "defaults", "game_presets.json")

_game_presets = {}
try:
    with open(PRESETS_FILE, "r") as f:
        _game_presets = json.load(f)
except Exception as e:
    logger.error("Failed to load game presets: %s", e)

DEFAULT_CONFIG = {
    "buttons": ["L1", "R1"],
    "enabled": False,
    "game": "wow",
    "whisperModel": "base",
    "whisperLanguage": "auto",
}


class Plugin:
    voice_service = None
    listener_process = None
    ydotoold_process = None
    ydotoold_ready = False
    poll_thread = None
    poll_running = False
    controller_enabled = False
    recording_start_count = 0
    active_preset = "wow"

    @staticmethod
    def _load_config():
        config = dict(DEFAULT_CONFIG)
        if os.path.exists(BUTTON_CONFIG_FILE):
            with open(BUTTON_CONFIG_FILE, "r") as f:
                saved = json.load(f)
            config.update(saved)
        if config.get("whisperModel") not in WHISPER_MODELS:
            config["whisperModel"] = "base"
        if config.get("whisperLanguage") not in WHISPER_LANGUAGES:
            config["whisperLanguage"] = "auto"
        if config.get("game") not in _game_presets:
            config["game"] = "wow"
        if not isinstance(config.get("buttons"), list) or not config["buttons"]:
            config["buttons"] = ["L1", "R1"]
        return config

    @staticmethod
    def _save_config(config):
        with open(BUTTON_CONFIG_FILE, "w") as f:
            json.dump(config, f)

    @staticmethod
    def _update_config(**kwargs):
        config = Plugin._load_config()
        config.update(kwargs)
        Plugin._save_config(config)
        return config

    @staticmethod
    def start_ydotoold():
        Plugin.ydotoold_ready = False
        ydotoold = os.path.join(plugin_path, "bin", "ydotoold")
        if not os.path.isfile(ydotoold):
            logger.error(f"Bundled ydotoold not found: {ydotoold}")
            return False
        Plugin.stop_ydotoold()
        Plugin.ydotoold_process = subprocess.Popen(
            [ydotoold, "--socket-path", YDOTOOL_SOCKET, "--socket-perm", "0600", "--mouse-off"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=Plugin._log_process_output, args=(Plugin.ydotoold_process,), daemon=True).start()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if Plugin.ydotoold_process.poll() is not None:
                logger.error(f"ydotoold exited with code {Plugin.ydotoold_process.returncode}")
                Plugin.ydotoold_process = None
                return False
            if os.path.exists(YDOTOOL_SOCKET):
                Plugin.ydotoold_ready = True
                return True
            time.sleep(0.05)
        Plugin.stop_ydotoold()
        return False

    @staticmethod
    def stop_ydotoold():
        Plugin.ydotoold_ready = False
        process = Plugin.ydotoold_process
        Plugin.ydotoold_process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        try:
            if os.path.exists(YDOTOOL_SOCKET):
                os.remove(YDOTOOL_SOCKET)
        except OSError:
            pass

    @staticmethod
    def _log_process_output(process):
        try:
            for line in process.stdout:
                logger.info(f"Child process: {line.rstrip()}")
        except Exception:
            pass

    @staticmethod
    def start_controller_listener():
        Plugin.stop_controller_listener()
        python_bin = "/usr/bin/python3"
        if not os.path.exists(python_bin):
            python_bin = shutil.which("python3")
            if not python_bin:
                logger.error("No python3 found")
                return False
        Plugin.listener_process = subprocess.Popen(
            [python_bin, "-m", "deckvoice.controller_listener"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=plugin_path,
            env={
                **os.environ,
                "DECKVOICE_CONFIG_DIR": CONFIG_DIR,
                "PYTHONPATH": plugin_path,
            },
        )
        threading.Thread(target=Plugin._log_process_output, args=(Plugin.listener_process,), daemon=True).start()
        time.sleep(0.5)
        if Plugin.listener_process.poll() is not None:
            logger.error(f"Controller listener exited with code {Plugin.listener_process.returncode}")
            return False
        return True

    @staticmethod
    def stop_controller_listener():
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 9)
            except Exception:
                pass
        if Plugin.listener_process:
            try:
                Plugin.listener_process.kill()
            except Exception:
                pass
            Plugin.listener_process = None
        for path in (STATE_FILE, PREVIEW_FILE, PID_FILE, CONTROLLER_TYPE_FILE):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    @staticmethod
    def poll_button_state():
        logger.info("Button state polling started")
        last_state = False
        health_check_counter = 0
        while Plugin.poll_running:
            try:
                if not Plugin.controller_enabled:
                    time.sleep(0.1)
                    continue
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, "r") as f:
                        state = f.read().strip() == "1"
                    if state and not last_state:
                        if Plugin.voice_service and not Plugin.voice_service.is_recording:
                            logger.info("Trigger pressed - start recording")
                            Plugin.voice_service.start_recording()
                            Plugin.recording_start_count += 1
                    elif not state and last_state:
                        if Plugin.voice_service and Plugin.voice_service.is_recording:
                            logger.info("Trigger released - stop and send")
                            Plugin.voice_service.stop_recording(send=True)
                    last_state = state

                health_check_counter += 1
                if health_check_counter >= 20:
                    health_check_counter = 0
                    if Plugin.listener_process and Plugin.listener_process.poll() is not None:
                        logger.warning("Controller listener died, restarting")
                        Plugin.start_controller_listener()
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"Error polling button state: {e}")
                time.sleep(0.1)
        logger.info("Button state polling stopped")

    @staticmethod
    def _start_runtime():
        config = Plugin._load_config()
        Plugin.active_preset = config["game"]
        preset = _game_presets.get(Plugin.active_preset, _game_presets.get("wow", {}))

        if Plugin.voice_service is None:
            Plugin.voice_service = VoiceService(
                plugin_dir=plugin_path,
                models_dir=MODELS_DIR,
                preset=preset,
                model_size=config["whisperModel"],
                language=config["whisperLanguage"],
                ca_file=CA_FILE,
            )
        else:
            Plugin.voice_service.model_size = config["whisperModel"]
            Plugin.voice_service.language = config["whisperLanguage"]
            Plugin.voice_service.set_preset(preset)

        if not Plugin.start_ydotoold():
            logger.error("Failed to start ydotoold")
            return False
        if not Plugin.voice_service.start_whisper_server():
            logger.error("Failed to start whisper-server")
            Plugin.stop_ydotoold()
            return False
        if not Plugin.start_controller_listener():
            logger.error("Failed to start controller listener")
            Plugin.voice_service.stop_whisper_server()
            Plugin.stop_ydotoold()
            return False

        Plugin.poll_running = True
        if Plugin.poll_thread is None or not Plugin.poll_thread.is_alive():
            Plugin.poll_thread = threading.Thread(target=Plugin.poll_button_state, daemon=True)
            Plugin.poll_thread.start()
        Plugin.controller_enabled = True
        return True

    @staticmethod
    def _stop_runtime():
        Plugin.controller_enabled = False
        Plugin.poll_running = False
        if Plugin.voice_service:
            if Plugin.voice_service.is_recording:
                Plugin.voice_service.stop_recording(send=False)
            Plugin.voice_service.stop_whisper_server()
        Plugin.stop_controller_listener()
        Plugin.stop_ydotoold()

    async def _main(self):
        logger.info("Initializing DeckVoice")
        try:
            config = Plugin._load_config()
            Plugin.active_preset = config["game"]
            preset = _game_presets.get(Plugin.active_preset, _game_presets.get("wow", {}))
            Plugin.voice_service = VoiceService(
                plugin_dir=plugin_path,
                models_dir=MODELS_DIR,
                preset=preset,
                model_size=config["whisperModel"],
                language=config["whisperLanguage"],
                ca_file=CA_FILE,
            )
            if config.get("enabled"):
                logger.info("Restoring enabled state")
                Plugin._start_runtime()
        except Exception:
            logger.error(f"Failed to initialize: {traceback.format_exc()}")

    async def _unload(self):
        logger.info("Unloading DeckVoice")
        Plugin._stop_runtime()

    async def _uninstall(self):
        Plugin._stop_runtime()

    async def set_enabled(self, enabled: bool):
        Plugin._update_config(enabled=bool(enabled))
        if enabled:
            ok = Plugin._start_runtime()
            return {"success": ok, "error": None if ok else (Plugin.voice_service.model_load_error if Plugin.voice_service else "start failed")}
        Plugin._stop_runtime()
        return {"success": True}

    async def get_button_config(self):
        return {"success": True, "config": Plugin._load_config()}

    async def set_button_config(self, buttons):
        if not isinstance(buttons, list) or not (1 <= len(buttons) <= 5):
            return {"success": False, "error": "buttons must be a list of 1-5 names"}
        Plugin._update_config(buttons=buttons)
        if Plugin.controller_enabled:
            Plugin.start_controller_listener()
        return {"success": True}

    async def get_presets(self):
        return {"success": True, "presets": _game_presets}

    async def get_whisper_languages(self):
        return {
            "success": True,
            "languages": list(WHISPER_LANGUAGES),
            "names": WHISPER_LANGUAGE_NAMES,
            "models": list(WHISPER_MODELS),
        }

    async def set_active_preset(self, game: str):
        if game not in _game_presets:
            return {"success": False, "error": f"unknown preset: {game}"}
        Plugin._update_config(game=game)
        Plugin.active_preset = game
        if Plugin.voice_service:
            Plugin.voice_service.set_preset(_game_presets[game])
            if Plugin.controller_enabled:
                Plugin.voice_service.start_whisper_server()
        return {"success": True}

    async def set_whisper_model(self, model: str):
        if model not in WHISPER_MODELS:
            return {"success": False, "error": f"unknown model: {model}"}
        Plugin._update_config(whisperModel=model)
        if Plugin.voice_service:
            Plugin.voice_service.model_size = model
            if Plugin.controller_enabled:
                ok = Plugin.voice_service.start_whisper_server()
                return {"success": ok, "error": Plugin.voice_service.model_load_error}
        return {"success": True}

    async def set_whisper_language(self, language: str):
        if language not in WHISPER_LANGUAGES:
            return {"success": False, "error": f"unknown language: {language}"}
        Plugin._update_config(whisperLanguage=language)
        if Plugin.voice_service:
            Plugin.voice_service.language = language
            if Plugin.controller_enabled:
                ok = Plugin.voice_service.start_whisper_server()
                return {"success": ok, "error": Plugin.voice_service.model_load_error}
        return {"success": True}

    async def get_status(self):
        vs = Plugin.voice_service
        button_state = "None"
        if os.path.exists(PREVIEW_FILE):
            try:
                with open(PREVIEW_FILE, "r") as f:
                    button_state = f.read().strip() or "None"
            except OSError:
                pass
        return {
            "success": True,
            "enabled": Plugin.controller_enabled,
            "status": vs.status if vs else "off",
            "recording": bool(vs and vs.is_recording),
            "server_ready": bool(vs and vs.server_ready),
            "model_loading": bool(vs and vs.model_loading),
            "model_load_error": vs.model_load_error if vs else None,
            "preview_text": vs.preview_text if vs else "",
            "last_transcription": vs.last_transcription if vs else None,
            "recording_start_count": Plugin.recording_start_count,
            "button_state": button_state,
            "game": Plugin.active_preset,
            "ydotoold_ready": Plugin.ydotoold_ready,
        }
