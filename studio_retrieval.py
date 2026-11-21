"""Request-scoped hybrid evidence retrieval for the optional TraceMind Studio.

Models are loaded once per long-lived API process. Embeddings are cached separately
per (person, as-of day, client, exact accessible record IDs). Never cache a larger
access scope and reuse it for another person. Source evidence never leaves the machine.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict

from tracemind_intelligence import EvidenceIndex


class StudioRetrieval:
    def __init__(self, max_scopes=10):
        self._lock = threading.RLock()
        self._model = None
        self._scopes = OrderedDict()
        self._qdrant_embedder = None
        self.max_scopes = max_scopes

    @staticmethod
    def text(record):
        return EvidenceIndex.content(record).strip()[:1200]

    def search(self, query, records, person, day, client=None, mode="lexical", limit=7):
        begin = time.perf_counter()
        records = [r for r in records if r.get("id") and r.get("type") != "notification" and (client is None or r.get("client") == client)]
        # True persistent vector DB, independently selected from the transient
        # neural mode. The vector store indexes TEAM records only and always
        # re-applies the authorized current record allow-list at query time.
        if mode == 'vector':
            from tracemind_vector_db import retrieve as vector_retrieve
            from tracemind_semantic import LocalEmbeddingModel
            with self._lock:
                if self._qdrant_embedder is None:
                    self._qdrant_embedder = LocalEmbeddingModel()
                selected, used, error = vector_retrieve(
                    query, records, client=client, limit=limit,
                    embedder=self._qdrant_embedder,
                )
            output = [
                {"id": r["id"], "type": r.get("type"), "client": r.get("client"),
                 "title": r.get("title") or r.get("subject") or r.get("type", "Record").title(),
                 "excerpt": (r.get("body") or "")[:200],
                 "score": None, "semantic_similarity": None}
                for r in selected
            ]
            return {"mode": "qdrant" if used else "lexical",
                    "neural_used": used, "vector_db_used": used,
                    "latency_ms": round((time.perf_counter()-begin)*1000, 1),
                    "error": error, "evidence": output}
        lexical = EvidenceIndex(records).search(query, client=client, limit=max(35, limit * 4))
        lexrank = {h.record["id"]: i + 1 for i, h in enumerate(lexical)}
        dense_rank, similarity = {}, {}
        neural_used, error = False, None
        if mode == "hybrid" and records:
            try:
                import numpy as np
                from tracemind_semantic import DEFAULT_MODEL
                from sentence_transformers import SentenceTransformer
                with self._lock:
                    if self._model is None:
                        # trust_remote_code=False; download only model weights, not work records.
                        self._model = SentenceTransformer(DEFAULT_MODEL, trust_remote_code=False)
                    ids = "|".join(r["id"] for r in records)
                    digest = hashlib.sha256(ids.encode("utf-8")).hexdigest()
                    key = (person, int(day), client, digest)
                    if key in self._scopes:
                        vectors = self._scopes[key]
                        self._scopes.move_to_end(key)
                    else:
                        texts = [self.text(r) for r in records]
                        vectors = self._model.encode(texts, batch_size=24, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
                        self._scopes[key] = vectors
                        while len(self._scopes) > self.max_scopes:
                            self._scopes.popitem(last=False)
                    qvec = self._model.encode([query], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)[0]
                    sims = np.asarray(vectors) @ np.asarray(qvec)
                order = sorted(range(len(records)), key=lambda i: float(sims[i]), reverse=True)
                rank = 1
                for idx in order:
                    if float(sims[idx]) < 0.28:
                        continue
                    rid = records[idx]["id"]
                    dense_rank[rid] = rank
                    similarity[rid] = float(sims[idx])
                    rank += 1
                neural_used = True
            except (ImportError, RuntimeError, ValueError, OSError) as exc:
                error = f"Neural model unavailable: {type(exc).__name__}"
        by_id = {r["id"]:r for r in records}
        found = set(lexrank) | set(dense_rank)
        scores = {rid: (1.0/(60+lexrank[rid]) if rid in lexrank else 0) +
                        (1.0/(60+dense_rank[rid]) if rid in dense_rank else 0) for rid in found}
        # Always return authorized evidence only; never generate factual claims here.
        ordered = sorted(found, key=lambda rid:(scores[rid],by_id[rid].get('at','')), reverse=True)[:limit]
        output = [{"id":rid,"type":by_id[rid].get('type'),"client":by_id[rid].get('client'),
                   "title":by_id[rid].get('title') or by_id[rid].get('subject') or by_id[rid].get('type','Record').title(),
                   "excerpt":(by_id[rid].get('body') or '')[:200],
                   "score":round(scores[rid],5),
                   "semantic_similarity":round(similarity[rid],3) if rid in similarity else None} for rid in ordered]
        return {"mode":"hybrid" if neural_used else "lexical", "neural_used":neural_used,
                "latency_ms":round((time.perf_counter()-begin)*1000,1),"error":error,
                "evidence":output}


retriever = StudioRetrieval()
