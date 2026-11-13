"""Fast unit tests: no Ollama, no Terraform, no AWS mock. A scripted LLM and fake gates
stand in for the model and for scripts/plan-json.sh and scripts/check-policies.sh."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from kit_agent import catalog, config, provision
from kit_agent.agent import Agent, pr_body, stated_amounts
from kit_agent.gates import PlanResult, PolicyResult, UnsafeTarget, local_env, parse_policy_output
from kit_agent.llm import ScriptedLLM, call
from kit_agent.workspace import Refused, ToolError, Workspace, hcl_value, render_unit, safe_path

KIT = Path(__file__).resolve().parents[2]
REQ = "a staging environment for team payments with a private bucket and a $200 budget"
TAGS = {"service": "payments", "data-classification": "confidential", "owner": "payments-team"}
BUCKET = {"name": "acme-staging-payments-data", "tags": TAGS}
BUDGET = {"name": "acme-staging-payments", "monthly_limit_usd": 200,
          "alert_emails": ["finops@example.com"], "tags": TAGS}


@pytest.fixture
def kit(tmp_path):
    """A throwaway git repo holding the kit's real modules/ and live/ folders."""
    root = tmp_path / "kit"
    for d in ("modules", "live", "scripts"):
        shutil.copytree(KIT / d, root / d, ignore=shutil.ignore_patterns(".terraform*", ".terragrunt-cache", ".state"))
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "kit"], check=True, env=env)
    return root


def bucket_plan():
    """A minimal plan JSON in Terraform's shape: a bucket and two resources that configure it."""
    def rc(t, n):
        return {"address": f"{t}.{n}", "mode": "managed", "type": t, "name": n, "change": {"actions": ["create"]}}
    ref = {"bucket": {"references": ["aws_s3_bucket.this.id", "aws_s3_bucket.this"]}}
    return {"resource_changes": [rc("aws_s3_bucket", "this"), rc("aws_s3_bucket_versioning", "this"),
                                 rc("aws_s3_bucket_public_access_block", "this")],
            "configuration": {"root_module": {"resources": [
                {"address": "aws_s3_bucket.this", "mode": "managed", "type": "aws_s3_bucket", "expressions": {}},
                {"address": "aws_s3_bucket_versioning.this", "mode": "managed", "type": "aws_s3_bucket_versioning", "expressions": ref},
                {"address": "aws_s3_bucket_public_access_block.this", "mode": "managed",
                 "type": "aws_s3_bucket_public_access_block", "expressions": ref}]}}}


class FakeGates:
    """Plan fails if a unit file has a marker; policies fail on a second NAT gateway outside prod."""

    def __init__(self):
        self.plans = self.policy_runs = 0

    def _units(self, root):
        return list((root / "live").glob("*/us-east-1/*/terragrunt.hcl"))

    def plan(self, root, envs):
        self.plans += 1
        for u in self._units(root):
            if "PLAN_ERROR" in u.read_text():
                return PlanResult(False, error="Error: Invalid value for variable")
        (root / "plans").mkdir(exist_ok=True)
        for u in self._units(root):
            if u.parts[-4] in envs:
                (root / "plans" / f"{u.parts[-4]}-{u.parts[-2]}.json").write_text(json.dumps(bucket_plan()))
        plans = {f"{u.parts[-4]}-{u.parts[-2]}": {"actions": {"create": 3}, "types": {"aws_s3_bucket": 1}}
                 for u in self._units(root) if u.parts[-4] in envs}
        return PlanResult(True, plans, seconds=0.1)

    def policies(self, root):
        self.policy_runs += 1
        files = {}
        for u in self._units(root):
            bad = '"per_az"' in u.read_text() and u.parts[-4] != "prod"
            files[f"{u.parts[-4]}-{u.parts[-2]}.json"] = {
                "pass": 4 if bad else 5, "fail": int(bad),
                "violations": ["3 NAT gateways planned outside prod (limit 1)"] if bad else []}
        return PolicyResult(not any(f["fail"] for f in files.values()), files, 0.1)


def happy_script():
    return [call("list_modules"),
            call("create_env", env="staging", owner="payments-team", cost_center="CC-1234"),
            call("write_unit", env="staging", unit="payments-bucket", module="s3-bucket", inputs=BUCKET),
            call("write_unit", env="staging", unit="payments-budget", module="budget", inputs=BUDGET),
            call("run_plan"), call("run_policies"),
            call("finish", title="staging for payments",
                 reasons=["private bucket", {"unit": "payments-budget", "reason": "$200 budget as asked"}])]


# ---- catalog ---------------------------------------------------------------------------------
def test_catalog_reads_the_kit_modules_and_hides_injected_inputs():
    mods = catalog.load(KIT)
    assert set(mods) == {"budget", "gpu-inference", "network", "s3-bucket"}  # tags has no resources
    assert mods["s3-bucket"].required() == {"name", "tags"}
    assert mods["budget"].required() == {"name", "monthly_limit_usd", "alert_emails", "tags"}
    assert mods["network"].required() == {"name", "cidr", "azs", "tags"}          # region comes from root.hcl
    assert "subnet_ids" not in mods["gpu-inference"].settable()                  # from the network dependency
    assert "nat_strategy" in catalog.describe(mods)


# ---- the write rules -------------------------------------------------------------------------
@pytest.mark.parametrize("rel", ["../outside.tf", "/etc/passwd", "modules/s3-bucket/main.tf", "live",
                                 "live/_envcommon/budget.hcl", "live/root.hcl", "live/dev/../../x.tf"])
def test_writes_outside_live_are_refused(kit, rel):
    with pytest.raises(Refused):
        safe_path(kit, rel)


def test_symlink_out_of_live_is_refused(kit, tmp_path):
    (kit / "live" / "escape").symlink_to(tmp_path)
    with pytest.raises(Refused):
        safe_path(kit, "live/escape/x.hcl")


def test_kit_owned_units_cannot_be_overwritten(kit):
    ws = Workspace(kit, "dev bucket, $10 budget")
    with pytest.raises(ToolError, match="belongs to the kit"):
        ws.write_unit("dev", "budget", "budget", {**BUDGET, "monthly_limit_usd": 10})


def test_unknown_module_is_a_hard_refusal(kit):
    with pytest.raises(Refused, match="unknown module"):
        Workspace(kit, "rds").write_unit("dev", "orders-db", "rds", {})


def test_unknown_and_missing_variables_go_back_to_the_model(kit):
    ws = Workspace(kit, "x")
    with pytest.raises(ToolError, match="no variable"):
        ws.write_unit("dev", "x-bucket", "s3-bucket", {**BUCKET, "acl": "public-read"})
    with pytest.raises(ToolError, match="needs name"):
        ws.write_unit("dev", "x-bucket", "s3-bucket", {"tags": TAGS})


def test_invented_arns_and_ids_are_rejected_but_given_ones_pass(kit):
    ws = Workspace(kit, "dev bucket with key arn:aws:kms:us-east-1:111122223333:key/real, $10 budget")
    with pytest.raises(ToolError, match="never invent"):
        ws.write_unit("dev", "a-bucket", "s3-bucket", {**BUCKET, "kms_key_arn": "arn:aws:kms:us-east-1:123:key/made-up"})
    assert ws.write_unit("dev", "a-bucket", "s3-bucket",
                         {**BUCKET, "kms_key_arn": "arn:aws:kms:us-east-1:111122223333:key/real"})["ok"]
    gpu = {"name": "a", "ami_id": "ami-0123456789abcdef0", "tags": TAGS}      # the kit's placeholder
    assert ws.write_unit("dev", "a-gpu", "gpu-inference", gpu, network_unit="a-net")["ok"]


def test_second_anomaly_monitor_is_rejected(kit):
    with pytest.raises(ToolError, match="one anomaly monitor"):
        Workspace(kit, "x").write_unit("dev", "x-budget", "budget", {**BUDGET, "anomaly_detection": True})


def test_a_stated_on_demand_share_cannot_be_silently_changed(kit):
    gpu = {"name": "a", "ami_id": "ami-0123456789abcdef0", "tags": TAGS}
    ws = Workspace(kit, "dev GPU inference with 100 percent on-demand, $50 budget")
    with pytest.raises(ToolError, match="states 100 percent on-demand"):
        ws.write_unit("dev", "a-gpu", "gpu-inference", {**gpu, "on_demand_percentage_above_base": 50}, network_unit="a-net")
    assert ws.write_unit("dev", "a-gpu", "gpu-inference", {**gpu, "on_demand_percentage_above_base": 100},
                         network_unit="a-net")["ok"]   # written as asked; the policy gate then fails it
    ws = Workspace(kit, "dev GPU inference, all spot, $50 budget")         # nothing stated: no check
    assert ws.write_unit("dev", "b-gpu", "gpu-inference", {**gpu, "on_demand_percentage_above_base": 0},
                         network_unit="a-net")["ok"]


def test_ollama_retries_once_on_a_server_error(monkeypatch):
    import io
    import urllib.error
    from kit_agent import llm as llm_mod
    replies = [urllib.error.HTTPError("u", 500, "boom", {}, None),
               io.BytesIO(json.dumps({"message": {"role": "assistant", "content": "ok"}}).encode())]

    class Resp:
        def __init__(self, b): self.b = b
        def __enter__(self): return self.b
        def __exit__(self, *a): return False

    def fake(req, timeout):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return Resp(r)
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", fake)
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    o = llm_mod.Ollama()
    assert o.chat([], [])["content"] == "ok" and o.retries == 1


def test_prod_needs_the_approval_label(kit):
    with pytest.raises(Refused, match="prod-approved"):
        Workspace(kit, "prod bucket").write_unit("prod", "p-bucket", "s3-bucket", BUCKET)
    ws = Workspace(kit, "prod bucket", labels=[config.PROD_APPROVAL_LABEL])
    assert ws.write_unit("prod", "p-bucket", "s3-bucket", BUCKET)["ok"]


def test_gpu_unit_takes_subnets_from_a_network_dependency(kit):
    ws = Workspace(kit, "gpu")
    with pytest.raises(ToolError, match="network_unit"):
        ws.write_unit("dev", "ml-gpu", "gpu-inference", {"name": "a", "ami_id": "ami-0123456789abcdef0", "tags": TAGS})
    ws.write_unit("dev", "ml-gpu", "gpu-inference", {"name": "a", "ami_id": "ami-0123456789abcdef0", "tags": TAGS},
                  network_unit="ml-network")
    text = (kit / "live/dev/us-east-1/ml-gpu/terragrunt.hcl").read_text()
    assert 'config_path = "../ml-network"' in text
    assert re.search(r"subnet_ids\s+= dependency\.network\.outputs\.private_subnet_ids", text)


def test_rendered_values_cannot_inject_templates_or_blocks():
    assert hcl_value("${file(\"/etc/passwd\")}") == '"$${file(\\"/etc/passwd\\")}"'
    text = render_unit("s3-bucket", {"name": "a\n}\nresource \"x\" \"y\" {"}, "req")
    assert "\nresource" not in text and text.count("\n}") == 3


@pytest.mark.skipif(not shutil.which("terragrunt"), reason="terragrunt not installed")
def test_rendered_unit_is_canonically_formatted(kit):
    Workspace(kit, REQ).write_unit("dev", "payments-budget", "budget", BUDGET)
    r = subprocess.run(["terragrunt", "hcl", "format", "--check", "--working-dir", str(kit / "live/dev")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ---- the loop --------------------------------------------------------------------------------
def test_happy_path_ends_with_passing_gates_and_a_pr_body(kit):
    gates = FakeGates()
    res = Agent(ScriptedLLM(happy_script()), gates).run(Workspace(kit, REQ))
    assert res.outcome == "pr" and res.attempts == 1
    assert sorted(res.files) == ["live/staging/env.hcl", "live/staging/us-east-1/payments-bucket/terragrunt.hcl",
                                 "live/staging/us-east-1/payments-budget/terragrunt.hcl", "live/staging/us-east-1/region.hcl"]
    assert res.reasons[1] == "payments-budget — $200 budget as asked"
    body = pr_body(REQ, [], res, "gpt-oss:20b")
    for part in ("## Plan", "## Policy results", "## Why these choices", "`modules/s3-bucket`", "Nothing was applied"):
        assert part in body


def test_policy_failure_is_fixed_and_counted_as_a_second_attempt(kit):
    net = {"name": "acme-staging-checkout", "cidr": "10.30.0.0/16", "azs": ["us-east-1a", "us-east-1b", "us-east-1c"],
           "tags": TAGS}
    budget = {**BUDGET, "monthly_limit_usd": 400}
    script = [call("create_env", env="staging", owner="checkout-team", cost_center="CC-1234"),
              call("write_unit", env="staging", unit="checkout-network", module="network", inputs={**net, "nat_strategy": "per_az"}),
              call("write_unit", env="staging", unit="checkout-budget", module="budget", inputs=budget),
              call("run_plan"), call("run_policies"),
              call("write_unit", env="staging", unit="checkout-network", module="network", inputs={**net, "nat_strategy": "single"}),
              call("run_plan"), call("run_policies"),
              call("finish", title="t", reasons=["one NAT outside prod"])]
    res = Agent(ScriptedLLM(script), FakeGates()).run(Workspace(kit, "staging network for checkout, $400 budget"))
    assert res.outcome == "pr" and res.attempts == 2
    assert [h["ok"] for h in res.history] == [True, False, True, True]
    assert "NAT" in res.history[1]["detail"]


def test_finish_is_blocked_until_gates_pass_after_the_last_write(kit):
    script = happy_script()[:6] + [
        call("write_unit", env="staging", unit="payments-bucket", module="s3-bucket", inputs={**BUCKET, "versioning": False}),
        call("finish", title="t", reasons=[])]
    llm = ScriptedLLM(script)
    res = Agent(llm, FakeGates(), max_turns=len(script)).run(Workspace(kit, REQ))
    assert res.outcome == "failed"
    assert any("finish needs" in str(t.get("result")) for t in res.transcript)


def test_an_invented_budget_is_rejected(kit):
    script = happy_script()
    script[3] = call("write_unit", env="staging", unit="payments-budget", module="budget",
                     inputs={**BUDGET, "monthly_limit_usd": 500})
    res = Agent(ScriptedLLM(script), FakeGates(), max_turns=len(script)).run(Workspace(kit, REQ))
    assert res.outcome == "failed"
    assert any("amount stated in the request" in str(t.get("result")) for t in res.transcript)


def test_no_stated_budget_ends_as_a_guard_refusal(kit):
    res = Agent(ScriptedLLM(happy_script()), FakeGates()).run(Workspace(kit, "staging bucket for team payments"))
    assert res.outcome == "refused" and res.refused_by == "guard"


def test_model_refusal_writes_nothing(kit):
    res = Agent(ScriptedLLM([call("refuse", reason="public buckets are not allowed")]), FakeGates()).run(
        Workspace(kit, "a public bucket, $50 budget"))
    assert res.outcome == "refused" and res.refused_by == "model" and res.files == []


def test_a_tool_call_written_as_json_text_is_accepted_and_counted(kit):
    reply = {"role": "assistant", "content": '```json\n{"name": "refuse", "arguments": {"reason": "no budget"}}\n```'}
    res = Agent(ScriptedLLM([reply]), FakeGates()).run(Workspace(kit, "staging bucket"))
    assert res.outcome == "refused" and res.text_tool_calls == 1
    prose = {"role": "assistant", "content": 'I would call {"name": "refuse"} here'}
    res = Agent(ScriptedLLM([prose] * 3), FakeGates()).run(Workspace(kit, "staging bucket"))
    assert res.outcome == "failed" and res.text_tool_calls == 0


def test_after_the_gates_pass_a_text_reply_is_nudged_to_finish_not_refuse(kit):
    script = happy_script()
    prose = {"role": "assistant", "content": "All checks passed."}
    script = script[:-1] + [prose] + script[-1:]
    llm = ScriptedLLM(script)
    res = Agent(llm, FakeGates()).run(Workspace(kit, REQ))
    assert res.outcome == "pr"
    nudge = llm.seen[-1][-1]["content"]
    assert "Call finish now" in nudge and "refuse" not in nudge and REQ in nudge
    # before any gate has passed the nudge still offers refuse
    llm = ScriptedLLM([prose, call("refuse", reason="x")])
    Agent(llm, FakeGates()).run(Workspace(kit, REQ))
    assert "refuse" in llm.seen[-1][-1]["content"]


def test_prod_write_without_label_stops_the_run(kit):
    script = [call("write_unit", env="prod", unit="p-bucket", module="s3-bucket", inputs=BUCKET),
              call("finish", title="t", reasons=[])]
    res = Agent(ScriptedLLM(script), FakeGates()).run(Workspace(kit, "prod bucket, $500 budget"))
    assert res.outcome == "refused" and res.refused_by == "guard" and res.files == []


def test_attempts_are_capped(kit):
    script = [call("write_unit", env="dev", unit="x-bucket", module="s3-bucket", inputs={**BUCKET, "name": "PLAN_ERROR"})]
    script += [call("run_plan")] * 5
    gates = FakeGates()
    res = Agent(ScriptedLLM(script), gates, max_attempts=3).run(Workspace(kit, "x, $5 budget"))
    assert res.outcome == "failed" and res.attempts == 3 and gates.plans == 3


def test_old_tool_results_are_trimmed_to_fit_the_context():
    agent = Agent(ScriptedLLM([]), FakeGates(), char_budget=2000)
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    msgs += [{"role": "tool", "tool_name": "x", "content": "y" * 900} for _ in range(6)]
    agent._trim(msgs)
    assert msgs[2]["content"] == "[older result trimmed]" and msgs[-1]["content"] == "y" * 900


def test_stated_amounts():
    assert stated_amounts("a $200 budget and 1,500 USD later, 3 AZs") == {200.0, 1500.0}
    assert stated_amounts("keep it cheap") == set()


# ---- gates -----------------------------------------------------------------------------------
def test_gates_only_ever_point_at_a_local_mock():
    env = local_env({"PATH": os.environ["PATH"], "AWS_PROFILE": "real", "AWS_ENDPOINT_URL": "https://s3.amazonaws.com"})
    assert env["KIT_TARGET"] == "moto" and env["AWS_ENDPOINT_URL"].startswith("http://localhost")
    assert "AWS_PROFILE" not in env and env["AWS_ACCESS_KEY_ID"] == "test"
    with pytest.raises(UnsafeTarget):
        local_env({"KIT_TARGET": "emulator", "AWS_ENDPOINT_URL": "https://ec2.us-east-1.amazonaws.com"})
    assert local_env({"KIT_TARGET": "emulator", "PATH": os.environ["PATH"]})["AWS_ENDPOINT_URL"].startswith("https://127.0.0.1")


def test_the_package_never_runs_apply_or_destroy():
    src = "\n".join(p.read_text() for p in (KIT / "agent/src/kit_agent").glob("*.py"))
    assert not re.search(r"""["'](apply|destroy|import)["']""", src)


def test_policy_output_is_parsed_per_plan():
    out = ("== dev-x.json\n1 - validation 2 NAT gateways planned outside prod (limit 1): a, b\n"
           "pass: 4, fail: 1, warn: 0, error: 0, skip: 0 \n== dev-y.json\npass: 5, fail: 0, warn: 0, error: 0, skip: 0 \n")
    files = parse_policy_output(out)
    assert files["dev-x.json"] == {"pass": 4, "fail": 1, "violations": ["2 NAT gateways planned outside prod (limit 1): a, b"]}
    assert files["dev-y.json"]["fail"] == 0


# ---- branch ----------------------------------------------------------------------------------
ADR_JSON = json.dumps({"context": "Payments needs a staging copy.", "options": [
    {"name": "Bucket and budget", "summary": "two kit modules"}, {"name": "Reuse dev", "summary": "no isolation"}],
    "chosen": "Bucket and budget", "rationale": "Private by default.", "consequences": ["one more budget"]})


@pytest.mark.skipif(not shutil.which("dot"), reason="Graphviz not installed")
def test_provision_leaves_one_branch_with_units_adr_and_diagram(kit, tmp_path):
    res, branch, body = provision(REQ, [], llm=ScriptedLLM(happy_script(), [ADR_JSON]), gates=FakeGates(), repo=kit,
                                  out_dir=tmp_path / "run")
    assert res.outcome == "pr" and branch.startswith("agent/a-staging-environment-for-team")
    files = subprocess.run(["git", "-C", str(kit), "show", "--name-only", "--format=%an", branch],
                           capture_output=True, text=True).stdout.split()
    assert files[0] == "kit-agent"
    assert all(f.startswith("live/staging/") or f.startswith("docs/adr/0001-staging-for-payments.") for f in files[1:])
    assert res.adr == "docs/adr/0001-staging-for-payments.md" and res.adr_from_model
    assert res.diagram_stats["coverage"] == 1.0 and res.diagram_stats["folded"] == 4
    assert "docs/adr/0001-staging-for-payments.md" in body
    assert (tmp_path / "run" / "pr-body.md").read_text() == body
    assert subprocess.run(["git", "-C", str(kit), "status", "--porcelain"], capture_output=True, text=True).stdout == ""
    assert "kit-agent-" not in subprocess.run(["git", "-C", str(kit), "worktree", "list"], capture_output=True, text=True).stdout


def test_a_refusal_leaves_no_branch(kit):
    res, branch, _ = provision("public bucket, $5 budget", [], llm=ScriptedLLM([call("refuse", reason="public")]),
                               gates=FakeGates(), repo=kit)
    assert res.outcome == "refused" and branch is None
    assert "agent/" not in subprocess.run(["git", "-C", str(kit), "branch"], capture_output=True, text=True).stdout


def test_an_unparseable_tool_call_goes_back_to_the_model(kit):
    from kit_agent.llm import BadToolCall

    class Flaky(ScriptedLLM):
        def chat(self, messages, tools):
            if self.calls == 2 and not any("not valid JSON" in str(m.get("content")) for m in messages):
                self.calls += 1
                raise BadToolCall('{"error":"error parsing tool call: raw=..., err=invalid character"}')
            return super().chat(messages, tools)
    llm = Flaky(happy_script())
    res = Agent(llm, FakeGates()).run(Workspace(kit, REQ))
    assert res.outcome == "pr" and res.bad_tool_calls == 1
    assert any("not valid JSON" in str(m.get("content")) for m in llm.seen[-1])
