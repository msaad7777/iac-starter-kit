"""Fast unit tests: no models, no network, no index."""
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from kit_assistant import config
from kit_assistant.components import tokenize
from kit_assistant.ingest import clean_markdown, split, split_markdown_sections
from kit_assistant.pipeline import PROMPT, RAG, format_context, normalise_citations, parse_citations


def doc(score: float, n: int = 1) -> Document:
    return Document(page_content=f"Set use_lockfile = true for native S3 locking {n}.", metadata={
        "chunk_id": f"r:p#{n}", "source": "OpenTofu docs", "repo": "opentofu/opentofu",
        "path": "website/docs/language/settings/backends/s3.mdx", "title": "S3", "section": "Locking",
        "url": "u", "licence": "MPL-2.0", "rerank_score": score})


def make_rag(answer: str, docs: list[Document]) -> RAG:
    rag = RAG.__new__(RAG)
    rag.retrieve = lambda q, mode=None, k=config.TOP_K: docs
    rag.chain = PROMPT | FakeListChatModel(responses=[answer])
    return rag


def test_tokenize_keeps_resource_names_split_on_punctuation():
    assert tokenize("What is aws_s3_bucket's use_lockfile?") == ["aws", "s3", "bucket", "s", "use", "lockfile"]


def test_parse_citations_splits_valid_and_invalid():
    valid, invalid = parse_citations("A [1]. B [2, 7]. C [3]", n_sources=5)
    assert valid == {1, 2, 3} and invalid == {7}


def test_markdown_sections_ignore_hashes_in_code_and_keep_indentation():
    text = "## Setup\nintro\n```sh\n# not a heading\n```\n### Nested\n```yaml\nspec:\n  mode: JSON\n```\n## Next\nend"
    sections = split_markdown_sections(text)
    assert [s for s, _ in sections] == ["Setup", "Setup > Nested", "Next"]
    assert "  mode: JSON" in sections[1][1]


def test_clean_markdown_drops_front_matter_and_mdx_imports():
    text = "---\ntitle: X\n---\nimport { Aside } from '@astrojs/starlight/components'\n<Aside>\nBody text\n"
    assert clean_markdown(text) == "Body text"


def test_code_files_split_on_resource_boundaries():
    hcl = "\n".join(f'resource "aws_s3_bucket" "b{i}" {{\n  bucket = "{"x" * 300}"\n}}\n' for i in range(6))
    pieces = [p for _, p in split(hcl, "main.tf")]
    assert len(pieces) > 1 and all(p.lstrip().startswith("resource") for p in pieces)


def test_context_names_source_path_and_section():
    assert format_context([doc(1.0)]).startswith("[1] OpenTofu docs: website/docs/language/settings/backends/s3.mdx > Locking")


def test_retrieval_gate_declines_without_calling_llm():
    rag = make_rag("should never be used [1]", [doc(-9.0)])
    a = rag.ask("What is the capital of Australia?")
    assert a.declined and a.decline_reason.startswith("retrieval_gate") and "generate" not in a.timings_ms


def test_llm_insufficient_context_declines():
    a = make_rag("INSUFFICIENT_CONTEXT", [doc(3.0)]).ask("q?")
    assert a.declined and a.decline_reason == "llm_insufficient_context"


def test_uncited_answer_is_declined():
    a = make_rag("Use native S3 locking.", [doc(3.0)]).ask("q?")
    assert a.declined and a.decline_reason == "no_valid_citation"


def test_invalid_citation_is_stripped_and_valid_kept():
    a = make_rag("Set use_lockfile = true [1]. Also X [9].", [doc(3.0)]).ask("q?")
    assert not a.declined
    assert "[9]" not in a.answer and "[1]" in a.answer
    assert [c["path"] for c in a.citations] == ["website/docs/language/settings/backends/s3.mdx"]


def test_fullwidth_citations_are_normalised():
    assert normalise_citations("A【1】. B【2†L5-L9】.") == "A[1]. B[2]."
    a = make_rag("Set use_lockfile = true【1】.", [doc(3.0)]).ask("q?")
    assert not a.declined and a.answer == "Set use_lockfile = true[1]."
