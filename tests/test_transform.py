"""Unit tests for the codegen's YAML rendering + git-serving helpers.

Parsing/encoding lives in homeops-ir-adapter and naming in homeops-ir-canonical
(each with their own tests). Here we cover render() and the git smart-protocol
helpers. render() consumes ir_adapter.Signal-like objects, so a tiny fake stands
in — no ir-adapter (Python 3.14) needed to exercise rendering.
"""

from flipper_ir_to_esphome import (
    _device_name,
    _id_prefix,
    _key,
    _mirror_out,
    _repo_from_path,
    _v2_command,
    _valid_repo,
    _wanted_refs,
    render,
)


class Sig:
    """Minimal stand-in for ir_adapter.Signal (render only reads these fields)."""

    def __init__(self, name, carrier_hz=38000, timings=(100, -200), repeat=1):
        self.name = name
        self.carrier_hz = carrier_hz
        self.timings = timings
        self.repeat = repeat


def _pkt(payload):
    """Encode one git pkt-line (4 hex length bytes covering themselves)."""
    b = payload.encode() if isinstance(payload, str) else payload
    return f"{len(b) + 4:04x}".encode() + b


# --- git smart-protocol helpers ------------------------------------------------

def test_v2_ls_refs_yields_wanted_branch():
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
    body = _pkt("command=fetch\n") + b"0001" + _pkt("want 0123abcd\n") + b"0000"
    assert _v2_command(body) == "fetch"
    assert _wanted_refs(body) == []


def test_repo_from_path_and_validation():
    assert _repo_from_path("/HomeOps/Flipper-IRDB.git/git-upload-pack") == "HomeOps/Flipper-IRDB"
    assert _repo_from_path("/ha-ir.git/info/refs") == "ha-ir"
    assert _repo_from_path("/x.github/repo.git/info/refs") == "x.github/repo"
    assert _repo_from_path("/nope") is None
    assert _valid_repo("HomeOps/Flipper-IRDB")
    assert not _valid_repo("ha-ir")
    assert not _valid_repo("a/b/c")
    assert not _valid_repo("../../etc/passwd")


def test_mirror_out_preserves_dirs_and_case():
    assert _mirror_out("TVs/Sony/Sony_Bravia.ir") == "TVs/Sony/Sony_Bravia.yaml"
    assert _mirror_out("ACs/LG/LG_AKB.ir") == "ACs/LG/LG_AKB.yaml"


# --- id prefix / device name ---------------------------------------------------

def test_id_prefix_from_path():
    assert _id_prefix("KVMs/Generic_8K_HDMI_DP_4Port_KVM.ir") == "kvm_generic"
    assert _id_prefix("TVs/Sony/Sony_Bravia.ir") == "tv_sony_bravia"
    assert _id_prefix("TVs/LG/LG_AKB.ir") == "tv_lg_akb"
    assert _id_prefix("vizio/tv") == "vizio_tv"
    assert _id_prefix("Samsung_TV.ir") == "samsung"
    assert _id_prefix("") == "ir"


def test_device_name_drops_category_keeps_case():
    assert _device_name("TVs/Sony/Sony_Bravia.ir") == "Sony Bravia"
    assert _device_name("KVMs/Generic_8K_HDMI_DP_4Port_KVM.ir") == "Generic"
    assert _device_name("TVs/LG/LG_AKB.ir") == "LG AKB"
    assert _device_name("") == "IR"


# --- canonical key + render ----------------------------------------------------

def test_key_resolves_canonical_else_slug():
    assert _key("Power") == "power_toggle"
    assert _key("VOL+") == "volume_up"
    assert _key("Vol_up") == "volume_up"
    assert _key("Custom Thing") == "custom_thing"     # unmapped -> sanitized slug


def test_render_uses_canonical_ids_and_subdevice():
    out = render([Sig("Power", 40000, (2400, -600), repeat=3)],
                 "TVs/Sony/Sony_Bravia.ir", "Lucaslhm/Flipper-IRDB@main")
    assert 'esphome:\n  devices:\n    - id: tv_sony_bravia\n      name: "Sony Bravia"\n' in out
    assert "id: tv_sony_bravia_power_toggle" in out
    assert 'name: "Power"' in out
    assert "device_id: tv_sony_bravia" in out
    assert "times: 3" in out          # parsed -> transmit-layer repeat


def test_render_dedupes_same_canonical_first_wins():
    out = render([Sig("Vol_up"), Sig("VOLUME_UP")], "TVs/Sony/Sony_Bravia.ir", "x")
    assert out.count("id: tv_sony_bravia_volume_up") == 1


def test_render_raw_has_no_repeat_but_parsed_does():
    raw = render([Sig("Custom", 38000, (100, -200), repeat=1)], "TVs/Sony/Sony_Bravia.ir", "x")
    assert "repeat:" not in raw
    parsed = render([Sig("Power", 40000, (2400, -600), repeat=3)], "TVs/Sony/Sony_Bravia.ir", "x")
    assert "repeat:" in parsed and "times: 3" in parsed


def test_render_each_component_gets_distinct_subdevice():
    sony = render([Sig("Power")], "TVs/Sony/Sony_Bravia.ir", "x")
    samsung = render([Sig("Power")], "TVs/Samsung/Samsung_QLED.ir", "x")
    assert 'id: tv_sony_bravia\n      name: "Sony Bravia"' in sony
    assert 'id: tv_samsung_qled\n      name: "Samsung QLED"' in samsung
    assert _id_prefix("TVs/Sony/Sony_Bravia.ir") != _id_prefix("TVs/Samsung/Samsung_QLED.ir")
