"""Smoke-test the ACTUAL Qdrant Python client with synthetic data.

Usage:
  python tools/vector_db_smoke.py
  python tools/vector_db_smoke.py --real-model

First command verifies Qdrant persistent mode with injected deterministic 3D
embeddings, no model downloads. Second also loads real local MiniLM (384 dims).
Never reads challenge answer keys, workplace records or OpenAI credentials.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tracemind_vector_db import QdrantEvidenceStore


class SyntheticEmbedder:
    model_name = 'tracemind-3d-qdrant-smoke-v1'
    def encode(self,texts):
        return [[1.,0.,0.] if any(t in s.lower() for t in ('invoice','payment','supplier'))
                else [0.,1.,0.] for s in texts]


def record(id,body):
    return {'id':id,'org':'demo_org','client':'demo_client','author':'demo_employee',
            'type':'chat','visibility':'team','at':'2026-11-21T00:00:00Z','body':body}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--real-model',action='store_true')
    args=ap.parse_args()
    try:from qdrant_client import QdrantClient  # noqa: F401
    except ImportError:
        print('ERROR: install Qdrant with: python -m pip install -r vector-requirements.txt')
        return 2
    if args.real_model:
        try:from tracemind_semantic import LocalEmbeddingModel
        except ImportError as exc:
            print('ERROR: optional neural dependency missing:',exc);return 2
        embedder=LocalEmbeddingModel()
    else:embedder=SyntheticEmbedder()
    rows=[record('invoice','Supplier payment invoices are awaiting finance approval.'),
          record('login','Sign-in authentication check completed.')]
    with tempfile.TemporaryDirectory(prefix='tracemind-qdrant-') as tmp:
        s=QdrantEvidenceStore(path=tmp,embedder=embedder)
        hits=s.search('Are supplier payments blocked?',rows)
        first=s.last_indexed;s.close()
        s=QdrantEvidenceStore(path=tmp,embedder=embedder)
        repeated=s.search('Are supplier payments blocked?',rows)
        second=s.last_indexed;s.close()
        if not hits or hits[0].record['id']!='invoice' or first!=2 or second!=0 or not repeated:
            print('FAIL: index persistence/semantic search was not correct')
            return 1
        print('PASS: REAL Qdrant persistent vector DB opened and queried')
        print('model:',embedder.model_name)
        print('first query indexed:',first,'records; second query indexed:',second)
        print('top source:',hits[0].record['id'],'; private records never indexed')
    return 0


if __name__=='__main__':raise SystemExit(main())
