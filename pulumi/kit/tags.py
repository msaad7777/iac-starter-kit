"""Standard FinOps tags, the same rules as modules/tags in Terraform."""
import re

STANDARD_KEYS = {"cost-center", "owner", "environment", "service", "data-classification", "managed-by"}
ENVIRONMENTS = {"dev", "staging", "prod"}
CLASSES = {"public", "internal", "confidential", "restricted"}


def standard_tags(
    cost_center: str,
    owner: str,
    environment: str,
    service: str,
    data_classification: str = "internal",
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    if not re.fullmatch(r"CC-\d{4}", cost_center):
        raise ValueError("cost_center must look like CC-1234")
    if not owner.strip():
        raise ValueError("owner must not be empty")
    if environment not in ENVIRONMENTS:
        raise ValueError("environment must be dev, staging or prod")
    if data_classification not in CLASSES:
        raise ValueError("data_classification must be public, internal, confidential or restricted")
    extra = extra or {}
    clash = STANDARD_KEYS & extra.keys()
    if clash:
        raise ValueError(f"extra must not redefine standard tag keys: {sorted(clash)}")
    return {
        "cost-center": cost_center,
        "owner": owner,
        "environment": environment,
        "service": service,
        "data-classification": data_classification,
        "managed-by": "pulumi",
        **extra,
    }
