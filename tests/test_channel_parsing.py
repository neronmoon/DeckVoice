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
        ],
    )
    def test_channel_prefix_recognized(self, wow_svc, prefix, expected_channel):
        ch, _ = wow_svc.parse_channel_and_text(f"{prefix} hello")
        assert ch == expected_channel

    def test_no_prefix_uses_default(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("hello everyone")
        assert ch == "say"
        assert text == "hello everyone"

    def test_partial_channel_name_not_matched(self, wow_svc):
        ch, _ = wow_svc.parse_channel_and_text("par hello")
        assert ch == "say"

    def test_russian_party(self, wow_svc):
        ch, text = wow_svc.parse_channel_and_text("пати hello")
        assert ch == "party"
        assert text == "hello"


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

    def test_preview_interval_constant(self):
        from deckvoice.voice_service import PREVIEW_INTERVAL_S

        assert PREVIEW_INTERVAL_S == 0.8
