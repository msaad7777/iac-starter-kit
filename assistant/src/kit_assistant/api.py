"""HTTP API. Binds to 127.0.0.1 only (see __init__.serve)."""
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .pipeline import RAG

app = FastAPI(title="kit-assistant", version="0.1.0")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@lru_cache(maxsize=1)
def rag() -> RAG:
    return RAG()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
def ask(q: Question) -> dict:
    ans = rag().ask(q.question).to_dict()
    for c in ans["contexts"]:
        c["text"] = c["text"][:400]
    return ans
