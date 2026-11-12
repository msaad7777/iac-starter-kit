"""Split the kit and the fetched docs into chunks and index them in Chroma."""
from __future__ import annotations

import fnmatch
import json
import re
import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from . import config
from .components import FastEmbedEmbeddings

COLLECTION = "iac_kit"
MD_SUFFIXES = (".md", ".mdx", ".markdown")

_text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
_code_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200, chunk_overlap=150,
    separators=["\nresource ", "\nmodule ", "\nvariable ", "\nrun ", "\n- name:", "\n  - ", "\ndef ", "\nclass ", "\n\n", "\n", " "])


def clean_markdown(text: str) -> str:
    """Drop front matter, MDX imports and JSX-only lines; keep prose, tables and code."""
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    lines = [ln for ln in text.splitlines()
             if not re.match(r"^\s*(import|export) .* from ['\"]", ln)
             and not re.match(r"^\s*</?[A-Z][A-Za-z]*[^>]*/?>\s*$", ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def title_of(text: str, path: str) -> str:
    m = re.search(r"^title:\s*[\"']?(.+?)[\"']?\s*$", text, flags=re.M) or re.search(r"^#\s+(.+)$", text, flags=re.M)
    return m.group(1).strip() if m else Path(path).name


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split on #, ## and ### headings, ignoring '#' inside code fences and keeping indentation.

    LangChain's MarkdownHeaderTextSplitter strips leading whitespace from every line, which
    breaks the YAML and HCL examples that matter most in infrastructure docs.
    """
    sections: list[tuple[str, list[str]]] = [("", [])]
    slots: list[str | None] = [None, None, None]
    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,3})\s+(.+?)\s*#*\s*$", line)
        if m:
            level = len(m.group(1))
            slots[level - 1] = m.group(2).strip()
            for i in range(level, 3):
                slots[i] = None
            sections.append((" > ".join(x for x in slots if x), [line]))
        else:
            sections[-1][1].append(line)
    return [(name, "\n".join(lines).strip()) for name, lines in sections if "\n".join(lines).strip()]


def split(text: str, path: str) -> list[tuple[str, str]]:
    """Return (section, chunk text) pairs."""
    if path.endswith(MD_SUFFIXES):
        out = []
        for section, body in split_markdown_sections(clean_markdown(text)):
            for piece in _text_splitter.split_text(body):
                out.append((section, piece))
        return out
    return [("", piece) for piece in _code_splitter.split_text(text)]


def kit_files() -> list[Path]:
    patterns = json.loads(config.SOURCES.read_text())["kit"]["include"]
    files = []
    for p in sorted(config.KIT_ROOT.rglob("*")):
        rel = p.relative_to(config.KIT_ROOT).as_posix()
        if p.is_file() and any(fnmatch.fnmatch(rel, pat) for pat in patterns) and "/." not in "/" + rel:
            files.append(p)
    return files


def collect() -> list[Document]:
    docs: list[Document] = []

    def add(text: str, *, source: str, repo: str, path: str, url: str, licence: str):
        title = title_of(text, path)
        for k, (section, piece) in enumerate(split(text, path)):
            if len(piece.strip()) < 80:
                continue
            docs.append(Document(page_content=piece, metadata={
                "chunk_id": f"{repo}:{path}#{k}", "source": source, "repo": repo, "path": path,
                "title": title, "section": section, "url": url, "licence": licence}))

    for f in kit_files():
        rel = f.relative_to(config.KIT_ROOT).as_posix()
        add(f.read_text(), source="IaC starter kit", repo="kit", path=rel,
            url=f"{config.KIT_REPO_URL}/blob/main/{rel}", licence="MIT")

    manifest = json.loads(config.MANIFEST.read_text())
    for src in manifest["external"]:
        root = config.CORPUS / src["repo"].replace("/", "__")
        for meta in src["files"]:
            text = (root / meta["path"]).read_text()
            add(text, source=src["name"], repo=src["repo"], path=meta["path"],
                url=f"https://github.com/{src['repo']}/blob/{src['sha']}/{meta['path']}", licence=src["licence"])
    return docs


def ingest() -> int:
    docs = collect()
    with config.CHUNKS.open("w") as f:
        for d in docs:
            f.write(json.dumps({"text": d.page_content, **d.metadata}) + "\n")
    if config.CHROMA_DIR.exists():
        shutil.rmtree(config.CHROMA_DIR)
    store = Chroma(collection_name=COLLECTION, embedding_function=FastEmbedEmbeddings(config.EMBED_MODEL),
                   persist_directory=str(config.CHROMA_DIR), collection_metadata={"hnsw:space": "cosine"})
    for i in range(0, len(docs), 256):
        batch = docs[i:i + 256]
        store.add_documents(batch, ids=[d.metadata["chunk_id"] for d in batch])
    by_source: dict[str, int] = {}
    for d in docs:
        by_source[d.metadata["source"]] = by_source.get(d.metadata["source"], 0) + 1
    for s, n in sorted(by_source.items()):
        print(f"  {s}: {n} chunks")
    return len(docs)
