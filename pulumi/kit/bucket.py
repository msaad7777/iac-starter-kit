"""SecureBucket: the Pulumi version of modules/s3-bucket, with the same defaults."""
import json
import re

import pulumi
import pulumi_aws as aws


class SecureBucket(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        bucket_name: str,
        tags: dict[str, str],
        versioning: bool = True,
        kms_key_arn: str | None = None,
        intelligent_tiering_after_days: int = 30,
        noncurrent_version_expiration_days: int = 90,
        opts: pulumi.ResourceOptions | None = None,
    ):
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket_name):
            raise ValueError("bucket_name must be a valid S3 bucket name")
        if intelligent_tiering_after_days < 0:
            raise ValueError("intelligent_tiering_after_days must be 0 or more")
        super().__init__("kit:storage:SecureBucket", name, None, opts)
        child = pulumi.ResourceOptions(parent=self)

        self.bucket = aws.s3.Bucket(name, bucket=bucket_name, tags=tags, opts=child)

        self.public_access_block = aws.s3.BucketPublicAccessBlock(
            f"{name}-pab",
            bucket=self.bucket.id,
            block_public_acls=True,
            block_public_policy=True,
            ignore_public_acls=True,
            restrict_public_buckets=True,
            opts=child,
        )

        aws.s3.BucketOwnershipControls(
            f"{name}-ownership",
            bucket=self.bucket.id,
            rule={"object_ownership": "BucketOwnerEnforced"},
            opts=child,
        )

        self.encryption = aws.s3.BucketServerSideEncryptionConfiguration(
            f"{name}-sse",
            bucket=self.bucket.id,
            rules=[
                {
                    "apply_server_side_encryption_by_default": {
                        "sse_algorithm": "aws:kms" if kms_key_arn else "AES256",
                        "kms_master_key_id": kms_key_arn,
                    },
                    "bucket_key_enabled": kms_key_arn is not None,
                }
            ],
            opts=child,
        )

        versioning_res = aws.s3.BucketVersioning(
            f"{name}-versioning",
            bucket=self.bucket.id,
            versioning_configuration={"status": "Enabled" if versioning else "Suspended"},
            opts=child,
        )

        rules = [
            {
                "id": "abort-incomplete-uploads",
                "status": "Enabled",
                "filter": {},
                "abort_incomplete_multipart_upload": {"days_after_initiation": 7},
            }
        ]
        if intelligent_tiering_after_days > 0:
            rules.append(
                {
                    "id": "intelligent-tiering",
                    "status": "Enabled",
                    "filter": {},
                    "transitions": [{"days": intelligent_tiering_after_days, "storage_class": "INTELLIGENT_TIERING"}],
                }
            )
        if versioning:
            rules.append(
                {
                    "id": "expire-noncurrent-versions",
                    "status": "Enabled",
                    "filter": {},
                    "noncurrent_version_expiration": {"noncurrent_days": noncurrent_version_expiration_days},
                }
            )
        self.lifecycle = aws.s3.BucketLifecycleConfiguration(
            f"{name}-lifecycle",
            bucket=self.bucket.id,
            rules=rules,
            opts=pulumi.ResourceOptions(parent=self, depends_on=[versioning_res]),
        )

        self.policy = aws.s3.BucketPolicy(
            f"{name}-tls-only",
            bucket=self.bucket.id,
            policy=self.bucket.arn.apply(
                lambda arn: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "DenyInsecureTransport",
                                "Effect": "Deny",
                                "Principal": "*",
                                "Action": "s3:*",
                                "Resource": [arn, f"{arn}/*"],
                                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                            }
                        ],
                    }
                )
            ),
            opts=pulumi.ResourceOptions(parent=self, depends_on=[self.public_access_block]),
        )

        self.register_outputs({"id": self.bucket.id, "arn": self.bucket.arn})
