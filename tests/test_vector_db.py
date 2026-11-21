"""Independently verify persistent-vector integration without network/model downloads.

The client is a fake Qdrant implementation; these tests validate integration,
index lifecycle, metadata scoping, and defense-in-depth. A real smoke test is
provided separately in tools/vector_db_smoke.py.
"""
import math
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracemind_vector_db import QdrantEvidenceStore, retrieve, _point_id


class FakeModels:
    Distance = types.SimpleNamespace(COSINE="Cosine")
    VectorParams = lambda **k: types.SimpleNamespace(**k)
    PointStruct = lambda **k: types.SimpleNamespace(**k)
    Filter = lambda **k: types.SimpleNamespace(**k)
    FieldCondition = lambda **k: types.SimpleNamespace(**k)
    HasIdCondition = lambda **k: types.SimpleNamespace(**k)
    MatchValue = lambda **k: types.SimpleNamespace(**k)


class FakeQdrant:
    def __init__(self):
        self.collections={}
        self.upserts=0
        self.ignore_filter=False
        self.extra_result=None
    def collection_exists(self,name):return name in self.collections
    def create_collection(self,collection_name,vectors_config):
        self.collections[collection_name]={}
    def retrieve(self,collection_name,ids,with_payload,with_vectors):
        return [p for i in ids if (p:=self.collections[collection_name].get(i)) is not None]
    def upsert(self,collection_name,points,wait):
        self.upserts+=len(points)
        for p in points:self.collections[collection_name][p.id]=p
    def query_points(self,collection_name,query,query_filter,limit,with_payload,with_vectors):
        items=[]
        for item in self.collections[collection_name].values():
            if not self.ignore_filter:
                for condition in query_filter.must:
                    if hasattr(condition,'has_id') and item.id not in condition.has_id:break
                    if hasattr(condition,'key') and item.payload.get(condition.key)!=condition.match.value:break
                else:pass
                if any((hasattr(c,'has_id') and item.id not in c.has_id) or
                       (hasattr(c,'key') and item.payload.get(c.key)!=c.match.value)
                       for c in query_filter.must):continue
            def cosine(a,b):
                dot=sum(x*y for x,y in zip(a,b)); aa=math.sqrt(sum(x*x for x in a));bb=math.sqrt(sum(x*x for x in b))
                return dot/(aa*bb) if aa*bb else 0.
            items.append(types.SimpleNamespace(id=item.id,score=cosine(item.vector,query),payload=item.payload))
        if self.extra_result is not None:items.insert(0,self.extra_result)
        items.sort(key=lambda x:x.score,reverse=True)
        return types.SimpleNamespace(points=items[:limit])
    def close(self):pass


class FakeEmbedding:
    model_name="test-fake-vectors-v1"
    def __init__(self):self.calls=[]
    def encode(self,texts):
        self.calls.extend(texts)
        out=[]
        for text in texts:
            s=text.lower()
            if any(k in s for k in ('payment','invoice','supplier','finance')):out.append([1.,0.,0.])
            elif any(k in s for k in ('login','sign in','authentication')):out.append([0.,1.,0.])
            else:out.append([0.,0.,1.])
        return out


def record(rid,body,org='org_a',client='northbeam',visibility='team',at='2026-11-02T12:00:00Z'):
    return {'id':rid,'org':org,'client':client,'type':'chat','visibility':visibility,
            'body':body,'author':'p01','at':at}


class QdrantIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fake=FakeQdrant();self.embed=FakeEmbedding();self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
    def store(self):
        return QdrantEvidenceStore(path=self.tmp.name,client=self.fake,models=FakeModels,embedder=self.embed)

    def test_persistent_upsert_and_semantic_lookup(self):
        rows=[record('a','Invoice approvals are pending.'),record('b','Login authentication tests passed.')]
        s=self.store();hit=s.search('Are supplier payments delayed?',rows)
        self.assertEqual(hit[0].record['id'],'a')
        self.assertEqual(s.last_indexed,2)
        old=self.fake.upserts
        # Simulate another process connecting to the same persisted index.
        s2=self.store();hit2=s2.search('supplier payments',rows)
        self.assertEqual(hit2[0].record['id'],'a')
        self.assertEqual(s2.last_indexed,0)
        self.assertEqual(self.fake.upserts,old)

    def test_changed_content_is_reembedded(self):
        rows=[record('a','Invoice approvals pending')]
        self.store().search('supplier payments',rows)
        n=self.fake.upserts
        changed=[record('a','Login authentication fixed')]
        self.store().search('login issue',changed)
        self.assertEqual(self.fake.upserts,n+1)

    def test_private_and_restricted_never_indexed(self):
        rows=[record('safe','Invoice payments'),record('priv','Invoice salary secret',visibility='private'),
              record('rest','Invoice restricted',visibility='restricted')]
        s=self.store();found=s.search('supplier payments',rows)
        ids=[x.record['id'] for x in found]
        self.assertEqual(ids,['safe'])
        self.assertEqual(sum(map(len,self.fake.collections.values())),1)

    def test_cross_org_records_rejected_in_same_request(self):
        rows=[record('a','Invoice payments'),record('b','Invoice payments',org='org_b')]
        with self.assertRaisesRegex(ValueError,'one authorized organization'):
            self.store().search('supplier payments',rows)

    def test_other_org_records_cannot_leak_from_existing_index(self):
        s=self.store();s.search('supplier payments',[record('x','Invoice payments',org='org_b')])
        results=self.store().search('supplier payments',[record('a','Invoice payments')])
        self.assertEqual([x.record['id'] for x in results],['a'])

    def test_forget_and_time_cutoff_apply_without_deleting_shared_vectors(self):
        rows=[record('old','Invoice payments'),record('future','Invoice payments',at='2026-12-10T00:00:00Z')]
        self.store().search('supplier payments',rows)
        # Engine.allowed would exclude forgotten and future records.
        hit=self.store().search('supplier payments',[rows[0]])
        self.assertEqual([x.record['id'] for x in hit],['old'])
        hit=self.store().search('supplier payments',[])
        self.assertEqual(hit,[])
        self.assertEqual(sum(map(len,self.fake.collections.values())),2)

    def test_bypass_qdrant_filter_still_no_leak(self):
        self.store().search('supplier payments',[record('private_to_user','Invoice payments',org='org_b')])
        self.fake.ignore_filter=True
        res=self.store().search('supplier payments',[record('allowed','Invoice payments')])
        self.assertEqual([x.record['id'] for x in res],['allowed'])

    def test_returned_fake_source_id_is_rejected(self):
        forged=types.SimpleNamespace(id=_point_id('org_a','a'),score=1.0,payload={'source_id':'forged'})
        self.fake.query_points=lambda **kwargs:types.SimpleNamespace(points=[forged])
        res=self.store().search('supplier payments',[record('a','Invoice payments')])
        self.assertEqual(res,[])

    def test_client_filter_prevents_cross_client(self):
        self.store().search('supplier payments',[record('a','Invoice payments'),record('b','Invoice payments',client='cobaltline')])
        res=self.store().search('supplier payments',[record('a','Invoice payments'),record('b','Invoice payments',client='cobaltline')],client='northbeam')
        self.assertEqual([x.record['id'] for x in res],['a'])

    def test_ranking_fuses_lexical_and_vectors(self):
        rows=[record('a','Invoice approvals are pending'),record('b','Authentication login is working')]
        docs,used,error=retrieve('supplier payments',rows,embedder=self.embed,path=self.tmp.name,
                                  client_obj=self.fake,models=FakeModels)
        self.assertTrue(used);self.assertIsNone(error)
        self.assertEqual(docs[0]['id'],'a')

    def test_missing_qdrant_falls_back_cleanly(self):
        # Inject failure at the vector query level. Lexical results must not expand scope.
        def boom(*a,**k):raise RuntimeError('qdrant unavailable')
        self.fake.query_points=boom
        rows=[record('a','Supplier payments are pending')]
        docs,used,error=retrieve('supplier payments',rows,embedder=self.embed,
                                  client_obj=self.fake,models=FakeModels)
        self.assertFalse(used);self.assertIn('Qdrant unavailable',error)
        self.assertEqual(docs[0]['id'],'a')

    def test_no_openai_key_required(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'','TRACEMIND_VECTOR_DB':'0'}):
            self.assertEqual(self.store().search('supplier payments',[record('a','Invoice payments')])[0].record['id'],'a')


if __name__=='__main__':unittest.main()
