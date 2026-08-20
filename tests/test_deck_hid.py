from deckvoice.deck_hid import STEAM_DECK_REPORT_SIZE, raw_button_states


def _blank_report(report_type=9):
    report = bytearray(STEAM_DECK_REPORT_SIZE)
    report[0] = 1
    report[1] = 0
    report[2] = report_type
    return report


def test_l1_r1_bits():
    report = _blank_report()
    report[8] |= (1 << 3) | (1 << 2)
    states = raw_button_states(bytes(report))
    assert states["L1"] is True
    assert states["R1"] is True
    assert states["A"] is False


def test_short_report_ignored():
    assert raw_button_states(b"\x00" * 10) is None
