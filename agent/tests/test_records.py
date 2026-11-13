"""Diagram mapping, ADR facts and the ADR-status CI check. No Ollama needed."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from kit_agent import adr, catalog, plandiagram
from kit_agent.llm import ScriptedLLM

KIT = Path(__file__).resolve().parents[2]


def kit_resource_types() -> set[str]:
    import re
    return {t for p in (KIT / "modules").glob("*/main.tf") for t in re.findall(r'^resource "(\w+)"', p.read_text(), re.M)}


def test_every_resource_type_in_the_kit_has_an_icon_or_a_parent():
    types = kit_resource_types()
    assert len(types) >= 20
    missing = [t for t in types if not (plandiagram.icon_path(t) or plandiagram.FOLD.match(t))]
    assert missing == []


@pytest.mark.parametrize("path", sorted(set(plandiagram.ICONS.values()) | set(plandiagram.GENERIC.values())
                                        | {"aws.network.PublicSubnet"}))
def test_every_icon_path_is_a_real_diagrams_class(path):
    from diagrams import Node
    cls = plandiagram.icon_class(path)          # some names are aliases, e.g. gcp GCS -> Storage
    assert issubclass(cls, Node) and cls._icon


@pytest.mark.parametrize("rtype, provider, icon", [
    ("aws_s3_bucket", "aws", "aws.storage.SimpleStorageServiceS3Bucket"),
    ("google_storage_bucket", "gcp", "gcp.storage.GCS"),
    ("google_compute_network", "gcp", "gcp.network.VPC"),
    ("azurerm_storage_account", "azure", "azure.storage.StorageAccounts"),
    ("azurerm_virtual_network", "azure", "azure.network.VirtualNetworks"),
])
def test_provider_prefix_picks_the_icon_set(rtype, provider, icon):
    assert plandiagram.provider_of(rtype) == provider
    assert plandiagram.icon_path(rtype) == icon and icon.startswith(provider + ".")


def test_public_subnets_get_the_public_subnet_icon():
    assert plandiagram.icon_path("aws_subnet", "public") == "aws.network.PublicSubnet"
    assert plandiagram.icon_path("aws_subnet", "private") == "aws.network.PrivateSubnet"


def _rc(addr, t, actions=("create",)):
    return {"address": addr, "mode": "managed", "type": t, "name": addr.split(".")[1].split("[")[0],
            "change": {"actions": list(actions)}}


def test_build_counts_drawn_folded_and_missed_and_draws_reference_edges():
    plan = {"resource_changes": [
        _rc("aws_vpc.this", "aws_vpc"), _rc("aws_subnet.private[0]", "aws_subnet"), _rc("aws_subnet.private[1]", "aws_subnet"),
        _rc("aws_route_table_association.private[0]", "aws_route_table_association"),
        _rc("aws_route_table.private", "aws_route_table"), _rc("aws_mystery.x", "aws_mystery")],
        "configuration": {"root_module": {"resources": [
            {"address": "aws_subnet.private", "mode": "managed", "expressions": {"vpc_id": {"references": ["aws_vpc.this.id", "aws_vpc.this"]}}},
            {"address": "aws_route_table_association.private", "mode": "managed",
             "expressions": {"route_table_id": {"references": ["aws_route_table.private"]}}}]}}}
    m = plandiagram.build({"dev-net": plan}, [{"env": "dev", "unit": "net", "module": "network"}])
    assert len(m.drawn) == 4 and len(m.folded) == 1 and m.missed == ["dev-net/aws_mystery.x"]
    assert round(m.coverage(), 3) == round(5 / 6, 3)
    assert ("dev-net/aws_vpc.this", "dev-net/aws_subnet.private") in m.edges
    subnet = [n for n in m.clusters["dev"]["net"] if n.rtype == "aws_subnet"][0]
    assert subnet.count == 2


def test_gpu_unit_gets_an_edge_from_its_network_unit():
    net = {"resource_changes": [_rc("aws_vpc.this", "aws_vpc")], "configuration": {}}
    gpu = {"resource_changes": [_rc("aws_autoscaling_group.this", "aws_autoscaling_group")], "configuration": {}}
    units = [{"env": "dev", "unit": "n"}, {"env": "dev", "unit": "g", "network_unit": "n"}]
    m = plandiagram.build({"dev-n": net, "dev-g": gpu}, units)
    assert ("dev-n/aws_vpc.this", "dev-g/aws_autoscaling_group.this") in m.edges


@pytest.mark.skipif(not shutil.which("dot"), reason="Graphviz not installed")
def test_render_writes_a_png(tmp_path):
    m = plandiagram.build({"dev-b": {"resource_changes": [_rc("aws_s3_bucket.this", "aws_s3_bucket")]}},
                          [{"env": "dev", "unit": "b"}])
    out = plandiagram.render(m, "t", tmp_path / "x.png")
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ---- ADR -------------------------------------------------------------------------------------
def test_replace_counts_as_one_add_and_one_destroy():
    assert adr.counts({"create": 3, "update": 1, "delete": 2, "delete+create": 1, "read": 4, "no-op": 9}) == (4, 1, 3)


UNITS = [{"env": "staging", "unit": "p-bucket", "module": "s3-bucket", "inputs": {}},
         {"env": "staging", "unit": "p-budget", "module": "budget", "inputs": {}}]
PLANS = {"staging-p-bucket": {"actions": {"create": 7, "read": 1}}, "staging-p-budget": {"actions": {"create": 1}}}
POLICIES = {"staging-p-bucket.json": {"pass": 5, "fail": 0}, "staging-p-budget.json": {"pass": 5, "fail": 0}}


def test_adr_is_proposed_and_its_facts_round_trip():
    draft = adr.Draft({"context": "c", "options": [{"name": "A", "summary": "a"}], "chosen": "A",
                       "rationale": "r", "consequences": ["x"]}, True)
    md = adr.render(1, "Payments staging", "req", [], UNITS, PLANS, POLICIES, "0001-x.png", draft, "2026-11-12")
    facts = adr.parse_facts(md)
    assert facts["status"] == "Proposed"
    assert facts["units"] == {"p-bucket": ("staging", "s3-bucket", 7, 0, 0), "p-budget": ("staging", "budget", 1, 0, 0)}
    assert "![Plan diagram](0001-x.png)" in md and "2 of 2 plan files pass all 5" in md


def test_bad_model_output_falls_back_to_a_marked_gap():
    d = adr.draft_sections(ScriptedLLM([], ["not json", '{"context": "only"}']), "r", UNITS, [])
    assert not d.from_model and d.sections["context"] == adr.FALLBACK


def test_next_number_follows_existing_adrs(tmp_path):
    (tmp_path / "docs/adr").mkdir(parents=True)
    (tmp_path / "docs/adr/0007-old.md").write_text("x")
    assert adr.next_number(tmp_path) == 8


# ---- the CI check ----------------------------------------------------------------------------
def _repo(tmp_path):
    root = tmp_path / "r"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(KIT / "scripts/check-adr-status.sh", root / "scripts")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    g = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, env=env)
    g("init", "-q", "-b", "main")
    (root / "docs/adr").mkdir(parents=True)
    (root / "docs/adr/0001-old.md").write_text("# 1\n\n- Status: Proposed\n")   # old, untouched by the branch
    g("add", "-A"); g("commit", "-q", "-m", "base")
    g("checkout", "-q", "-b", "feature")
    return root, g


def _check(root):
    return subprocess.run(["bash", "scripts/check-adr-status.sh", "main"], cwd=root, capture_output=True, text=True)


def test_adr_check_fails_while_a_touched_adr_is_proposed_and_passes_once_accepted(tmp_path):
    root, g = _repo(tmp_path)
    f = root / "docs/adr/0002-new.md"
    f.write_text("# 2\n\n- Status: Proposed\n")
    g("add", "-A"); g("commit", "-q", "-m", "agent")
    r = _check(root)
    assert r.returncode == 1 and "0002-new.md is still Proposed" in r.stdout and "0001" not in r.stdout
    f.write_text("# 2\n\n- Status: Accepted\n")
    g("add", "-A"); g("commit", "-q", "-m", "review")
    r = _check(root)
    assert r.returncode == 0 and "ok   docs/adr/0002-new.md" in r.stdout


def test_adr_check_passes_when_no_adr_changes(tmp_path):
    root, g = _repo(tmp_path)
    (root / "x.txt").write_text("x")
    g("add", "-A"); g("commit", "-q", "-m", "other")
    r = _check(root)
    assert r.returncode == 0 and "0 ADR(s) changed" in r.stdout
