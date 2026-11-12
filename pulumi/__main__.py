"""Example stack: one secure, tagged bucket for model artifacts."""
import pulumi

from kit.bucket import SecureBucket
from kit.tags import standard_tags

cfg = pulumi.Config()
env = pulumi.get_stack()

tags = standard_tags(
    cost_center=cfg.require("costCenter"),
    owner=cfg.require("owner"),
    environment=env,
    service="llm-platform",
    data_classification="confidential",
)

artifacts = SecureBucket("model-artifacts", bucket_name=f"acme-{env}-pulumi-model-artifacts", tags=tags)

pulumi.export("bucket", artifacts.bucket.id)
