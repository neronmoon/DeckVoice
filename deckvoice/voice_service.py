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
from collections import deque
from pathlib import Path

logger = logging.getLogger()

WHISPER_MODELS = ("tiny", "base", "small-q5_1", "medium-q5_0", "large-q5_0")
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
    "large-q5_0": "ggml-large-v3-q5_0.bin",
}
GGML_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

WHISPER_SERVER_HOST = "127.0.0.1"
WHISPER_SERVER_PORT = 8178
MIN_INFERENCE_BYTES = 8000
YDOTOOL_SOCKET = "/tmp/deckvoice-ydotool.sock"
VU_FILE = "/tmp/deckvoice_vu"
VU_BARS = 8
VU_GAIN = 24.0
PENDING_FILE = "/tmp/deckvoice_pending"
CONFIRM_SEC = 5.0
DOUBLE_TAP_SEC = 0.5
HOLD_TO_REC_SEC = 0.28
LAST_WAV = "/tmp/deckvoice-last.wav"
QUIET_MIC_VOLUME = 0.25
TARGET_PEAK = 18000
MAX_GAIN = 6.0
PREROLL_SEC = 0.5


def push_preroll(ring, nbytes, chunk, limit):
    ring.append(chunk)
    nbytes += len(chunk)
    while nbytes > limit and ring:
        nbytes -= len(ring.popleft())
    return nbytes


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
        out.append(min(1.0, rms * VU_GAIN))
    return out


def write_vu(levels) -> None:
    try:
        with open(VU_FILE, "w") as f:
            f.write(" ".join(f"{v:.3f}" for v in levels))
    except OSError:
        pass


def wrap_pending(text, width=40, max_lines=2):
    words = text.split()
    lines = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if len(trial) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(1, width - 1)].rstrip() + "…"
    return "\n".join(lines)


def write_pending(text: str) -> None:
    tmp = f"{PENDING_FILE}.partial"
    try:
        with open(tmp, "w") as f:
            f.write(text or "")
        os.replace(tmp, PENDING_FILE)
    except OSError:
        pass


def confirm_tap(now, last_tap, window=DOUBLE_TAP_SEC):
    if last_tap and 0 < now - last_tap <= window:
        return True, 0.0
    return False, now


def parse_wpctl_volume(text: str):
    muted = "[MUTED]" in text
    vol = float(text.split(":", 1)[1].split()[0])
    return vol, muted


def mic_setting_quiet(text: str, floor=QUIET_MIC_VOLUME) -> bool:
    vol, muted = parse_wpctl_volume(text)
    return muted or vol < floor


def read_mic_quiet() -> bool:
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    r = subprocess.run(
        ["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"],
        capture_output=True,
        text=True,
        env=env,
        timeout=1,
    )
    if r.returncode or not r.stdout.strip():
        return False
    return mic_setting_quiet(r.stdout)


STEAM_CONFIG_PATHS = (
    "/home/deck/.steam/steam/config/config.vdf",
    "/home/deck/.local/share/Steam/config/config.vdf",
)


def tdp_limit_enabled(text: str) -> bool:
    for line in text.splitlines():
        if '"TDPLimitEnabled"' not in line:
            continue
        if '"1"' in line.split('"TDPLimitEnabled"', 1)[1]:
            return True
    return False


def read_tdp_limited() -> bool:
    seen = set()
    for path in STEAM_CONFIG_PATHS:
        real = os.path.realpath(path)
        if real in seen or not os.path.isfile(path):
            continue
        seen.add(real)
        try:
            with open(path) as f:
                text = f.read()
        except OSError:
            continue
        if tdp_limit_enabled(text):
            return True
    return False


def resample_to_16k(pcm: bytes, src_rate: int) -> bytes:
    if src_rate == 16000:
        return pcm
    n = len(pcm) // 2
    samples = struct.unpack(f"<{n}h", pcm)
    ratio = src_rate / 16000
    out = []
    out_n = int(n / ratio)
    for i in range(out_n):
        a = int(i * ratio)
        b = min(n, int((i + 1) * ratio))
        if a >= n:
            break
        if b <= a:
            b = min(n, a + 1)
        out.append(sum(samples[a:b]) // (b - a))
    return struct.pack(f"<{len(out)}h", *out)


def highpass_pcm(pcm_int16: bytes) -> bytes:
    n = len(pcm_int16) // 2
    if n < 2:
        return pcm_int16
    src = struct.unpack_from(f"<{n}h", pcm_int16)
    y = [0.0] * n
    prev_x = 0.0
    prev_y = 0.0
    for i, s in enumerate(src):
        prev_y = s - prev_x + 0.995 * prev_y
        prev_x = float(s)
        y[i] = prev_y
    peak = max(abs(v) for v in y)
    if peak > 32767:
        scale = 32767.0 / peak
        y = [v * scale for v in y]
    return struct.pack(f"<{n}h", *[int(v) for v in y])


def spectral_denoise(pcm_int16: bytes) -> bytes:
    n = len(pcm_int16) // 2
    n_fft, hop = 512, 128
    if n < n_fft:
        return pcm_int16
    try:
        import numpy as np
    except ImportError:
        return pcm_int16
    x = np.frombuffer(pcm_int16, dtype=np.int16).astype(np.float64)
    w = np.hanning(n_fft)
    frames = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
    spec = np.fft.rfft(frames * w)
    mag = np.abs(spec)
    energy = mag.sum(axis=1)
    k = max(1, len(energy) // 5)
    noise = np.median(mag[np.argsort(energy)[:k]], axis=0)
    gain = np.maximum(mag - 1.2 * noise, 0.12 * mag) / np.maximum(mag, 1e-9)
    cleaned = np.fft.irfft(spec * gain, n=n_fft)
    out = np.zeros(n)
    acc = np.zeros(n)
    for i, chunk in enumerate(cleaned):
        a = i * hop
        out[a:a + n_fft] += chunk * w
        acc[a:a + n_fft] += w * w
    y = np.divide(out, acc, out=np.zeros_like(out), where=acc > 0.05)
    tail = (len(cleaned) - 1) * hop + n_fft
    if tail < n:
        y[tail:] = x[tail:]
    return np.clip(y, -32768, 32767).astype(np.int16).tobytes()


def drop_hallucination(text: str) -> str:
    norm = " ".join("".join(c for c in text.lower() if c.isalpha() or c.isspace()).split())
    if norm in {
        "thanks for watching",
        "thank you for watching",
        "thanks for listening",
        "thank you for listening",
        "please subscribe",
        "thanks for watching everybody",
        "thank you for watching everybody",
    }:
        return ""
    return text


def vad_keep_span(flags, pad):
    if not any(flags):
        return 0, 0
    first = next(i for i, f in enumerate(flags) if f)
    last = len(flags) - 1 - next(i for i, f in enumerate(reversed(flags)) if f)
    return max(0, first - pad), min(len(flags), last + pad + 1)


def vad_trim(pcm_int16: bytes, rate=16000, mode=2, frame_ms=20, pad_ms=200) -> bytes:
    frame = rate * frame_ms // 1000 * 2
    if len(pcm_int16) < frame:
        return pcm_int16
    try:
        import webrtcvad
    except ImportError:
        return pcm_int16
    vad = webrtcvad.Vad(mode)
    flags = [
        vad.is_speech(pcm_int16[i:i + frame], rate)
        for i in range(0, len(pcm_int16) - frame + 1, frame)
    ]
    a, b = vad_keep_span(flags, pad_ms // frame_ms)
    return pcm_int16[a * frame:b * frame]


def boost_pcm(pcm_int16: bytes) -> bytes:
    n = len(pcm_int16) // 2
    if not n:
        return pcm_int16
    samples = struct.unpack_from(f"<{n}h", pcm_int16)
    peak = max(abs(s) for s in samples)
    if peak == 0 or peak >= TARGET_PEAK:
        return pcm_int16
    gain = min(TARGET_PEAK / peak, MAX_GAIN)
    return struct.pack(f"<{n}h", *[int(s * gain) for s in samples])


def write_last_wav(pcm_int16: bytes, sample_rate: int, path=LAST_WAV) -> None:
    tmp = f"{path}.partial"
    with open(tmp, "wb") as f:
        f.write(_wav_bytes(pcm_int16, sample_rate))
    os.replace(tmp, path)


def reap_matching_exes(binary, proc_dir="/proc"):
    binary = os.path.realpath(str(binary))
    if not os.path.isdir(proc_dir):
        return
    for entry in os.scandir(proc_dir):
        if not entry.name.isdigit():
            continue
        try:
            exe = os.path.realpath(os.path.join(proc_dir, entry.name, "exe"))
        except OSError:
            continue
        if exe != binary and not exe.startswith(binary + " "):
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


def download_progress_label(got: int, total: int) -> str:
    mb = got // (1024 * 1024)
    return f"{mb} / {total // (1024 * 1024)} MB" if total else f"{mb} MB"


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
        model_size="small-q5_1",
        language="auto",
        ca_file=None,
    ):
        self.plugin_dir = Path(plugin_dir)
        self.models_dir = Path(models_dir)
        self.preset = preset or {}
        self.model_size = model_size if model_size in WHISPER_MODELS else "small-q5_1"
        self.language = language if language in WHISPER_LANGUAGES else "auto"
        self.ca_file = ca_file
        self.default_channel = self.preset.get("default_channel", "")
        self.channel_commands = self.preset.get("channels") or {"type": ""}

        self.server_process = None
        self.server_ready = False
        self.model_loading = False
        self.model_load_error = None
        self.download_progress = ""
        self._server_log_lines = []
        self._server_log_thread = None
        self._overlay_proc = None
        self.pending_text = ""
        self.pending_until = 0.0

        self.is_recording = False
        self.recording_stream = None
        self.audio_chunks = []
        self.preroll = deque()
        self.preroll_bytes = 0
        self.audio_lock = threading.Lock()
        self.sample_rate = 16000
        self.input_channels = 1
        self.recording_lock = threading.Lock()
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
        self.download_progress = "0 MB"
        with urllib.request.urlopen(url, context=self._ssl_context()) as resp, open(tmp_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                got += len(chunk)
                self.download_progress = download_progress_label(got, total)
        self.download_progress = ""
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

            deadline = time.monotonic() + 180
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
                    self.start_input_stream()
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
            logger.error("Failed to start whisper-server: %s", e)
            self.stop_whisper_server()
            self.status = "error"
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
        reap_matching_exes(self._whisper_binary())

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
        self.clear_pending()
        self.stop_overlay()
        self.stop_input_stream()
        self.model_loading = False
        self.download_progress = ""
        self.status = "off"

    def start_overlay(self):
        if self._overlay_proc and self._overlay_proc.poll() is None:
            return
        binary = self.plugin_dir / "bin" / "deckvoice-overlay"
        if not binary.is_file():
            logger.warning("overlay binary missing: %s", binary)
            return
        reap_matching_exes(binary)
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
        reap_matching_exes(self.plugin_dir / "bin" / "deckvoice-overlay")

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
        return drop_hallucination((payload.get("text") or "").strip())

    def audio_callback(self, indata, frames, time_info, status):
        raw = to_mono(bytes(indata), self.input_channels)
        limit = int(self.sample_rate * 2 * PREROLL_SEC)
        with self.audio_lock:
            self.preroll_bytes = push_preroll(self.preroll, self.preroll_bytes, raw, limit)
            if self.is_recording:
                self.audio_chunks.append(raw)
        if self.is_recording:
            write_vu(vu_levels(raw))

    def start_input_stream(self):
        if self.recording_stream:
            return
        import sounddevice as sd

        try:
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
        except Exception as e:
            logger.warning("mic stream start failed: %s", e)
            self.recording_stream = None

    def stop_input_stream(self):
        stream = self.recording_stream
        self.recording_stream = None
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self.audio_lock:
            self.preroll.clear()
            self.preroll_bytes = 0
            self.audio_chunks = []

    def offer_pending(self, text):
        text = (text or "").strip()
        if not text:
            self.clear_pending()
            return
        self.pending_text = text
        self.pending_until = time.monotonic() + CONFIRM_SEC
        write_pending(wrap_pending(text))

    def clear_pending(self):
        self.pending_text = ""
        self.pending_until = 0.0
        write_pending("")

    def pending_expired(self):
        return bool(self.pending_text) and time.monotonic() >= self.pending_until

    def confirm_pending(self):
        text = self.pending_text
        self.clear_pending()
        if text:
            self.send_to_chat(text)

    def start_recording(self):
        self.clear_pending()
        with self.recording_lock:
            if self.is_recording:
                return
            self.start_input_stream()
            if not self.recording_stream:
                return
            with self.audio_lock:
                self.audio_chunks = list(self.preroll)
                self.is_recording = True
            self.status = "recording"

    def stop_recording(self, send=True):
        with self.recording_lock:
            with self.audio_lock:
                if not self.is_recording:
                    return
                self.is_recording = False
                pcm = b"".join(self.audio_chunks)
                self.audio_chunks = []
            write_vu([0.0] * VU_BARS)
            self.status = "transcribing"
            if not pcm:
                self.status = "listening"
                return

            pcm16 = boost_pcm(vad_trim(spectral_denoise(highpass_pcm(resample_to_16k(pcm, self.sample_rate)))))
            write_last_wav(pcm16, 16000)
            t0 = time.monotonic()
            text = self._inference(pcm16, 16000)
            logger.info("inference %.2fs (%d bytes)", time.monotonic() - t0, len(pcm16))
            if text and send:
                self.offer_pending(text)
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
