"""Paths and settings. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parents[2]
KIT_ROOT = ASSISTANT.parent
DATA = ASSISTANT / "data"
CORPUS = DATA / "corpus"
MANIFEST = DATA / "manifest.json"
CHUNKS = DATA / "chunks.jsonl"
CHROMA_DIR = DATA / "chroma"
SOURCES = ASSISTANT / "sources.json"

KIT_REPO_URL = os.getenv("KIT_REPO_URL", "https://github.com/msaad7777/iac-starter-kit")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:20b")

CANDIDATES = int(os.getenv("CANDIDATES", "30"))
TOP_K = int(os.getenv("TOP_K", "5"))
DECLINE_THRESHOLD = float(os.getenv("DECLINE_THRESHOLD", "-2.0"))
