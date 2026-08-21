import math
import struct
import wave

from deckvoice.voice_service import (
    MAX_GAIN,
    TARGET_PEAK,
    boost_pcm,
    highpass_pcm,
    download_progress_label,
    mic_setting_quiet,
    parse_wpctl_volume,
    push_preroll,
    tdp_limit_enabled,
    resample_to_16k,
    spectral_denoise,
    drop_hallucination,
    confirm_tap,
    wrap_pending,
    vad_keep_span,
    write_last_wav,
)


def test_parse_wpctl_volume():
    assert parse_wpctl_volume("Volume: 1.30\n") == (1.3, False)
    assert parse_wpctl_volume("Volume: 0.15 [MUTED]\n") == (0.15, True)


def test_mic_setting_quiet():
    assert mic_setting_quiet("Volume: 0.10\n") is True
    assert mic_setting_quiet("Volume: 1.00 [MUTED]\n") is True
    assert mic_setting_quiet("Volume: 0.25\n") is False
    assert mic_setting_quiet("Volume: 1.30\n") is False


def test_tdp_limit_enabled():
    assert tdp_limit_enabled('"TDPLimitEnabled"\t\t"1"\n') is True
    assert tdp_limit_enabled('"TDPLimitEnabled"\t\t"0"\n') is False
    assert tdp_limit_enabled("") is False


def test_boost_pcm_raises_quiet_peak():
    quiet = struct.pack("<4h", 0, 4000, -800, 400)
    samples = struct.unpack("<4h", boost_pcm(quiet))
    assert max(abs(s) for s in samples) == TARGET_PEAK


def test_boost_pcm_leaves_loud_alone():
    loud = struct.pack("<2h", TARGET_PEAK, -20000)
    assert boost_pcm(loud) == loud


def test_boost_pcm_caps_gain():
    assert struct.unpack("<h", boost_pcm(struct.pack("<h", 100)))[0] == int(100 * MAX_GAIN)


def test_resample_to_16k_averages_bins():
    pcm = struct.pack("<6h", 100, 100, 100, 200, 200, 200)
    assert resample_to_16k(pcm, 48000) == struct.pack("<2h", 100, 200)
    assert resample_to_16k(pcm, 16000) is pcm


def test_highpass_pcm_drops_dc():
    pcm = struct.pack("<400h", *([2000] * 400))
    out = struct.unpack("<400h", highpass_pcm(pcm))
    assert abs(out[-1]) < abs(out[0]) / 3


def test_push_preroll_keeps_latest_bytes():
    from collections import deque

    ring = deque()
    n = 0
    n = push_preroll(ring, n, b"aa", 4)
    n = push_preroll(ring, n, b"bb", 4)
    n = push_preroll(ring, n, b"cc", 4)
    assert b"".join(ring) == b"bbcc"
    assert n == 4


def test_spectral_denoise_drops_hiss_floor():
    n = 16000
    tone = [int(8000 * math.sin(2 * math.pi * 200 * i / 16000)) for i in range(n)]
    hiss = [((i * 1103515245 + 12345) & 0x7FFF) % 800 - 400 for i in range(n)]
    mix = [hiss[i] if i < 6400 else tone[i] + hiss[i] for i in range(n)]
    pcm = struct.pack(f"<{n}h", *mix)
    try:
        import numpy
    except ImportError:
        assert spectral_denoise(pcm) == pcm
        return
    out = struct.unpack(f"<{n}h", spectral_denoise(pcm))
    def rms(sl):
        return math.sqrt(sum(x * x for x in sl) / len(sl))
    assert rms(out[:3200]) < rms(mix[:3200]) * 0.5
    assert max(abs(x) for x in out[8000:12000]) > 4000


def test_vad_keep_span_trims_edges():
    assert vad_keep_span([False, False, True, True, False, False, False], 1) == (1, 5)
    assert vad_keep_span([True, False], 0) == (0, 1)
    assert vad_keep_span([False, False], 3) == (0, 0)


def test_drop_hallucination_youtube_outro():
    assert drop_hallucination("Thanks for watching!") == ""
    assert drop_hallucination("party pull now") == "party pull now"


def test_confirm_tap_needs_second_press():
    hit, last = confirm_tap(1.0, 0.0)
    assert hit is False
    assert last == 1.0
    hit, last = confirm_tap(1.3, last)
    assert hit is True
    assert last == 0.0
    hit, last = confirm_tap(3.0, 1.0)
    assert hit is False
    assert last == 3.0


def test_wrap_pending_breaks_long_line():
    assert wrap_pending("party pull now stack left") == "party pull now stack left"
    text = wrap_pending("one two three four five six seven eight nine ten eleven")
    assert "\n" in text
    assert "…" in wrap_pending("word " * 30)


def test_write_last_wav(tmp_path):
    path = tmp_path / "last.wav"
    pcm = struct.pack("<4h", 0, 1200, -800, 400)
    write_last_wav(pcm, 16000, str(path))
    with wave.open(str(path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.readframes(wf.getnframes()) == pcm


def test_download_progress_label():
    assert download_progress_label(0, 1031 * 1024 * 1024) == "0 / 1031 MB"
    assert download_progress_label(5 * 1024 * 1024, 0) == "5 MB"
