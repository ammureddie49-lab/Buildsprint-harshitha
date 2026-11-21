"""Qdrant-backed, persistent semantic evidence retrieval for TraceMind.

Qdrant local mode needs no server, API key, or OpenAI dependency.
The store receives ONLY previously authorized records, and deliberately indexes
only TEAM records. It stores opaque IDs and metadata, NOT raw record bodies.

Important: every query uses an allow-list of CURRENTLY authorized record IDs,
then rechecks every returned ID against that allow-list. This provides live
forget/time/permission enforcement even for older persisted vector points.
The caller is responsible for passing Engine.allowed(person, at).

The scorer's original route is unchanged unless TRACEMIND_VECTOR_DB=1.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import threading
import uuid
from typing import Iterable

from tracemind_intelligence import EvidenceIndex
from tracemind_semantic import DEFAULT_MODEL, LocalEmbeddingModel

_COLLECTION_PREFIX = "tracemind_shared_"
_LOCK = threading.RLock()


@dataclass(frozen=True)
class VectorHit:
    record: dict
    score: float
    rank: int


def enabled() -> bool:
    return os.environ.get("TRACEMIND_VECTOR_DB", "").strip().lower() in ("1", "true", "yes")


def db_path(root: Path | str | None = None) -> Path:
    custom = os.environ.get("TRACEMIND_QDRANT_PATH")
    return Path(custom).expanduser().resolve() if custom else (Path(root or Path.cwd()).resolve() / ".tracemind-qdrant")


def _as_vector(v):
    result = [float(n) for n in v]
    if not result or not all(__import__("math").isfinite(v) for v in result):
        raise ValueError("Embedding returned an empty or nonfinite vector")
    return result


def _point_id(org: str, source_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "tracemind/shared/" + org + "/" + source_id))


def _content(row: dict) -> str:
    return EvidenceIndex.content(row).strip()[:1200]


class QdrantEvidenceStore:
    """Embedded local Qdrant with incremental upserts and strict query scoping.

    ``client`` / ``models`` / ``embedder`` injection exists for independent tests.
    A real run imports qdrant_client lazily, so the official offline CLI never
    needs this optional package.
    """

    def __init__(self, path=None, embedder=None, client=None, models=None):
        self.path = db_path() if path is None else Path(path)
        self.embedder = embedder or LocalEmbeddingModel()
        self.client = client
        self.models = models
        self._owned = False
        self.model_name = str(getattr(self.embedder, "model_name", DEFAULT_MODEL))
        digest = hashlib.sha256(self.model_name.encode("utf-8")).hexdigest()[:12]
        self.collection = _COLLECTION_PREFIX + digest
        self.last_indexed = 0

    def _open(self):
        if self.client is None:
            from qdrant_client import QdrantClient, models
            self.path.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(self.path))
            self.models = models
            self._owned = True
        elif self.models is None:
            from qdrant_client import models
            self.models = models
        return self.client, self.models

    def close(self):
        if self._owned and self.client is not None:
            self.client.close()
            self.client = None
            self._owned = False

    @staticmethod
    def _eligible(rows: Iterable[dict], client_filter=None):
        unique = {}
        for row in rows:
            # Exclude personal or restricted source material from persistent
            # embedding storage, regardless of whether one user may read it.
            if not row.get("id") or row.get("visibility", "team") != "team":
                continue
            if row.get("type") == "notification" or not row.get("org"):
                continue
            if client_filter is not None and row.get("client") != client_filter:
                continue
            unique[(row["org"], row["id"])] = row
        return list(unique.values())

    def search(self, question: str, authorized_records: Iterable[dict], client=None, limit=10) -> list[VectorHit]:
        if not question.strip() or limit <= 0:
            return []
        eligible = self._eligible(authorized_records, client)
        if not eligible:
            return []
        orgs = {r["org"] for r in eligible}
        if len(orgs) != 1:
            # Never accidentally search or index mixed organizations as one scope.
            raise ValueError("Qdrant query must contain one authorized organization")
        org = next(iter(orgs))
        with _LOCK:
            db, m = self._open()
            query_vector = _as_vector(self.embedder.encode([question])[0])
            if not db.collection_exists(self.collection):
                db.create_collection(
                    collection_name=self.collection,
                    vectors_config=m.VectorParams(size=len(query_vector), distance=m.Distance.COSINE),
                )

            by_point = {_point_id(org, row["id"]): row for row in eligible}
            point_ids = list(by_point)
            stored = db.retrieve(collection_name=self.collection, ids=point_ids,
                                 with_payload=True, with_vectors=False)
            by_stored_id = {str(p.id): p for p in stored}
            to_encode = []
            hashes = {}
            for pid, row in by_point.items():
                body = _content(row)
                fp = hashlib.sha256((body + "\0" + str(row.get("at")) + "\0" +
                                     str(row.get("client"))).encode("utf-8")).hexdigest()
                hashes[pid] = fp
                previous = by_stored_id.get(pid)
                if previous is None or (previous.payload or {}).get("fingerprint") != fp:
                    to_encode.append((pid, row, body))
            if to_encode:
                # Model call is batched; vectors are persisted across runs.
                embeddings = self.embedder.encode([body for _, _, body in to_encode])
                if len(embeddings) != len(to_encode):
                    raise ValueError("Wrong embedding batch length")
                points = []
                for (pid, row, _), vector in zip(to_encode, embeddings):
                    v = _as_vector(vector)
                    if len(v) != len(query_vector):
                        raise ValueError("Embedding dimension mismatch")
                    points.append(m.PointStruct(id=pid, vector=v, payload={
                        "source_id": row["id"], "org": org,
                        "client": row.get("client") or "", "at": row.get("at") or "",
                        "fingerprint": hashes[pid],
                    }))
                db.upsert(collection_name=self.collection, points=points, wait=True)
            self.last_indexed = len(to_encode)
            must = [
                m.FieldCondition(key="org", match=m.MatchValue(value=org)),
                m.HasIdCondition(has_id=point_ids),
            ]
            if client is not None:
                must.append(m.FieldCondition(key="client", match=m.MatchValue(value=client)))
            response = db.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=m.Filter(must=must),
                limit=max(1, int(limit)),
                with_payload=True,
                with_vectors=False,
            )
            results = []
            for found in response.points:
                # Defense in depth: never trust vector backend filtering as ACL.
                pid = str(found.id)
                row = by_point.get(pid)
                if row is None or (found.payload or {}).get("source_id") != row["id"]:
                    continue
                if row["org"] != org or (client is not None and row.get("client") != client):
                    continue
                score = float(found.score)
                # Same modest cosine threshold as the existing MiniLM retriever.
                if score < 0.28:
                    continue
                results.append(VectorHit(record=row, score=score, rank=len(results) + 1))
            return results[:limit]


def retrieve(question: str, authorized_records: Iterable[dict], client=None, limit=18, embedder=None,
             path=None, client_obj=None, models=None):
    """Return (records, used_vector_db, error) with a safe lexical fallback.

    This deliberately never broadens access to make vector results appear good.
    """
    records = list(authorized_records)
    store = QdrantEvidenceStore(path=path, embedder=embedder, client=client_obj, models=models)
    try:
        hits = store.search(question, records, client=client, limit=limit)
        lexical = EvidenceIndex(records).search(question, client=client, limit=max(limit * 3, 30))
        dense_rank = {h.record["id"]: i + 1 for i, h in enumerate(hits)}
        lexical_rank = {h.record["id"]: i + 1 for i, h in enumerate(lexical)}
        authorized = {r["id"]: r for r in records if r.get("id")}
        scores = {}
        for rid in set(dense_rank) | set(lexical_rank):
            if rid not in authorized:
                continue
            scores[rid] = ((1 / (60 + dense_rank[rid]) if rid in dense_rank else 0) +
                           (1 / (60 + lexical_rank[rid]) if rid in lexical_rank else 0))
        ordered = sorted(scores, key=scores.get, reverse=True)[:limit]
        return [authorized[rid] for rid in ordered], True, None
    except (ImportError, OSError, ValueError, RuntimeError, TypeError) as exc:
        fallback = EvidenceIndex(records).search(question, client=client, limit=limit)
        return [h.record for h in fallback], False, f"Qdrant unavailable: {type(exc).__name__}: {exc}"
    finally:
        store.close()
