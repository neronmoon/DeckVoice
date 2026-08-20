#!/usr/bin/env python3
import io
import json
import logging
import os
import ssl
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

logger = logging.getLogger()

WHISPER_MODELS = ("tiny", "base", "small-q5_1", "medium-q5_0")
WHISPER_LANGUAGE_NAMES = {
    "en": "English",
    "ru": "Russian",
    "uk": "Ukrainian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "it": "Italian",
    "pl": "Polish",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
}
WHISPER_LANGUAGES = ("auto",) + tuple(WHISPER_LANGUAGE_NAMES.keys())

GGML_MODEL_FILES = {
    "tiny": "ggml-tiny-q8_0.bin",
    "base": "ggml-base-q8_0.bin",
    "small-q5_1": "ggml-small-q5_1.bin",
    "medium-q5_0": "ggml-medium-q5_0.bin",
}
GGML_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

WHISPER_SERVER_HOST = "127.0.0.1"
WHISPER_SERVER_PORT = 8178
MIN_INFERENCE_BYTES = 8000
YDOTOOL_SOCKET = "/tmp/deckvoice-ydotool.sock"
VU_FILE = "/tmp/deckvoice_vu"
VU_BARS = 8


def to_mono(pcm_int16: bytes, channels: int) -> bytes:
    if channels <= 1:
        return pcm_int16
    n = len(pcm_int16) // 2
    samples = struct.unpack_from(f"<{n}h", pcm_int16)
    out = []
    for i in range(0, n - channels + 1, channels):
        acc = 0
        for c in range(channels):
            acc += samples[i + c]
        out.append(acc // channels)
    return struct.pack(f"<{len(out)}h", *out)


def vu_levels(pcm_int16: bytes, bars=VU_BARS) -> list:
    n = len(pcm_int16) // 2
    if n < bars:
        return [0.0] * bars
    samples = struct.unpack_from(f"<{n}h", pcm_int16)
    step = n // bars
    out = []
    for i in range(bars):
        sl = samples[i * step:(i + 1) * step]
        acc = 0
        for s in sl:
            acc += s * s
        rms = (acc / len(sl)) ** 0.5 / 32768.0
        out.append(min(1.0, rms * 6.0))
    return out


def write_vu(levels) -> None:
    try:
        with open(VU_FILE, "w") as f:
            f.write(" ".join(f"{v:.3f}" for v in levels))
    except OSError:
        pass


def _wav_bytes(pcm_int16: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_int16)
    return buf.getvalue()


def _multipart(fields: dict, file_field: str, filename: str, content: bytes, content_type: str):
    boundary = b"----DeckVoiceBoundary7MA4YWxkTrZu0gW"
    parts = []
    for name, value in fields.items():
        parts.append(
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="' + name.encode() + b'"\r\n\r\n'
            + str(value).encode() + b"\r\n"
        )
    parts.append(
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="' + file_field.encode()
        + b'"; filename="' + filename.encode() + b'"\r\n'
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n"
        + content + b"\r\n"
    )
    parts.append(b"--" + boundary + b"--\r\n")
    body = b"".join(parts)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"}
    return body, headers


class VoiceService:
    def __init__(
        self,
        plugin_dir,
        models_dir,
        preset=None,
        model_size="base",
        language="auto",
        ca_file=None,
    ):
        self.plugin_dir = Path(plugin_dir)
        self.models_dir = Path(models_dir)
        self.preset = preset or {}
        self.model_size = model_size if model_size in WHISPER_MODELS else "base"
        self.language = language if language in WHISPER_LANGUAGES else "auto"
        self.ca_file = ca_file
        self.default_channel = self.preset.get("default_channel", "")
        self.channel_commands = self.preset.get("channels") or {"type": ""}

        self.server_process = None
        self.server_ready = False
        self.model_loading = False
        self.model_load_error = None
        self._server_log_lines = []
        self._server_log_thread = None
        self._overlay_proc = None

        self.is_recording = False
        self.recording_stream = None
        self.audio_chunks = []
        self.audio_lock = threading.Lock()
        self.sample_rate = 16000
        self.input_channels = 1
        self.recording_lock = threading.Lock()
        self.preview_text = ""
        self.last_transcription = None
        self.last_transcription_time = None
        self.status = "off"

        self._load_language_config()
        if self.preset.get("channels"):
            self.channel_commands = self.preset["channels"]

    def _load_language_config(self):
        self.channel_triggers = {}
        config_file = self.plugin_dir / "channel_languages.json"
        if not config_file.exists():
            config_file = self.plugin_dir / "defaults" / "channel_languages.json"
        if not config_file.exists():
            for channel in self.channel_commands:
                self.channel_triggers[channel] = channel
            return
        with open(config_file) as f:
            config = json.load(f)
        for lang_code in config.get("enabled_languages", ["en"]):
            lang_data = config.get("languages", {}).get(lang_code)
            if not lang_data:
                continue
            for channel_name, triggers in lang_data.get("channels", {}).items():
                for trigger in triggers:
                    self.channel_triggers[trigger.lower()] = channel_name

    def set_preset(self, preset):
        self.preset = preset or {}
        self.default_channel = self.preset.get("default_channel", "")
        self.channel_commands = self.preset.get("channels") or {"type": ""}

    def _ggml_model_path(self):
        return self.models_dir / GGML_MODEL_FILES[self.model_size]

    def _ssl_context(self):
        if self.ca_file:
            return ssl.create_default_context(cafile=self.ca_file)
        return ssl.create_default_context()

    def ensure_model(self):
        model_path = self._ggml_model_path()
        if model_path.is_file() and model_path.stat().st_size > 0:
            return model_path
        self.models_dir.mkdir(parents=True, exist_ok=True)
        filename = model_path.name
        url = f"{GGML_MODEL_BASE_URL}/{filename}"
        tmp_path = model_path.with_suffix(model_path.suffix + ".partial")
        logger.info(f"Downloading ggml model {filename}")
        self.status = "loading"
        with urllib.request.urlopen(url, context=self._ssl_context()) as resp, open(tmp_path, "wb") as out:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        tmp_path.replace(model_path)
        logger.info(f"Downloaded ggml model to {model_path}")
        return model_path

    def _server_env(self):
        lib_dir = self.plugin_dir / "bin" / "lib"
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = str(lib_dir)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        return env

    def start_whisper_server(self):
        self.stop_whisper_server()
        self.model_loading = True
        self.model_load_error = None
        self.status = "loading"
        self._server_log_lines = []
        try:
            model_path = self.ensure_model()
            binary = self.plugin_dir / "bin" / "whisper-server"
            if not binary.is_file():
                raise FileNotFoundError(f"whisper-server not found: {binary}")

            cmd = [
                str(binary),
                "-m", str(model_path),
                "--host", WHISPER_SERVER_HOST,
                "--port", str(WHISPER_SERVER_PORT),
                "-l", self.language,
                "-t", "4",
                "-sns",
                "--no-flash-attn",
            ]

            env = self._server_env()
            logger.info(
                "Starting whisper-server (gpu): cmd=%s LD_LIBRARY_PATH=%s",
                cmd,
                env.get("LD_LIBRARY_PATH", ""),
            )
            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                cwd=str(self.plugin_dir / "bin"),
                start_new_session=True,
            )
            logger.info("whisper-server pid=%s", self.server_process.pid)
            self._server_log_thread = threading.Thread(target=self._log_server, daemon=True)
            self._server_log_thread.start()

            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                code = self.server_process.poll()
                if code is not None:
                    self._drain_server_log(timeout=1.0)
                    raise RuntimeError(self._format_server_exit(code))
                if self._server_alive():
                    self.server_ready = True
                    self.model_loading = False
                    self.status = "listening"
                    logger.info("whisper-server ready (gpu)")
                    self.start_overlay()
                    return True
                time.sleep(0.2)
            raise TimeoutError(
                "Timed out waiting for whisper-server; last log:\n"
                + "\n".join(self._server_log_lines[-30:])
            )
        except Exception as e:
            self.model_load_error = str(e)
            self.model_loading = False
            self.server_ready = False
            self.status = "error"
            logger.error("Failed to start whisper-server: %s", e)
            self.stop_whisper_server()
            return False

    def _format_server_exit(self, code):
        import signal

        detail = f"whisper-server exited with code {code}"
        if code is not None and code < 0:
            sig = -code
            try:
                detail += f" ({signal.Signals(sig).name})"
            except ValueError:
                detail += f" (signal {sig})"
        tail = self._server_log_lines[-40:]
        if tail:
            detail += "\n--- whisper-server output ---\n" + "\n".join(tail)
        return detail

    def _drain_server_log(self, timeout=1.0):
        thread = getattr(self, "_server_log_thread", None)
        if thread and thread.is_alive():
            thread.join(timeout=timeout)

    def _log_server(self):
        process = self.server_process
        if not process or not process.stdout:
            return
        try:
            for line in process.stdout:
                text = line.rstrip()
                self._server_log_lines.append(text)
                if len(self._server_log_lines) > 200:
                    self._server_log_lines = self._server_log_lines[-200:]
                logger.info("whisper-server: %s", text)
        except Exception as e:
            logger.warning("whisper-server log reader stopped: %s", e)

    def _server_alive(self):
        try:
            req = urllib.request.Request(
                f"http://{WHISPER_SERVER_HOST}:{WHISPER_SERVER_PORT}/",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=1) as resp:
                return resp.status < 500
        except Exception:
            return False

    def _whisper_binary(self):
        return os.path.realpath(self.plugin_dir / "bin" / "whisper-server")

    def _reap_whisper_servers(self):
        binary = self._whisper_binary()
        if not os.path.isfile(binary) or not os.path.isdir("/proc"):
            return
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                exe = os.path.realpath(f"/proc/{entry.name}/exe")
            except OSError:
                continue
            if exe != binary:
                continue
            pid = int(entry.name)
            try:
                os.kill(pid, 9)
            except OSError:
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except OSError:
                pass

    def stop_whisper_server(self):
        self.server_ready = False
        process = self.server_process
        self.server_process = None
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, 9)
            except OSError:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        self._reap_whisper_servers()
        self.stop_overlay()
        self.status = "off"

    def start_overlay(self):
        if self._overlay_proc and self._overlay_proc.poll() is None:
            return
        binary = self.plugin_dir / "bin" / "deckvoice-overlay"
        if not binary.is_file():
            logger.warning("overlay binary missing: %s", binary)
            return
        env = self._server_env()
        display = env.get("DISPLAY") or ":0"
        env["DISPLAY"] = display
        env["HOME"] = "/home/deck"
        cmd = [str(binary)]
        if os.geteuid() == 0:
            cmd = [
                "runuser", "-u", "deck", "--",
                "env",
                f"DISPLAY={display}",
                f"LD_LIBRARY_PATH={env.get('LD_LIBRARY_PATH', '')}",
                "HOME=/home/deck",
                str(binary),
            ]
        try:
            log = open("/tmp/deckvoice-overlay.log", "w")
            self._overlay_proc = subprocess.Popen(
                cmd,
                env=env,
                start_new_session=True,
                stdout=log,
                stderr=log,
            )
        except OSError as e:
            logger.warning("overlay start failed: %s", e)
            self._overlay_proc = None
            return
        logger.info("overlay pid=%s", self._overlay_proc.pid)

    def stop_overlay(self):
        proc = self._overlay_proc
        self._overlay_proc = None
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, 9)
            except OSError:
                try:
                    proc.kill()
                except OSError:
                    pass

    def _inference(self, pcm_int16: bytes, sample_rate: int) -> str:
        if not self.server_ready or len(pcm_int16) < MIN_INFERENCE_BYTES:
            return ""
        wav = _wav_bytes(pcm_int16, sample_rate)
        fields = {
            "temperature": "0.0",
            "response_format": "json",
            "language": self.language,
        }
        body, headers = _multipart(fields, "file", "audio.wav", wav, "audio/wav")
        req = urllib.request.Request(
            f"http://{WHISPER_SERVER_HOST}:{WHISPER_SERVER_PORT}/inference",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            logger.warning(f"inference failed: {e}")
            return ""
        text = payload.get("text") or ""
        return text.strip()

    def audio_callback(self, indata, frames, time_info, status):
        if not self.is_recording:
            return
        raw = to_mono(bytes(indata), self.input_channels)
        with self.audio_lock:
            self.audio_chunks.append(raw)
        write_vu(vu_levels(raw))

    def _drain_pcm(self) -> bytes:
        with self.audio_lock:
            data = b"".join(self.audio_chunks)
            self.audio_chunks = []
            return data

    def _resample_to_16k(self, pcm: bytes, src_rate: int) -> bytes:
        if src_rate == 16000:
            return pcm
        n = len(pcm) // 2
        samples = struct.unpack(f"<{n}h", pcm)
        ratio = src_rate / 16000
        out_n = int(n / ratio)
        out = []
        for i in range(out_n):
            src_i = int(i * ratio)
            if src_i >= n:
                break
            out.append(samples[src_i])
        return struct.pack(f"<{len(out)}h", *out)

    def start_recording(self):
        import sounddevice as sd

        with self.recording_lock:
            if self.is_recording:
                return
            self.is_recording = True
            self.preview_text = ""
            with self.audio_lock:
                self.audio_chunks = []
            self.status = "recording"

            device_info = sd.query_devices(sd.default.device[0], "input")
            self.sample_rate = int(device_info["default_samplerate"])
            self.input_channels = 2 if device_info["max_input_channels"] >= 2 else 1
            self.recording_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.input_channels,
                callback=self.audio_callback,
                dtype="int16",
            )
            self.recording_stream.start()

    def stop_recording(self, send=True):
        with self.recording_lock:
            if not self.is_recording:
                return
            self.is_recording = False
            if self.recording_stream:
                self.recording_stream.stop()
                self.recording_stream.close()
                self.recording_stream = None

            pcm = self._drain_pcm()
            write_vu([0.0] * VU_BARS)
            self.status = "transcribing"
            if not pcm:
                self.preview_text = ""
                self.status = "listening"
                return

            pcm16 = self._resample_to_16k(pcm, self.sample_rate)
            t0 = time.monotonic()
            text = self._inference(pcm16, 16000)
            logger.info("inference %.2fs (%d bytes)", time.monotonic() - t0, len(pcm16))
            self.preview_text = text
            self.last_transcription = text
            self.last_transcription_time = time.time()
            if text and send:
                self.send_to_chat(text)
            self.status = "listening"

    def parse_channel_and_text(self, text):
        text = text.strip()
        text_lower = text.lower()
        for trigger, channel_name in sorted(
            self.channel_triggers.items(), key=lambda item: len(item[0]), reverse=True
        ):
            prefixes = [f"{trigger}:", f"{trigger},", f"{trigger}.", f"{trigger} "]
            for prefix in prefixes:
                if text_lower.startswith(prefix):
                    if channel_name in self.channel_commands:
                        return channel_name, text[len(prefix):].strip()
        return self.default_channel, text

    def send_to_chat(self, text, channel=None):
        if not text:
            return
        if channel is None:
            channel, text = self.parse_channel_and_text(text)
        channel_cmd = self.channel_commands.get(channel, "")
        if channel == "type":
            text = text.rstrip(".!?,;:")
        full_message = f"{channel_cmd}{text}"

        ydotool = self.plugin_dir / "bin" / "ydotool"
        if not ydotool.is_file():
            ydotool = "ydotool"
        else:
            ydotool = str(ydotool)

        env = os.environ.copy()
        env["YDOTOOL_SOCKET"] = YDOTOOL_SOCKET

        if channel == "type":
            open_key = None
            send_key = None
        else:
            open_key = self.preset.get("chat_open_key")
            send_key = self.preset.get("chat_send_key")

        logger.info(f"Sending to {channel}: {full_message}")
        if open_key == "enter":
            subprocess.run([ydotool, "key", "28:1", "28:0"], capture_output=True, text=True, env=env)
            time.sleep(0.1)
        self._type_text(ydotool, env, full_message)
        time.sleep(0.1)
        if send_key == "enter":
            subprocess.run([ydotool, "key", "28:1", "28:0"], capture_output=True, text=True, env=env)

    def _set_clipboard(self, text: str) -> bool:
        script = (
            "import sys\n"
            "text=sys.stdin.read()\n"
            "ok=False\n"
            "try:\n"
            " import gi\n"
            " gi.require_version('Gtk','3.0')\n"
            " gi.require_version('Gdk','3.0')\n"
            " from gi.repository import Gtk,Gdk,GLib\n"
            " Gtk.init([])\n"
            " cb=Gtk.Clipboard.get_default(Gdk.Display.get_default())\n"
            " cb.set_text(text,-1)\n"
            " cb.store()\n"
            " GLib.timeout_add(120,Gtk.main_quit)\n"
            " Gtk.main()\n"
            " ok=True\n"
            "except Exception:\n"
            " try:\n"
            "  import tkinter\n"
            "  r=tkinter.Tk(); r.withdraw()\n"
            "  r.clipboard_clear(); r.clipboard_append(text); r.update()\n"
            "  r.after(120,r.destroy); r.mainloop(); ok=True\n"
            " except Exception:\n"
            "  pass\n"
            "sys.exit(0 if ok else 1)\n"
        )
        env = os.environ.copy()
        env["LANG"] = "en_US.UTF-8"
        env["LC_ALL"] = "en_US.UTF-8"
        xauth = "/home/deck/.Xauthority"
        if os.path.isfile(xauth):
            env["XAUTHORITY"] = xauth
        python = "/usr/bin/python3" if os.path.isfile("/usr/bin/python3") else sys.executable
        for display in (":1", ":0"):
            env["DISPLAY"] = display
            cmd = [python, "-c", script]
            if os.geteuid() == 0:
                cmd = [
                    "runuser", "-u", "deck", "--", "env",
                    f"DISPLAY={display}",
                    f"XAUTHORITY={env.get('XAUTHORITY', '')}",
                    "HOME=/home/deck",
                    "LANG=en_US.UTF-8",
                    python, "-c", script,
                ]
            try:
                r = subprocess.run(
                    cmd, input=text, text=True, capture_output=True, env=env, timeout=3,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            if r.returncode == 0:
                return True
        logger.warning("clipboard set failed")
        return False

    def _type_text(self, ydotool, env, text):
        if self._set_clipboard(text):
            subprocess.run(
                [ydotool, "key", "29:1", "47:1", "47:0", "29:0"],
                capture_output=True,
                text=True,
                env=env,
            )
            return
        subprocess.run([ydotool, "type", "--", text], capture_output=True, text=True, env=env)
