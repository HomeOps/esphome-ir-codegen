"""Unit tests for the Flipper .ir -> ESPHome transformer."""

from flipper_ir_to_esphome import emit_nec, emit_raw, emit_sony, generate, parse_ir


def test_parse_splits_on_hash():
    text = (
        "Filetype: IR signals file\nVersion: 1\n#\n"
        "name: A\ntype: parsed\nprotocol: NEC\n"
        "address: 04 00 00 00\ncommand: 08 00 00 00\n#\n"
        "name: B\ntype: raw\nfrequency: 38000\ndata: 100 200\n"
    )
    entries = parse_ir(text)
    assert [e["name"] for e in entries] == ["A", "B"]


def test_nec_adds_inverted_high_byte():
    action, args = emit_nec({"address": "04 00 00 00", "command": "08 00 00 00"})
    assert action == "transmit_nec"
    assert args["address"] == "0xFB04"
    assert args["command"] == "0xF708"


def test_sony_sirc_packs_command_then_address():
    action, args = emit_sony(
        {"protocol": "SIRC", "address": "01 00 00 00", "command": "15 00 00 00"}
    )
    assert action == "transmit_sony"
    assert args["nbits"] == 12
    # data = command(0x15) | (address(0x01) << 7) = 0x95
    assert args["data"] == "0x95"


def test_raw_alternates_sign():
    action, args = emit_raw({"frequency": "38000", "data": "100 200 300 400"})
    assert action == "transmit_raw"
    assert args["carrier_frequency"] == 38000
    assert args["code"] == [100, -200, 300, -400]


def test_generate_emits_stable_button_id():
    # The Atom-button showcase presses `power` — that id must be stable.
    entries = [{
        "name": "Power", "type": "parsed", "protocol": "SIRC",
        "address": "01 00 00 00", "command": "15 00 00 00",
    }]
    out = generate(entries, "ref", "src", None, "")
    assert "id: ir_power" in out
    assert 'name: "Power"' in out
    assert "transmit_sony" in out
