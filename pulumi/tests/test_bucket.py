"""Unit tests with Pulumi mocks: no cloud account, no Pulumi Cloud login, no provider plugin."""
import pulumi
import pytest


class Mocks(pulumi.runtime.Mocks):
    def new_resource(self, args: pulumi.runtime.MockResourceArgs):
        outputs = dict(args.inputs)
        if args.typ == "aws:s3/bucket:Bucket":
            outputs["arn"] = f"arn:aws:s3:::{args.inputs['bucket']}"
        return [f"{args.name}_id", outputs]

    def call(self, args: pulumi.runtime.MockCallArgs):
        return {}


pulumi.runtime.set_mocks(Mocks(), preview=False)

from kit.bucket import SecureBucket  # noqa: E402  (mocks must be set before import)
from kit.tags import standard_tags  # noqa: E402

TAGS = standard_tags("CC-1234", "platform-team", "dev", "checkout")


def resolve(*outputs):
    """Wait for Pulumi outputs inside a test."""
    return pulumi.Output.all(*outputs)


@pulumi.runtime.test
def test_public_access_fully_blocked():
    b = SecureBucket("t1", bucket_name="acme-dev-test-1", tags=TAGS)

    def check(v):
        assert all(v), "every public access flag must be true"

    return resolve(
        b.public_access_block.block_public_acls,
        b.public_access_block.block_public_policy,
        b.public_access_block.ignore_public_acls,
        b.public_access_block.restrict_public_buckets,
    ).apply(check)


@pulumi.runtime.test
def test_sse_s3_by_default_and_bucket_key_with_kms():
    plain = SecureBucket("t2", bucket_name="acme-dev-test-2", tags=TAGS)
    kms = SecureBucket("t3", bucket_name="acme-dev-test-3", tags=TAGS, kms_key_arn="arn:aws:kms:us-east-1:111122223333:key/abc")

    def check(v):
        plain_rule, kms_rule = v[0][0], v[1][0]
        assert plain_rule["apply_server_side_encryption_by_default"]["sse_algorithm"] == "AES256"
        assert kms_rule["apply_server_side_encryption_by_default"]["sse_algorithm"] == "aws:kms"
        assert kms_rule["bucket_key_enabled"] is True

    return resolve(plain.encryption.rules, kms.encryption.rules).apply(check)


@pulumi.runtime.test
def test_lifecycle_rules_follow_settings():
    full = SecureBucket("t4", bucket_name="acme-dev-test-4", tags=TAGS)
    bare = SecureBucket("t5", bucket_name="acme-dev-test-5", tags=TAGS, versioning=False, intelligent_tiering_after_days=0)

    def check(v):
        assert [r["id"] for r in v[0]] == ["abort-incomplete-uploads", "intelligent-tiering", "expire-noncurrent-versions"]
        assert [r["id"] for r in v[1]] == ["abort-incomplete-uploads"]

    return resolve(full.lifecycle.rules, bare.lifecycle.rules).apply(check)


@pulumi.runtime.test
def test_tls_only_policy_and_tags():
    b = SecureBucket("t6", bucket_name="acme-dev-test-6", tags=TAGS)

    def check(v):
        policy, tags = v
        assert '"aws:SecureTransport": "false"' in policy
        assert tags["cost-center"] == "CC-1234" and tags["managed-by"] == "pulumi"

    return resolve(b.policy.policy, b.bucket.tags).apply(check)


def test_rejects_bad_bucket_name():
    with pytest.raises(ValueError):
        SecureBucket("bad", bucket_name="Bad_Bucket", tags=TAGS)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cost_center": "marketing"},
        {"environment": "qa"},
        {"extra": {"owner": "someone-else"}},
    ],
)
def test_tag_validation(kwargs):
    base = dict(cost_center="CC-1234", owner="platform-team", environment="dev", service="checkout")
    base.update(kwargs)
    with pytest.raises(ValueError):
        standard_tags(**base)
