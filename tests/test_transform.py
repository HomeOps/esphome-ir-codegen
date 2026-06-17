"""Unit tests for the Flipper .ir -> ESPHome transformer.

Parsed protocols are encoded by the infrared-protocols library and emitted as
transmit_raw, so these assert the raw timings the library returns (its protocol
correctness is covered by its own test suite). Requires the library installed
(Python >= 3.14).
"""

from flipper_ir_to_esphome import (
    _ha_ir_codesets,
    _id_prefix,
    _mirror_out,
    _repo_from_path,
    _slug,
    _v2_command,
    _valid_repo,
    _wanted_refs,
    emit_parsed,
    emit_raw,
    generate,
    generate_from_commands,
    parse_ir,
)


def _pkt(payload):
    """Encode one git pkt-line (4 hex length bytes covering themselves)."""
    b = payload.encode() if isinstance(payload, str) else payload
    return f"{len(b) + 4:04x}".encode() + b


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


def test_v2_ls_refs_yields_wanted_branch():
    # The ref is per-device: it only appears in the protocol-v2 ls-refs request,
    # where git sends several ref-prefix lines to resolve `<ref>`.
    body = (
        _pkt("command=ls-refs\n") + b"0001"
        + _pkt("ref-prefix refs/heads/main\n")
        + _pkt("ref-prefix refs/tags/main\n")
        + _pkt("ref-prefix main\n") + b"0000"
    )
    assert _v2_command(body) == "ls-refs"
    assert _wanted_refs(body) == ["main"]


def test_wanted_refs_keeps_slashed_branch():
    body = _pkt("command=ls-refs\n") + b"0001" + _pkt("ref-prefix refs/heads/feat/x\n") + b"0000"
    assert _wanted_refs(body) == ["feat/x"]


def test_v2_fetch_has_no_wanted_refs():
    # The follow-up fetch carries no ref-prefix; the branch was built at ls-refs.
    body = _pkt("command=fetch\n") + b"0001" + _pkt("want 0123abcd\n") + b"0000"
    assert _v2_command(body) == "fetch"
    assert _wanted_refs(body) == []


def test_repo_from_path_and_validation():
    # The flipper source repo is the URL path; ha-ir is a reserved single segment.
    assert _repo_from_path("/HomeOps/Flipper-IRDB.git/git-upload-pack") == "HomeOps/Flipper-IRDB"
    assert _repo_from_path("/ha-ir.git/info/refs") == "ha-ir"
    assert _repo_from_path("/x.github/repo.git/info/refs") == "x.github/repo"  # .github != .git boundary
    assert _repo_from_path("/nope") is None
    assert _valid_repo("HomeOps/Flipper-IRDB")
    assert not _valid_repo("ha-ir")                 # reserved, not a flipper source
    assert not _valid_repo("a/b/c")                 # exactly one slash allowed
    assert not _valid_repo("../../etc/passwd")      # no traversal


def test_id_prefix_from_path():
    # Button ids are namespaced by '<category>_<brand>' derived from the path:
    # the category drops its trailing 's', the brand keeps only the first token.
    assert _id_prefix("KVMs/Generic_8K_HDMI_DP_4Port_KVM.ir") == "kvm_generic"
    assert _id_prefix("TVs/Sony/Sony_Bravia.ir") == "tv_sony"
    assert _id_prefix("vizio/tv") == "vizio_tv"          # ha-ir layout
    assert _id_prefix("Samsung_TV.ir") == "samsung"      # single segment -> brand only
    assert _id_prefix("") == "ir"                        # fallback keeps a leading letter


def test_slug_uses_prefix_and_dodges_reserved_words():
    assert _slug("Power", "kvm_generic") == "kvm_generic_power"
    assert _slug("1", "kvm_generic") == "kvm_generic_1"   # leading-letter guarantee
    assert _slug("Return", "tv_sony") == "tv_sony_return"


def test_generate_emits_stable_button_id():
    # The Atom-button showcase presses the Sony power button — its id is the
    # path-namespaced `tv_sony_power` and must be stable.
    entries = [{
        "name": "Power", "type": "parsed", "protocol": "SIRC",
        "address": "01 00 00 00", "command": "15 00 00 00",
    }]
    out = generate(entries, "ref", "TVs/Sony/Sony_Bravia.ir", None, "")
    assert "id: tv_sony_power" in out
    assert 'name: "Power"' in out
    assert "transmit_raw" in out
    assert "# TODO unsupported" not in out


def test_generate_from_commands_renders_raw_with_repeat():
    # ha-ir adapter: a library Command -> transmit_raw + transmit-layer repeat.
    from infrared_protocols.commands.nec import NECCommand

    out = generate_from_commands([("POWER", NECCommand(address=0x04, command=0x08))], "vizio/tv")
    assert "id: vizio_tv_power" in out
    assert "transmit_raw" in out
    assert "repeat:" in out and "times: 3" in out
    assert "code: [9000, -4500" in out      # NEC leader from the library


def test_generate_from_commands_dedupes_ids():
    from infrared_protocols.commands.nec import NECCommand

    out = generate_from_commands(
        [("POWER", NECCommand(address=0x04, command=0x08)),
         ("Power", NECCommand(address=0x04, command=0x09))],   # same slug -> vizio_tv_power
        "vizio/tv",
    )
    assert out.count("id: vizio_tv_power") == 1


def test_ha_ir_codesets_includes_vizio_tv_power():
    # The ha-ir adapter discovers infrared-protocols' own curated code sets.
    sets = dict(_ha_ir_codesets())
    assert "vizio/tv" in sets
    names = {name for name, _cmd in sets["vizio/tv"]}
    assert "POWER" in names


def test_generate_repeats_parsed_but_not_raw():
    # Library frames are single -> the transmit layer must repeat them (Sony
    # SIRC needs ~3 frames). A raw capture is authoritative and sent as-is.
    parsed = generate(
        [{"name": "Power", "type": "parsed", "protocol": "SIRC",
          "address": "01 00 00 00", "command": "15 00 00 00"}],
        "ref", "src", None, "",
    )
    assert "repeat:" in parsed
    assert "times: 3" in parsed

    raw = generate(
        [{"name": "Power", "type": "raw", "frequency": "40000", "data": "100 200"}],
        "ref", "src", None, "",
    )
    assert "repeat:" not in raw
