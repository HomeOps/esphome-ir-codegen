"""Unit tests for the Flipper .ir -> ESPHome transformer.

Parsed protocols are encoded by the infrared-protocols library and emitted as
transmit_raw, so these assert the raw timings the library returns (its protocol
correctness is covered by its own test suite). Requires the library installed
(Python >= 3.14).
"""

from flipper_ir_to_esphome import (
    _mirror_out,
    emit_parsed,
    emit_raw,
    generate,
    parse_ir,
)


def test_parse_splits_on_hash():
    text = (
        "Filetype: IR signals file\nVersion: 1\n#\n"
        "name: A\ntype: parsed\nprotocol: NEC\n"
        "address: 04 00 00 00\ncommand: 08 00 00 00\n#\n"
        "name: B\ntype: raw\nfrequency: 38000\ndata: 100 200\n"
    )
    entries = parse_ir(text)
    assert [e["name"] for e in entries] == ["A", "B"]


def test_raw_alternates_sign():
    action, args = emit_raw({"frequency": "38000", "data": "100 200 300 400"})
    assert action == "transmit_raw"
    assert args["carrier_frequency"] == 38000
    assert args["code"] == [100, -200, 300, -400]


def test_parsed_nec_encoded_as_raw_timings():
    # NEC leader is 9000µs mark + 4500µs space (infrared_protocols.commands.nec).
    action, args = emit_parsed(
        {"protocol": "NEC", "address": "04 00 00 00", "command": "08 00 00 00"}
    )
    assert action == "transmit_raw"
    assert args["carrier_frequency"] == 38000
    assert args["code"][:2] == [9000, -4500]


def test_parsed_sony_encoded_as_raw_timings():
    # Sony SIRC leader is 4T = 2400µs mark, 40kHz carrier.
    action, args = emit_parsed(
        {"protocol": "SIRC", "address": "01 00 00 00", "command": "15 00 00 00"}
    )
    assert action == "transmit_raw"
    assert args["carrier_frequency"] == 40000
    assert args["code"][0] == 2400


def test_parsed_samsung_encoded_as_raw_timings():
    action, args = emit_parsed(
        {"protocol": "Samsung32", "address": "07 00 00 00", "command": "02 00 00 00"}
    )
    assert action == "transmit_raw"
    assert isinstance(args["code"], list) and len(args["code"]) > 2


def test_parsed_unmapped_protocol_returns_none():
    # RC6 isn't one the library encoders cover here -> falls through to skipped.
    assert emit_parsed({"protocol": "RC6", "address": "00", "command": "00"}) is None


def test_mirror_out_preserves_dirs_and_case():
    # The served .yaml must match what a device's files: entry references.
    assert _mirror_out("TVs/Sony/Sony_Bravia.ir") == "TVs/Sony/Sony_Bravia.yaml"
    assert _mirror_out("ACs/LG/LG_AKB.ir") == "ACs/LG/LG_AKB.yaml"


def test_generate_emits_stable_button_id():
    # The Atom-button showcase presses `power` — that id must be stable.
    entries = [{
        "name": "Power", "type": "parsed", "protocol": "SIRC",
        "address": "01 00 00 00", "command": "15 00 00 00",
    }]
    out = generate(entries, "ref", "src", None, "")
    assert "id: ir_power" in out
    assert 'name: "Power"' in out
    assert "transmit_raw" in out
    assert "# TODO unsupported" not in out
