"""Draw an architecture diagram from Terraform plan JSON, in code. The model never draws it.

- Every managed resource in the plan is drawn: its own icon (one node per resource block,
  "×N" when count makes several), or folded into its parent's node when it only configures
  that parent (bucket versioning, route table associations, ...). Anything else is a miss.
- The provider prefix picks the icon set: aws_ -> AWS, google_ -> GCP, azurerm_ -> Azure.
  Only AWS is exercised end to end; the kit has no GCP or Azure modules, so those mappings
  are only unit-tested.
- Nodes are grouped by environment and unit. Edges come from the references Terraform
  records in the plan's configuration section, plus one edge per Terragrunt dependency.
"""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ICONS = {
    # AWS: every type the kit's modules create
    "aws_vpc": "aws.network.VPC",
    "aws_subnet": "aws.network.PrivateSubnet",
    "aws_internet_gateway": "aws.network.InternetGateway",
    "aws_nat_gateway": "aws.network.NATGateway",
    "aws_eip": "aws.compute.EC2ElasticIpAddress",
    "aws_route_table": "aws.network.RouteTable",
    "aws_vpc_endpoint": "aws.network.Endpoint",
    "aws_flow_log": "aws.network.VPCFlowLogs",
    "aws_s3_bucket": "aws.storage.SimpleStorageServiceS3Bucket",
    "aws_launch_template": "aws.compute.EC2Ami",
    "aws_autoscaling_group": "aws.compute.EC2AutoScaling",
    "aws_autoscaling_schedule": "aws.management.CloudwatchEventTimeBased",
    "aws_budgets_budget": "aws.cost.Budgets",
    "aws_ce_anomaly_monitor": "aws.cost.CostExplorer",
    "aws_instance": "aws.compute.EC2Instance",
    "aws_security_group": "aws.network.Nacl",
    "aws_kms_key": "aws.security.KMS",
    "aws_iam_role": "aws.security.IAMRole",
    # GCP and Azure: mapped and unit-tested only (the kit has no modules for them)
    "google_compute_network": "gcp.network.VPC",
    "google_compute_subnetwork": "gcp.network.VPC",
    "google_compute_router_nat": "gcp.network.NAT",
    "google_storage_bucket": "gcp.storage.GCS",
    "google_compute_instance": "gcp.compute.ComputeEngine",
    "google_compute_instance_group_manager": "gcp.compute.ComputeEngine",
    "google_billing_budget": "gcp.operations.Monitoring",
    "azurerm_virtual_network": "azure.network.VirtualNetworks",
    "azurerm_subnet": "azure.network.Subnets",
    "azurerm_nat_gateway": "azure.networking.Nat",
    "azurerm_storage_account": "azure.storage.StorageAccounts",
    "azurerm_linux_virtual_machine_scale_set": "azure.compute.VMScaleSet",
    "azurerm_consumption_budget_resource_group": "azure.general.Subscriptions",
}
# Resources that only configure another resource: listed on the parent's node, not drawn alone.
FOLD = re.compile(r"^(aws_s3_bucket_\w+|aws_route|aws_route_table_association|aws_ce_anomaly_subscription"
                  r"|aws_vpc_endpoint_route_table_association|google_storage_bucket_iam_\w+"
                  r"|azurerm_subnet_nat_gateway_association)$")
SHORT = {"aws_s3_bucket_server_side_encryption_configuration": "encryption",
         "aws_s3_bucket_lifecycle_configuration": "lifecycle", "aws_s3_bucket_public_access_block": "public access block",
         "aws_s3_bucket_ownership_controls": "ownership", "aws_route_table_association": "associations",
         "aws_ce_anomaly_subscription": "alert subscription"}
PROVIDERS = {"aws_": "aws", "google_": "gcp", "azurerm_": "azure"}
GENERIC = {"aws": "aws.general.General", "gcp": "gcp.compute.ComputeEngine", "azure": "azure.general.Resource"}


def provider_of(rtype: str) -> str | None:
    return next((p for pre, p in PROVIDERS.items() if rtype.startswith(pre)), None)


def icon_path(rtype: str, name: str = "") -> str | None:
    if rtype == "aws_subnet" and "public" in name:
        return "aws.network.PublicSubnet"
    return ICONS.get(rtype)


def icon_class(path: str):
    mod, cls = path.rsplit(".", 1)
    return getattr(importlib.import_module(f"diagrams.{mod}"), cls)


def _config_resources(module: dict, prefix: str = "") -> dict[str, dict]:
    out = {f"{prefix}{r['address']}": r for r in module.get("resources", []) if r.get("mode") == "managed"}
    for name, call in module.get("module_calls", {}).items():
        out.update(_config_resources(call.get("module", {}), f"{prefix}module.{name}."))
    return out


def _base(address: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", address)


@dataclass
class Node:
    key: str            # "<plan>/<config address>"
    rtype: str
    name: str
    count: int = 0
    folded: list[str] = field(default_factory=list)
    icon: str | None = None


@dataclass
class Model:
    clusters: dict[str, dict[str, list[Node]]] = field(default_factory=dict)  # env -> unit -> nodes
    edges: set[tuple[str, str]] = field(default_factory=set)
    drawn: list[str] = field(default_factory=list)     # plan addresses with their own icon
    folded: list[str] = field(default_factory=list)    # plan addresses shown on a parent's node
    missed: list[str] = field(default_factory=list)    # plan addresses with no icon at all

    def coverage(self) -> float:
        total = len(self.drawn) + len(self.folded) + len(self.missed)
        return (len(self.drawn) + len(self.folded)) / total if total else 1.0


def build(plans: dict[str, dict], units: list[dict]) -> Model:
    """plans: {"<env>-<unit>": plan JSON}. units: the agent's units (env, unit, network_unit)."""
    m = Model()
    unit_of = {f"{u['env']}-{u['unit']}": u for u in units}
    first_node: dict[str, str] = {}
    for plan_name, plan in plans.items():
        u = unit_of.get(plan_name, {"env": plan_name.split("-")[0], "unit": plan_name})
        conf = _config_resources(plan.get("configuration", {}).get("root_module", {}))
        nodes: dict[str, Node] = {}
        changes = [rc for rc in plan.get("resource_changes", []) if rc.get("mode") == "managed"]
        # pass 1: resources with their own node
        for rc in changes:
            base = _base(rc["address"])
            if FOLD.match(rc["type"]):
                continue
            node = nodes.setdefault(base, Node(f"{plan_name}/{base}", rc["type"], rc.get("name", ""),
                                               icon=icon_path(rc["type"], rc.get("name", ""))))
            node.count += 1
            (m.drawn if node.icon else m.missed).append(f"{plan_name}/{rc['address']}")
        # pass 2: fold configuration resources into the node they reference
        for rc in changes:
            if not FOLD.match(rc["type"]):
                continue
            base = _base(rc["address"])
            refs = [_base(r) for e in conf.get(base, {}).get("expressions", {}).values()
                    for r in (e.get("references", []) if isinstance(e, dict) else [])]
            parent = next((nodes[r] for r in refs if r in nodes), None)
            if parent is None:
                m.missed.append(f"{plan_name}/{rc['address']}")
                continue
            label = SHORT.get(rc["type"], rc["type"].removeprefix("aws_s3_bucket_").removeprefix("aws_").replace("_", " "))
            if label not in parent.folded:
                parent.folded.append(label)
            m.folded.append(f"{plan_name}/{rc['address']}")
        # edges between drawn nodes, from configuration references
        for base, node in nodes.items():
            for expr in conf.get(base, {}).get("expressions", {}).values():
                for ref in (expr.get("references", []) if isinstance(expr, dict) else []):
                    tgt = _base(ref)
                    for cand in (tgt, tgt.rsplit(".", 1)[0]):
                        if cand in nodes and cand != base:
                            m.edges.add((nodes[cand].key, node.key))
                            break
            for dep in conf.get(base, {}).get("depends_on", []):
                if _base(dep) in nodes:
                    m.edges.add((nodes[_base(dep)].key, node.key))
        m.clusters.setdefault(u["env"], {})[u["unit"]] = list(nodes.values())
        if nodes:
            first_node[plan_name] = next(iter(nodes.values())).key
    # Terragrunt dependencies between units (gpu-inference takes subnets from a network unit)
    for u in units:
        net = u.get("network_unit")
        src = first_node.get(f"{u['env']}-{net}") if net else None
        dst = [n.key for n in m.clusters.get(u["env"], {}).get(u["unit"], []) if n.rtype == "aws_autoscaling_group"]
        if src and dst:
            m.edges.add((src, dst[0]))
    return m


def render(model: Model, title: str, out_png: Path) -> Path:
    from diagrams import Cluster, Diagram, Edge

    out_png.parent.mkdir(parents=True, exist_ok=True)
    made = {}
    attrs = {"fontsize": "20", "pad": "0.4", "splines": "spline", "nodesep": "0.5", "ranksep": "0.9"}
    with Diagram(title, filename=str(out_png.with_suffix("")), outformat="png", show=False,
                 direction="LR", graph_attr=attrs):
        for env, units in model.clusters.items():
            with Cluster(f"{env}"):
                for unit, nodes in units.items():
                    with Cluster(unit):
                        for n in nodes:
                            label = n.name + (f" ×{n.count}" if n.count > 1 else "")
                            label = f"{n.rtype.removeprefix('aws_')}\n{label}"
                            if n.folded:
                                rows = [", ".join(n.folded[i:i + 2]) for i in range(0, len(n.folded), 2)]
                                label += "\n+ " + "\n".join(rows)
                            path = n.icon or GENERIC[provider_of(n.rtype) or "aws"]
                            made[n.key] = icon_class(path)(label)
        for a, b in sorted(model.edges):
            if a in made and b in made:
                cross = a.split("/")[0] != b.split("/")[0]
                made[a] >> Edge(style="dashed" if cross else "solid", color="#475569") >> made[b]
    return out_png


def from_plan_files(plans_dir: Path, units: list[dict]) -> dict[str, dict]:
    names = {f"{u['env']}-{u['unit']}" for u in units}
    return {p.stem: json.loads(p.read_text()) for p in sorted(plans_dir.glob("*.json")) if p.stem in names}
