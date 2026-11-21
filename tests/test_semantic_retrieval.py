"""Tests independent from official BuildSprint answers; no network/model needed."""
from __future__ import annotations
import os, unittest
from unittest.mock import patch
from tracemind_semantic import HybridEvidenceRetriever, retrieve, enabled


def r(key, text, client="alpha", kind="mail", at="2026-11-02T10:00:00Z"):
    return dict(id=key,body=text,client=client,type=kind,at=at)


class FakeEmbedding:
    """Deterministic stand-in for testing fusion and security, NOT a neural model."""
    def __init__(self, mapping):
        self.mapping = mapping
        self.seen = []
    def encode(self, texts):
        self.seen.extend(texts)
        return [self.mapping.get(text, [0.0,1.0]) for text in texts]


class HybridRetrievalTests(unittest.TestCase):
    def test_off_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(enabled())
    def test_lexical_default_kept(self):
        recs=[r('a','The invoice approval flow is blocked at finance'),r('b','The coffee beans arrived')]
        rows,used,error=retrieve('invoice approval',recs)
        self.assertFalse(used)
        self.assertIsNone(error)
        self.assertEqual(rows[0]['id'],'a')
    def test_neural_paraphrase_retrieval_works_with_mock_vectors(self):
        query='Who is accountable for supplier onboarding?'
        wanted='Priya coordinates the new partner induction process.'
        distractor='The office purchased coffee supplies.'
        embed=FakeEmbedding({query:[1,0],wanted:[0.98,0.2],distractor:[0.01,1.0]})
        rows,used,error=retrieve(query,[r('d',distractor),r('w',wanted)],embedder=embed)
        self.assertTrue(used)
        self.assertIsNone(error)
        self.assertEqual(rows[0]['id'],'w')
    def test_client_scoped_before_embedding(self):
        query='Who owns the supplier induction process?'
        a='Supplier induction process is assigned to A'
        b='Supplier induction process is assigned to B'
        emb=FakeEmbedding({query:[1,0],a:[1,0],b:[1,0]})
        rows,used,_=retrieve(query,[r('same',a,'alpha'),r('secret',b,'beta')],client='alpha',embedder=emb)
        self.assertEqual([x['id'] for x in rows],['same'])
        self.assertFalse(any(' B' in text for text in emb.seen))
    def test_authorized_inputs_only(self):
        # The caller has already eliminated private and future evidence.
        emb=FakeEmbedding({'release readiness':[1,0], 'Release is ready':[1,0]})
        allowed=[r('team','Release is ready')]
        rows,used,_=retrieve('release readiness',allowed,embedder=emb)
        self.assertTrue(used)
        self.assertEqual([x['id'] for x in rows],['team'])
        self.assertNotIn('PRIVATE: unreleased merger',emb.seen)
    def test_notifications_skipped(self):
        emb=FakeEmbedding({'notification text':[1,0]})
        rows,used,_=retrieve('notification text',[r('noise','notification text',kind='notification')],embedder=emb)
        self.assertEqual(rows,[])
        self.assertFalse(used)
    def test_zero_vector_safe(self):
        emb=FakeEmbedding({'q':[0,0], 'x':[0,0]})
        hits=HybridEvidenceRetriever([r('1','x')],embedder=emb).search('q')
        self.assertEqual(hits,[])
    def test_model_unavailable_falls_back(self):
        class NoModel:
            def encode(self, texts):
                raise ImportError('no local model weights')
        rows,used,error=retrieve('invoice flow',[r('a','invoice flow blocked')],embedder=NoModel())
        self.assertEqual(rows[0]['id'],'a')
        self.assertFalse(used)
        self.assertIn('ImportError',error)
    def test_deterministic_ranking_under_record_reorder(self):
        q='payment authorization'
        docs=[r('a','Payment authorization approved'),r('b','Coffee beans'),r('c','Accounts payable approved')]
        first=[x.record['id'] for x in HybridEvidenceRetriever(docs).search(q)]
        second=[x.record['id'] for x in HybridEvidenceRetriever(list(reversed(docs))).search(q)]
        self.assertEqual(first,second)
    def test_relevant_citations_not_created(self):
        emb=FakeEmbedding({'contract renewal':[1,0],'Renewal was approved':[1,0]})
        hits=HybridEvidenceRetriever([r('r42','Renewal was approved')],emb).search('contract renewal')
        self.assertEqual(hits[0].record['id'],'r42')
        self.assertNotIn('answer',hits[0].record)
    def test_wrong_model_shape_is_detected(self):
        class Bad:
            def encode(self,texts):return [[1,0]]
        _,used,error=retrieve('invoice',[r('a','invoice')],embedder=Bad())
        self.assertFalse(used)
        self.assertIn('ValueError',error)

if __name__=='__main__':unittest.main()
