import json
from pathlib import Path

import pytest

from deckvoice.voice_service import VoiceService

ROOT = Path(__file__).resolve().parents[1]
PRESETS = json.loads((ROOT / "defaults" / "game_presets.json").read_text())


@pytest.fixture
def wow_svc(tmp_path):
    return VoiceService(
        plugin_dir=ROOT,
        models_dir=tmp_path,
        preset=PRESETS["wow"],
        model_size="base",
        language="auto",
    )


@pytest.fixture
def generic_svc(tmp_path):
    return VoiceService(
        plugin_dir=ROOT,
        models_dir=tmp_path,
        preset=PRESETS["generic"],
        model_size="base",
        language="auto",
    )


class TestWoWChannelSeparators:
    def test_space_separator(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("party let's go")
        assert ch == "party"
        assert text == "let's go"

    def test_colon_separator(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("party: pull boss")
        assert ch == "party"
        assert text == "pull boss"

    def test_comma_separator(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("party, I need mana")
        assert ch == "party"
        assert text == "I need mana"

    def test_period_separator(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("party. ready?")
        assert ch == "party"
        assert text == "ready?"

    def test_case_insensitive(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("Party: hello")
        assert ch == "party"
        assert text == "hello"


class TestWoWChannels:
    @pytest.mark.parametrize(
        "prefix,expected_channel",
        [
            ("say", "say"),
            ("party", "party"),
            ("raid", "raid"),
            ("guild", "guild"),
            ("officer", "officer"),
            ("yell", "yell"),
            ("instance", "instance"),
            ("whisper", "whisper"),
            ("type", "type"),
            ("alert", "alert"),
            ("general", "general"),
            ("trade", "trade"),
            ("local defense", "localdefense"),
            ("lfg", "lfg"),
            ("looking for group", "lfg"),
        ],
    )
    def test_channel_prefix_recognized(self, wow_svc, prefix, expected_channel):
        ch, _ = wow_svc.parse_channel_and_text(f"{prefix} hello")
        assert ch == expected_channel

    def test_no_prefix_uses_default(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("hello everyone")
        assert ch == ""
        assert text == "hello everyone"
        assert wow_svc.channel_commands.get(ch, "") == ""

    def test_partial_channel_name_not_matched(self, wow_svc):
        ch, _ = wow_svc.parse_channel_and_text("par hello")
        assert ch == ""

    def test_say_prefix_uses_slash_s(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("say hello everyone")
        assert ch == "say"
        assert text == "hello everyone"
        assert wow_svc.channel_commands[ch] == "/s "

    def test_russian_say(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("скажи всем привет")
        assert ch == "say"
        assert text == "всем привет"

    def test_russian_party(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("пати hello")
        assert ch == "party"
        assert text == "hello"

    def test_russian_general(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("общий wts boe")
        assert ch == "general"
        assert text == "wts boe"

    def test_russian_general_hello(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("общий всем привет")
        assert ch == "general"
        assert text == "всем привет"

    def test_russian_general_comma(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("общий, всем привет")
        assert ch == "general"
        assert text == "всем привет"


class TestGenericPreset:
    def test_default_channel_is_type(self, generic_svc):
        assert generic_svc.default_channel == "type"

    def test_no_channel_keywords(self, generic_svc):
        ch, text = generic_svc.parse_channel_and_text("party let's go")
        assert ch == "type"
        assert text == "party let's go"


class TestWavAndMultipart:
    def test_wav_header(self):
        from deckvoice.voice_service import _wav_bytes

        pcm = b"\x00\x00" * 1600
        wav = _wav_bytes(pcm, 16000)
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"

    def test_send_plain_has_no_slash(self, wow_svc, monkeypatch):
        typed = []
        monkeypatch.setattr(wow_svc, "_type_text", lambda _y, _e, text: typed.append(text))
        monkeypatch.setattr("deckvoice.voice_service.subprocess.run", lambda *_a, **_k: None)
        wow_svc.send_to_chat("hello everyone")
        assert typed == ["hello everyone"]

    def test_send_say_uses_slash_s(self, wow_svc, monkeypatch):
        typed = []
        monkeypatch.setattr(wow_svc, "_type_text", lambda _y, _e, text: typed.append(text))
        monkeypatch.setattr("deckvoice.voice_service.subprocess.run", lambda *_a, **_k: None)
        wow_svc.send_to_chat("say hello everyone")
        assert typed == ["/s hello everyone"]

    def test_unicode_pastes_via_clipboard(self, wow_svc, monkeypatch):
        calls = []

        class Result:
            returncode = 0

        monkeypatch.setattr(wow_svc, "_set_clipboard", lambda text: True)
        monkeypatch.setattr(
            "deckvoice.voice_service.subprocess.run",
            lambda cmd, **_kwargs: calls.append(cmd) or Result(),
        )
        wow_svc.send_to_chat("Ок, как мне слышно")
        assert any("47:1" in cmd for cmd in calls)

    def test_start_overlay_skips_missing_binary(self, wow_svc, tmp_path):
        wow_svc.plugin_dir = tmp_path
        wow_svc.start_overlay()
        assert wow_svc._overlay_proc is None

    def test_stop_whisper_reaps_without_process(self, wow_svc):
        wow_svc.server_process = None
        wow_svc.stop_whisper_server()
        assert wow_svc.server_ready is False
        assert wow_svc.status == "off"

    def test_stop_keeps_final_preview(self, wow_svc):
        wow_svc.server_ready = True
        wow_svc.is_recording = True
        wow_svc.sample_rate = 16000
        wow_svc.audio_chunks = [b"\x00\x00" * 8000]
        wow_svc.preview_text = "hello"
        wow_svc._inference = lambda pcm, sr: "hello world"
        wow_svc.stop_recording(send=False)
        assert wow_svc.preview_text == "hello world"
        assert wow_svc.last_transcription == "hello world"
        assert wow_svc.status == "listening"
        assert wow_svc.is_recording is False


def test_vu_levels_silence_is_zero():
    from deckvoice.voice_service import vu_levels

    assert vu_levels(b"\x00\x00" * 64) == [0.0] * 8


def test_vu_levels_loud_pcm_fills_bars():
    import struct

    from deckvoice.voice_service import vu_levels

    pcm = struct.pack("<h", 22000) * 64
    levels = vu_levels(pcm)
    assert len(levels) == 8
    assert all(v > 0.7 for v in levels)


def test_to_mono_mixes_left_and_right():
    import struct

    from deckvoice.voice_service import to_mono

    left = struct.pack("<hh", 20000, 0) * 4
    right = struct.pack("<hh", 0, 20000) * 4
    assert to_mono(left, 2) == to_mono(right, 2) == struct.pack("<h", 10000) * 4
    mono = struct.pack("<h", 1234) * 4
    assert to_mono(mono, 1) is mono
