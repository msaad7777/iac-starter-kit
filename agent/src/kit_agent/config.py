"""Paths and settings. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

AGENT = Path(__file__).resolve().parents[2]
KIT_ROOT = Path(os.getenv("KIT_ROOT", AGENT.parent))
RUNS = AGENT / "runs"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:20b")
NUM_CTX = int(os.getenv("NUM_CTX", "8192"))
THINK = os.getenv("THINK", "low")
LLM_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT_S", "600"))

MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))   # gate runs (plan + policies) per request
MAX_TURNS = int(os.getenv("MAX_TURNS", "24"))        # LLM calls per request

ENVIRONMENTS = ("dev", "staging", "prod")             # the tags module only accepts these
REGION = "us-east-1"
PROD_APPROVAL_LABEL = "prod-approved"
BRANCH_PREFIX = os.getenv("AGENT_BRANCH_PREFIX", "agent/")
