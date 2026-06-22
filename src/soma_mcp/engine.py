"""
engine.py — the retrieval engine interface SOMA MCP depends on.

The production SOMA server backs these methods with a real pipeline (pgvector
search, Haiku relevance filtering, multi-step orchestration, a notes store and a
feedback log). This reference repository ships that engine as an *interface*
(`Engine`) plus a small, dependency-free `InMemoryEngine` so the MCP server runs
and its tests pass without the proprietary retrieval stack.

Swap `InMemoryEngine` for your own implementation of `Engine` to put the same
nine MCP tools in front of your own memory.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Engine(Protocol):
    """Everything the MCP tool kernel needs from a memory backend.

    Tuple return shapes mirror the production pipeline so the kernel logic is
    identical whether it runs on the real engine or the in-memory reference.
    """

    # --- read ---
    def search(self, query: str) -> tuple[list[str], list[str], list[dict], str]:
        """Return (documents, ids, metadatas, keyword) for a raw vector search."""

    def filter_relevant(self, query: str, docs: list[str], ids: list[str]
                        ) -> tuple[list[str], list[str], str]:
        """Relevance-filter a candidate pool. Return (docs, ids, explanation)."""

    def get_chunk(self, chunk_id: str) -> dict | None:
        """Return a single chunk as {"id", "text", "meta"} or None."""

    def assemble_context(self, question: str, deep: bool
                        ) -> tuple[str, list[str], list[dict], str]:
        """Run the full retrieval pipeline. Return (text, ids, metas, status)."""

    # --- write ---
    def add_note(self, text: str) -> int:
        """Store a new note; return the number of chunks written."""

    def full_note(self, base_id: str) -> tuple[str | None, str]:
        """Return (text, date) for a note's base id, or (None, "") if absent."""

    def update_note(self, base_id: str, new_text: str) -> tuple[int | None, int]:
        """Overwrite a note. Return (new_chunks, old_chunks); (None, old) = no-op."""

    def delete_note(self, base_id: str) -> int:
        """Delete a note and return how many chunks were removed."""

    def log_feedback(self, question: str, answer: str, verdict: str,
                     causes: list[str], comment: str, source_ids: list[str]) -> None:
        """Append a dogfood-feedback record to a log (not to memory)."""


class InMemoryEngine:
    """A tiny, dependency-free Engine for local runs, demos and tests.

    Substring "search", no real embeddings or LLM. Notes live in a dict keyed by
    base id. This exists so the server and its tests run out of the box — it is
    not a substitute for a real retrieval pipeline.
    """

    def __init__(self) -> None:
        # base_id -> {"text", "date", "meta"}
        self._notes: dict[str, dict] = {}
        self.feedback: list[dict] = []
        self._seq = 0

    # --- read ---
    def search(self, query: str):
        q = query.lower()
        docs, ids, metas = [], [], []
        for bid, n in self._notes.items():
            if q in n["text"].lower() or not q:
                cid = f"{bid}-0"
                docs.append(n["text"])
                ids.append(cid)
                metas.append(n["meta"])
        return docs, ids, metas, query

    def filter_relevant(self, query, docs, ids):
        # The reference keeps everything; a real engine would prune here.
        return docs, ids, "in-memory engine: no LLM filtering applied"

    def get_chunk(self, chunk_id):
        base = chunk_id.rsplit("-", 1)[0]
        n = self._notes.get(base)
        if not n:
            return None
        return {"id": chunk_id, "text": n["text"], "meta": n["meta"]}

    def assemble_context(self, question, deep):
        docs, ids, metas, _ = self.search(question)
        text = "\n\n".join(docs)
        status = f"in-memory: {len(docs)} chunk(s){' (deep)' if deep else ''}"
        return text, ids, metas, status

    # --- write ---
    def add_note(self, text):
        self._seq += 1
        base_id = f"note-ref-{self._seq:04d}"
        self._notes[base_id] = {
            "text": text, "date": "2026-01-01",
            "meta": {"herkomst": "note", "datum": "2026-01-01",
                     "domein": "", "gesprekstitel": ""},
        }
        return 1

    def full_note(self, base_id):
        n = self._notes.get(base_id)
        return (n["text"], n["date"]) if n else (None, "")

    def update_note(self, base_id, new_text):
        n = self._notes.get(base_id)
        if not n:
            return None, 0
        if n["text"] == new_text:
            return None, 1
        n["text"] = new_text
        return 1, 1

    def delete_note(self, base_id):
        return 1 if self._notes.pop(base_id, None) else 0

    def log_feedback(self, question, answer, verdict, causes, comment, source_ids):
        self.feedback.append({
            "question": question, "answer": answer, "verdict": verdict,
            "causes": causes, "comment": comment, "source_ids": source_ids,
        })
