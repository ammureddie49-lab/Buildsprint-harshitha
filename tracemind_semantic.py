"""Opt-in local neural retrieval for TraceMind (never an independent answer generator).

Only caller-authorized records enter this transient index. No disk caching of records
or vectors, no network transport of source content. Model weights may be downloaded
by SentenceTransformers on first use, but source text stays local.

The dependency and model are deliberately optional: the scored deterministic CLI
remains unchanged unless TRACEMIND_SEMANTIC=1 and model fallback is configured.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from typing import Iterable

from tracemind_intelligence import EvidenceIndex

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def enabled() -> bool:
    return os.environ.get("TRACEMIND_SEMANTIC", "").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class HybridHit:
    record: dict
    score: float
    lexical_rank: int | None
    dense_rank: int | None
    dense_similarity: float | None


def _dot(a, b) -> float:
    return float(sum(float(x) * float(y) for x, y in zip(a, b)))


def _norm(x) -> float:
    return math.sqrt(sum(float(v) ** 2 for v in x))


class LocalEmbeddingModel:
    """Lazy local SentenceTransformer; no required runtime dependency."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.environ.get("TRACEMIND_SEMANTIC_MODEL", DEFAULT_MODEL)
        self._model = None

    def encode(self, texts: list[str]):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, trust_remote_code=False)
        # normalize to permit direct cosine (dot-product) similarity
        return self._model.encode(texts, batch_size=16, show_progress_bar=False,
                                  convert_to_numpy=True, normalize_embeddings=True)


class HybridEvidenceRetriever:
    """Fuse FTS5/BM25 lexical ranking with optional dense cosine similarity.

    This class only consumes the supplied authorized records. The host engine must
    filter them for requester, time, organization, visibility and forgetting BEFORE
    calling it. In particular, never pass the raw database to this class.
    """

    def __init__(self, authorized_records: Iterable[dict], embedder=None):
        self.records = [r for r in authorized_records if r.get("id") and r.get("type") != "notification"]
        self.embedder = embedder
        self.model_used = False

    @staticmethod
    def _text(record):
        # Keep a bounded context; do not leak privileged metadata into the model.
        return EvidenceIndex.content(record).strip()[:1200]

    def search(self, question: str, client: str | None = None, limit: int = 18):
        if limit < 1:
            return []
        scoped = [r for r in self.records if client is None or r.get("client") == client]
        if not scoped or not question.strip():
            return []
        lexical = EvidenceIndex(scoped).search(question, client=client, limit=max(40, limit * 3))
        lexical_rank = {x.record["id"]: (i + 1) for i, x in enumerate(lexical)}
        lexical_scores = {x.record["id"]: x.score for x in lexical}
        dense_rank = {}
        dense_scores = {}
        self.model_used = False
        if self.embedder is not None:
            # An injected embedder is useful for offline, deterministic unit tests.
            # In production this is a local SentenceTransformer model.
            matrix = self.embedder.encode([question] + [self._text(r) for r in scoped])
            if len(matrix) != len(scoped) + 1:
                raise ValueError("Embedding model returned the wrong number of vectors")
            query_vector = matrix[0]
            sim=[]
            for i, v in enumerate(matrix[1:]):
                denom = _norm(query_vector) * _norm(v)
                similarity = (_dot(query_vector, v) / denom) if denom else 0.0
                # A minimum similarity avoids promoting irrelevant material based
                # solely on noisy model rank. The threshold is intentionally modest.
                if similarity >= 0.28:
                    sim.append((similarity, scoped[i]["id"]))
            sim.sort(reverse=True)
            for rank, (similarity, record_id) in enumerate(sim, 1):
                dense_rank[record_id] = rank
                dense_scores[record_id] = similarity
            self.model_used = True
        elif not lexical:
            return []
        # Reciprocal rank fusion: one outlier score cannot eclipse both rankers.
        by_id = {r["id"]: r for r in scoped}
        ids = set(lexical_rank) | set(dense_rank)
        scores = []
        for record_id in ids:
            fused = 0.0
            if record_id in lexical_rank:
                fused += 1.0 / (60 + lexical_rank[record_id])
            if record_id in dense_rank:
                fused += 1.0 / (60 + dense_rank[record_id])
            # Evidence retrieval is not a claim-supporting verifier. The LLM and
            # final output validator must still check supported citations.
            scores.append(HybridHit(by_id[record_id], fused, lexical_rank.get(record_id),
                                    dense_rank.get(record_id), dense_scores.get(record_id)))
        return sorted(scores, key=lambda hit:(hit.score,
                         lexical_scores.get(hit.record["id"], 0),
                         hit.record.get("at", "")), reverse=True)[:limit]


def retrieve(question: str, authorized_records: Iterable[dict],
             client: str | None = None, limit: int = 18, embedder=None):
    """Select bounded evidence; fallback to lexical if neural model isn't installed.

    Returns (records, neural_used, reason). The mode is visible to benchmarks and
    operators, instead of silently claiming the neural model actually ran.
    """
    authorized = list(authorized_records)
    if os.environ.get("TRACEMIND_VECTOR_DB", "").strip().lower() in ("1", "true", "yes"):
        # Only activated explicitly, and only for permission-filtered evidence
        # supplied by the original CLI's model-fallback branch.
        from tracemind_vector_db import retrieve as vector_retrieve
        return vector_retrieve(question, authorized, client=client, limit=limit, embedder=embedder)
    if embedder is None and enabled():
        embedder = LocalEmbeddingModel()
    retriever = HybridEvidenceRetriever(authorized, embedder)
    try:
        hits = retriever.search(question, client=client, limit=limit)
        return [h.record for h in hits], retriever.model_used, None
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        # If dependency or local model is unavailable, keep the secure lexical
        # fallback and report the reason. Never fall back to unfiltered records.
        lexical = EvidenceIndex(authorized).search(question, client=client, limit=limit)
        return [hit.record for hit in lexical], False, f"{type(exc).__name__}: {exc}"
