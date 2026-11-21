"""Independent tests of SDK function-call loop, permissions and staged actions."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from fastapi.testclient import TestClient

import studio_api
from studio_actions import stage, confirm, list_items, list_memory
from studio_agent import Agent

class FakeOpenAI:
    def __init__(self,steps):self.steps=iter(steps);self.inputs=[]
    def responses_create(self,**kwargs):
        self.inputs.append(kwargs)
        return next(self.steps)
    @property
    def responses(self):return NS(create=self.responses_create)

def tool_response(name,args,call_id='c1'):
    return NS(output=[NS(type='function_call',name=name,arguments=json.dumps(args),call_id=call_id)],output_text='',
              usage=NS(input_tokens=65,output_tokens=24))

def text_response(data):
    return NS(output=[],output_text=json.dumps(data),usage=NS(input_tokens=70,output_tokens=25))

@unittest.skipUnless(
    (Path(os.environ.get('R3_PACK') or Path(__file__).resolve().parents[1]).resolve()
     / 'data/days/day-01.jsonl').is_file(),
    'Organizer public fixtures missing: set R3_PACK or use the Local Verification ZIP',
)
class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.old=studio_api.STUDIO_DB
        studio_api.STUDIO_DB=Path(cls.tmp.name)/'studio.sqlite3'
        studio_api.seed_demo()
        cls.client=TestClient(studio_api.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        studio_api.STUDIO_DB=cls.old
        cls.tmp.cleanup()

    def setUp(self):
        self.client.post('/api/demo-reset')

    def _agent(self,person='p02',day=3,steps=()):
        scope=studio_api.scoped_engine(person,day)
        eng=scope.__enter__()
        self.addCleanup(lambda:scope.__exit__(None,None,None))
        return Agent(eng,person,day,studio_api.cutoff(day),sdk_client=FakeOpenAI(steps))

    def test_read_source_never_exposes_private_records_to_openai(self):
        agent=self._agent()
        with studio_api.scoped_engine('p02',3) as eng:
            own_private=next(r for r in studio_api.available(eng,'p02',3) if r.get('visibility')=='private')
        self.assertEqual(agent.execute('read_source',{'source_id':own_private['id']})['error'],'Source not accessible')

    def test_private_source_never_in_model_evidence_results(self):
        agent=self._agent()
        out=agent.execute('search_evidence',{'query':'Dubai trip 20–24 Nov'})
        self.assertTrue(all(x['source_id'] in agent.byid for x in out['evidence']))
        self.assertTrue(all(agent.byid[x['source_id']]['visibility']=='team' for x in out['evidence']))

    def test_model_sees_no_records_from_second_organization(self):
        agent=self._agent()
        self.assertTrue(all(x.get('org')==agent.org for x in agent.team))
        self.assertTrue(all(x.get('visibility')=='team' for x in agent.team))

    def test_model_loop_executes_real_search_function_and_validates_source(self):
        agent=self._agent()
        team=next(r for r in agent.team if r.get('body'))
        # Read the actual source ID using a tool call, then cite it in final JSON.
        agent.client=FakeOpenAI([
          tool_response('read_source',{'source_id':team['id']}),
          text_response({'answer':'I found an accessible source record.','sources':[team['id']],'clarify':None}),
        ])
        result=agent.ask('Check this source')
        self.assertEqual(result['answer']['sources'],[team['id']])
        self.assertEqual(result['trace'][0]['tool'],'read_source')
        self.assertEqual(result['usage']['input_tokens'],135)
        payload=agent.client.inputs[1]['input']
        self.assertTrue(any(x.get('type')=='function_call_output' and x.get('call_id')=='c1' for x in payload))

    def test_unsupported_citation_is_rejected(self):
        agent=self._agent(steps=[text_response({'answer':'Nina owns HR','sources':['nonexistent'],'clarify':None})])
        result=agent.ask('Who owns HR?')
        self.assertIsNone(result['answer'])
        self.assertIsNotNone(result['clarify'])

    def test_hallucinated_numeric_date_is_rejected(self):
        agent=self._agent()
        team=next(r for r in agent.team if r.get('body'))
        agent.client=FakeOpenAI([
            tool_response('read_source',{'source_id':team['id']}),
            text_response({'answer':'The deadline is 2099-12-12','sources':[team['id']],'clarify':None}),
        ])
        self.assertIsNone(agent.ask('What happened?')['answer'])

    def test_agent_can_stage_call_but_does_not_place_it(self):
        agent=self._agent(steps=[tool_response('prepare_action',{'type':'schedule_call','title':'Call supplier','details':'Discuss invoice','due':'2026-11-13T10:00','target_id':'','memory_kind':'none','source_ids':[]}),
                                 text_response({'answer':'I prepared a call plan for approval.','sources':[],'clarify':None})])
        result=agent.ask('Plan a call with the supplier')
        self.assertEqual(len(result['actions']),1)
        self.assertEqual(result['actions'][0]['status'],'pending')
        self.assertFalse(list_items(agent.eng.db,'p02',agent.org))
        approved=confirm(agent.eng.db,result['actions'][0]['id'],'p02',agent.org,True)
        self.assertTrue(approved['result']['local_only'])
        self.assertEqual(list_items(agent.eng.db,'p02',agent.org)[0]['type'],'call')

    def test_cannot_approve_another_persons_action(self):
        agent=self._agent()
        action=stage(agent.eng.db,'p02',agent.org,'create_task',{'title':'Follow up'})
        with self.assertRaises(PermissionError):confirm(agent.eng.db,action['id'],'p03',agent.org,True)

    def test_rejecting_action_does_not_write_item(self):
        agent=self._agent()
        action=stage(agent.eng.db,'p02',agent.org,'draft_message',{'title':'Email draft'})
        confirm(agent.eng.db,action['id'],'p02',agent.org,False)
        self.assertFalse(list_items(agent.eng.db,'p02',agent.org))

    def test_existing_official_task_cannot_be_mutated_by_agent(self):
        agent=self._agent()
        action=stage(agent.eng.db,'p02',agent.org,'update_task',{'target_id':'t100','title':'Hijack'})
        with self.assertRaises(PermissionError):confirm(agent.eng.db,action['id'],'p02',agent.org,True)

    def test_unsourced_fact_memory_refused(self):
        agent=self._agent()
        action=stage(agent.eng.db,'p02',agent.org,'remember',{'title':'Ownership','details':'X owns Y','memory_kind':'fact'})
        with self.assertRaises(ValueError):confirm(agent.eng.db,action['id'],'p02',agent.org,True)

    def test_saved_preference_scoped_to_person(self):
        agent=self._agent()
        action=stage(agent.eng.db,'p02',agent.org,'remember',{'title':'Brief preference','details':'Fewer newsletters','memory_kind':'preference'})
        confirm(agent.eng.db,action['id'],'p02',agent.org,True)
        self.assertEqual(len(list_memory(agent.eng.db,'p02',agent.org)),1)
        self.assertFalse(list_memory(agent.eng.db,'p03',agent.org))
        # The user's explicitly approved preference can be used if they opt into external mode.
        self.assertEqual(len(agent.execute('recall_memory',{'query':''})['memories']),1)

    def test_source_fact_memory_requires_accessible_record(self):
        agent=self._agent()
        action=stage(agent.eng.db,'p02',agent.org,'remember',{'title':'Ownership','details':'X owns Y','memory_kind':'fact','source_ids':['bad-id']})
        with self.assertRaises(PermissionError):confirm(agent.eng.db,action['id'],'p02',agent.org,True,allowed_sources=set(agent.byid))

    def test_api_refuses_remote_mode_without_user_consent(self):
        result=self.client.post('/api/agent',json={'person':'p02','day':3,'question':'Hello','api_key':'fake','consent':False})
        self.assertEqual(result.status_code,400)

    def test_api_refuses_remote_mode_without_key(self):
        from unittest.mock import patch
        with patch.dict('os.environ',{'OPENAI_API_KEY':''}):
            result=self.client.post('/api/agent',json={'person':'p02','day':3,'question':'Hello','consent':True})
        self.assertEqual(result.status_code,400)

    def test_api_manual_task_requires_confirm(self):
        r=self.client.post('/api/actions/prepare',json={'person':'p02','type':'create_task','title':'Prepare report'})
        self.assertEqual(r.status_code,200)
        aid=r.json()['action']['id']
        self.assertEqual(self.client.get('/api/actions?person=p02&day=3').json()['items'],[])
        self.assertEqual(self.client.post(f'/api/actions/{aid}/decision',json={'person':'p02','day':3,'approve':True}).status_code,200)
        self.assertEqual(len(self.client.get('/api/actions?person=p02&day=3').json()['items']),1)

    def test_api_action_visibility_person_scoped(self):
        self.client.post('/api/actions/prepare',json={'person':'p02','type':'create_task','title':'Personal follow-up'})
        self.assertFalse(self.client.get('/api/actions?person=p03&day=3').json()['actions'])

    def test_memory_revision_supersedes_previous_value(self):
        agent=self._agent()
        a=stage(agent.eng.db,'p02',agent.org,'remember',{'title':'Brief style','details':'Keep 6 updates','memory_kind':'preference'})
        confirm(agent.eng.db,a['id'],'p02',agent.org,True)
        b=stage(agent.eng.db,'p02',agent.org,'remember',{'title':'Brief style','details':'Keep 3 updates','memory_kind':'preference'})
        confirm(agent.eng.db,b['id'],'p02',agent.org,True)
        history=list_memory(agent.eng.db,'p02',agent.org)
        self.assertEqual(len(history),2)
        self.assertEqual({m['status'] for m in history},{'active','superseded'})
        self.assertEqual([m['value'] for m in agent.execute('recall_memory',{'query':'Brief style'})['memories']],['Keep 3 updates'])

    def test_expired_memory_not_sent_to_model(self):
        agent=self._agent()
        a=stage(agent.eng.db,'p02',agent.org,'remember',{'title':'Expired preference','details':'Temporary','memory_kind':'preference','due':'2020-01-01'})
        confirm(agent.eng.db,a['id'],'p02',agent.org,True)
        self.assertEqual(list_memory(agent.eng.db,'p02',agent.org)[0]['status'],'expired')
        self.assertEqual(agent.execute('recall_memory',{'query':'Expired'})['memories'],[])

    def test_forget_purges_matching_approved_local_drafts(self):
        agent=self._agent()
        a=stage(agent.eng.db,'p02',agent.org,'draft_message',{'title':'Dubai trip itinerary'})
        confirm(agent.eng.db,a['id'],'p02',agent.org,True)
        self.assertEqual(len(list_items(agent.eng.db,'p02',agent.org)),1)
        f=stage(agent.eng.db,'p02',agent.org,'forget',{'title':'Dubai trip'})
        confirm(agent.eng.db,f['id'],'p02',agent.org,True,forget_callback=agent.eng.forget)
        self.assertEqual(list_items(agent.eng.db,'p02',agent.org),[])

    def test_forget_action_wipes_private_source_after_approval(self):
        with studio_api.scoped_engine('p02',3) as eng:
            note=next(r for r in studio_api.available(eng,'p02',3) if r.get('visibility')=='private' and 'Dubai trip' in r.get('body',''))
        aid=self.client.post('/api/actions/prepare',json={'person':'p02','type':'forget','title':'Dubai trip'}).json()['action']['id']
        self.assertEqual(self.client.get('/api/sources/'+note['id']+'?person=p02&day=3').status_code,200)
        self.client.post(f'/api/actions/{aid}/decision',json={'person':'p02','day':3,'approve':True})
        self.assertEqual(self.client.get('/api/sources/'+note['id']+'?person=p02&day=3').status_code,404)

if __name__=='__main__':unittest.main()
