"""Live Studio API integration tests. Never modify official answer keys or fixtures."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

import studio_api
from tracemind import Engine

@unittest.skipUnless(
    (Path(os.environ.get('R3_PACK') or Path(__file__).resolve().parents[1]).resolve()
     / 'data/days/day-01.jsonl').is_file(),
    'Organizer public fixtures missing: set R3_PACK or use the Local Verification ZIP',
)
class StudioAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.old_db = studio_api.STUDIO_DB
        studio_api.STUDIO_DB = Path(cls.temporary.name) / 'studio.sqlite3'
        studio_api.seed_demo()
        cls.client = TestClient(studio_api.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        studio_api.STUDIO_DB = cls.old_db
        cls.temporary.cleanup()

    def test_bootstrap_real_persons_and_days(self):
        obj=self.client.get('/api/bootstrap').json()
        self.assertEqual(obj['days'],[1,2,3,4,5])
        self.assertTrue(any(p['id']=='p02' for p in obj['persons']))

    def test_real_briefs_are_time_scoped(self):
        obj=self.client.get('/api/briefs',params={'person':'p02','day':3}).json()
        self.assertEqual(len(obj['briefs']),2)

    def test_dashboard_comes_from_real_records(self):
        obj=self.client.get('/api/dashboard',params={'person':'p02','day':3}).json()
        self.assertGreater(obj['stats']['records'],100)
        self.assertEqual(obj['stats']['meetings'],2)
        self.assertEqual(obj['day'],3)

    def test_question_sources_are_real_and_visible(self):
        obj=self.client.post('/api/ask',json={'person':'p02','day':3,'question':'Who owns billing for Northbeam now?','mode':'lexical'}).json()
        self.assertIn('Arjun',obj['result']['answer']['text'])
        with studio_api.scoped_engine('p02',3) as eng:
            permissible={r['id'] for r in studio_api.available(eng,'p02',3)}
        self.assertTrue(set(obj['result']['answer']['sources']).issubset(permissible))
        self.assertTrue(all(x['id'] in permissible for x in obj['retrieval']['evidence']))

    def test_source_endpoints_restrict_cross_org(self):
        with studio_api.scoped_engine('q01',3) as eng:
            other=next(r for r in studio_api.available(eng,'q01',3) if r.get('org')=='org_bw')
        self.assertEqual(self.client.get(f"/api/sources/{other['id']}",params={'person':'p02','day':3}).status_code,404)
        self.assertEqual(self.client.get(f"/api/sources/{other['id']}",params={'person':'q01','day':3}).status_code,200)

    def test_source_and_search_hide_future(self):
        with studio_api.scoped_engine('p02',5) as eng:
            day5=next(r for r in studio_api.available(eng,'p02',5) if studio_api.datetime_utc(r.get('at'))>studio_api.datetime_utc(studio_api.cutoff(3)))
        self.assertEqual(self.client.get(f"/api/sources/{day5['id']}",params={'person':'p02','day':3}).status_code,404)
        result=self.client.get('/api/records',params={'person':'p02','day':3,'q':day5['id']}).json()
        self.assertEqual(result['total'],0)

    def test_own_private_visible_and_other_person_denied(self):
        with studio_api.scoped_engine('p02',3) as eng:
            own=next(r for r in studio_api.available(eng,'p02',3) if r.get('visibility')=='private')
        self.assertEqual(self.client.get(f"/api/sources/{own['id']}",params={'person':'p02','day':3}).status_code,200)
        self.assertEqual(self.client.get(f"/api/sources/{own['id']}",params={'person':'p03','day':3}).status_code,404)

    def test_no_leak_from_wrong_organization_in_ask_results(self):
        obj=self.client.post('/api/ask',json={'person':'p02','day':3,'question':'Who owns Cobaltline fleet dashboard?','mode':'lexical'}).json()
        with studio_api.scoped_engine('p02',3) as eng:
            ids={r['id'] for r in studio_api.available(eng,'p02',3)}
        self.assertTrue(all(r['id'] in ids for r in obj['retrieval']['evidence']))

    def test_feedback_filter_prevents_future_memory_in_day_one(self):
        with studio_api.scoped_engine('p02',1) as eng:
            self.assertEqual(eng._feedback(),[])
        m1=self.client.get('/api/memory',params={'person':'p02','day':1}).json()
        self.assertEqual(m1['feedback'],[])
        m3=self.client.get('/api/memory',params={'person':'p02','day':3}).json()
        self.assertTrue(any('newsletter' in f.get('words','').lower() for f in m3['feedback']))

    def test_demo_reset_restores_studio_only(self):
        # The reset affects only the isolated Studio database.
        self.assertTrue(self.client.post('/api/demo-reset').json()['ok'])
        with studio_api.scoped_engine('p02',3) as eng:
            note=next(r for r in studio_api.available(eng,'p02',3) if r.get('visibility')=='private' and 'Dubai trip' in r.get('body',''))
        self.client.post('/api/forget',json={'person':'p02','what':'Dubai trip'})
        self.assertEqual(self.client.get('/api/sources/'+note['id'],params={'person':'p02','day':3}).status_code,404)
        self.assertTrue(self.client.post('/api/demo-reset').json()['ok'])
        self.assertEqual(self.client.get('/api/sources/'+note['id'],params={'person':'p02','day':3}).status_code,200)

    def test_optional_remote_model_never_runs_without_opt_in(self):
        import llm_adapter
        old=llm_adapter.grounded_ask
        try:
            def fail_if_called(*args,**kwargs):
                raise AssertionError('Unexpected external model call')
            llm_adapter.grounded_ask=fail_if_called
            result=self.client.post('/api/ask',json={'person':'p02','day':3,'question':'Anything new about vendor invoices?','mode':'model'})
            self.assertEqual(result.status_code,200)
            self.assertIn('disabled',result.json()['note'].lower())
        finally:
            llm_adapter.grounded_ask=old

    def test_unknown_demo_identity_is_rejected(self):
        self.assertEqual(self.client.get('/api/dashboard',params={'person':'p9999','day':3}).status_code,400)
        self.assertEqual(self.client.post('/api/ask',json={'person':'p9999','day':3,'question':'who owns this?'}).status_code,400)

    def test_malformed_ask_is_rejected(self):
        self.assertEqual(self.client.post('/api/ask',json={'person':'p02','day':4,'question':'x'}).status_code,422)

    def test_forget_affects_only_selected_demo_identity(self):
        # use a privately authored travel note, never a shared workplace fact.
        with studio_api.scoped_engine('p02',3) as eng:
            notes=[r for r in studio_api.available(eng,'p02',3) if r.get('visibility')=='private' and 'Dubai trip' in r.get('body','')]
        self.assertTrue(notes)
        rid=notes[0]['id']
        self.assertEqual(self.client.get('/api/sources/'+rid,params={'person':'p02','day':3}).status_code,200)
        r=self.client.post('/api/forget',json={'person':'p02','what':'Dubai trip'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.get('/api/sources/'+rid,params={'person':'p02','day':3}).status_code,404)
        self.assertNotIn(rid, [r['id'] for r in self.client.get('/api/records',params={'person':'p02','day':3}).json()['items']])

if __name__=='__main__':unittest.main()
