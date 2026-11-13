"""A minimal Ollama chat client with tool calling, standard library only.

Anything with a `chat(messages, tools) -> dict` method works; tests use a scripted fake."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from . import config


class BadToolCall(Exception):
    """Ollama could not parse the model's tool call (it answers HTTP 500 "error parsing tool
    call"). At temperature 0 a plain retry repeats the same bad JSON, so the agent sends the
    parser error back to the model instead."""


class Ollama:
    def __init__(self, model: str = config.LLM_MODEL, url: str = config.OLLAMA_URL,
                 num_ctx: int = config.NUM_CTX, think: str | bool = config.THINK,
                 timeout_s: int = config.LLM_TIMEOUT_S):
        self.model, self.url, self.num_ctx, self.think, self.timeout_s = model, url, num_ctx, think, timeout_s
        self.calls = self.last_prompt_tokens = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.retries = 0

    def _post(self, body: dict) -> dict:
        """POST to /api/chat. One retry on a 5xx: the Ollama server is shared with other jobs
        and returned a 500 once during eval run 2."""
        req = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:600] if e.fp else ""
                if "error parsing tool call" in detail:
                    raise BadToolCall(detail) from e
                if e.code < 500 or attempt:
                    raise
                self.retries += 1
                time.sleep(5)
        raise RuntimeError("unreachable")

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        body = {"model": self.model, "messages": messages, "tools": tools, "stream": False,
                "think": self.think, "options": {"temperature": 0, "num_ctx": self.num_ctx}}
        data = self._post(body)
        self.calls += 1
        self.last_prompt_tokens = data.get("prompt_eval_count", 0)
        self.prompt_tokens += self.last_prompt_tokens
        self.output_tokens += data.get("eval_count", 0)
        return data["message"]

    def complete(self, messages: list[dict], schema: dict) -> str:
        """One call with no tools whose reply must match a JSON schema (Ollama structured output)."""
        body = {"model": self.model, "messages": messages, "stream": False, "think": self.think,
                "format": schema, "options": {"temperature": 0, "num_ctx": self.num_ctx}}
        data = self._post(body)
        self.calls += 1
        return data["message"]["content"]


class ScriptedLLM:
    """Replays a fixed list of assistant messages. Used by the tests instead of Ollama."""

    def __init__(self, replies: list[dict], completions: list[str] | None = None):
        self.replies = list(replies)
        self.completions = list(completions or [])
        self.seen: list[list[dict]] = []
        self.calls = self.prompt_tokens = self.output_tokens = 0

    def chat(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        self.calls += 1
        if not self.replies:
            return {"role": "assistant", "content": "(script exhausted)"}
        return self.replies.pop(0)

    def complete(self, messages, schema):
        self.calls += 1
        return self.completions.pop(0) if self.completions else "not json"


def call(name: str, **arguments) -> dict:
    """Build one assistant message that calls one tool, in Ollama's shape."""
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}
