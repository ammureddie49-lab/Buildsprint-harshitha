"""Synthetic checks for score-critical model activation, budgets, and generalization.

The fake client is not a substitute for a live-key evaluation. These tests
assert that new phrasings reach interpretation and unsafe/unbounded prompts don't.
"""
from __future__ import annotations
import json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from tracemind_model_config import model_enabled,fits_input_budget,cost_usd
from tracemind_hybrid import Gateway,HybridMemory,interpret_due,QUESTION_SYSTEM,EVIDENCE_SYSTEM
from tracemind import Engine
import llm_adapter

class FakeClient:
    def __init__(self,response=None,input_tokens=100):
        self.responses=self
        self.calls=[]
        self.response=response or {'answer':'', 'sources':[], 'clarify':'', 'refused':''}
        self.tokens=input_tokens
    def create(self,**kw):
        self.calls.append(kw)
        return NS(output_text=json.dumps(self.response),usage=NS(input_tokens=self.tokens,output_tokens=30))

class BadRequestError(Exception):
    """Mimics the live OpenAI Responses-API 400 raised when json_object format
    is requested but the input messages do not contain the word 'json'."""

class JsonRuleClient:
    """Stands in for the OpenAI SDK; enforces the live Responses-API rule that
    text.format=json_object requires the word 'json' in the input content."""
    def __init__(self):
        self.responses=self
        self.calls=[]
    def create(self,**kw):
        self.calls.append(kw)
        fmt=((kw.get('text') or {}).get('format') or {})
        if fmt.get('type')=='json_object':
            msgs=kw.get('input') or []
            if not isinstance(msgs,list):msgs=[msgs]
            blob=' '.join((m.get('content','') if isinstance(m,dict) else str(m)) for m in msgs)
            if 'json' not in blob.lower():
                raise BadRequestError("Response input messages must contain the word 'json'.")
        return NS(output_text=json.dumps({'facts':[]}),usage=NS(input_tokens=12,output_tokens=6))


class ModelModeTests(unittest.TestCase):
    def test_default_auto_with_key_no_dotenv_required(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','TRACEMIND_MODEL':'gpt-4.1-mini'},clear=True):
            self.assertTrue(Gateway.enabled())
            self.assertTrue(llm_adapter.enabled())

    def test_explicit_zero_overrides_key(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','TRACEMIND_USE_LLM':'0'},clear=True):
            self.assertFalse(Gateway.enabled())
            self.assertFalse(llm_adapter.enabled())

    def test_no_key_offline_and_unknown_model_fail_closed(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(model_enabled())
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','TRACEMIND_MODEL':'some-unknown-model'},clear=True):
            self.assertFalse(model_enabled())

    def test_custom_price_for_other_model(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','TRACEMIND_MODEL':'other-model',
              'TRACEMIND_PRICE_INPUT_PER_M':'2', 'TRACEMIND_PRICE_OUTPUT_PER_M':'4'},clear=True):
            self.assertTrue(Gateway.enabled())
            self.assertEqual(cost_usd(1000000,1000000),6)

    def test_budget_preflight_blocks_network(self):
        fake=FakeClient()
        # Use realistic mixed-word text: repeated 'x' compresses to ~1 token/char under
        # BPE (tiktoken), so 'x'*6500 may not exceed a 4000-token budget. Word-based text
        # tokenises at the expected ~1 token/word rate and reliably exceeds the limit.
        _words='the invoice billing owner changed from Kavya to Arjun client record evidence task due '
        big_body=_words*600  # ~90 000 chars -> well above 4000 tokens regardless of tokeniser
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'},clear=True):
            gw=Gateway(fake)
            result=gw.request(QUESTION_SYSTEM,{'question':'abc','evidence':[{'body':big_body}]},input_budget=4000)
            self.assertIsNone(result)
            self.assertEqual(fake.calls,[])
            self.assertIn('InputBudgetExceeded',gw.errors)

    def test_server_reported_over_budget_output_is_rejected_and_metered(self):
        fake=FakeClient({'answer':'fake','sources':['r1']},input_tokens=4200)
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'},clear=True):
            gw=Gateway(fake)
            result=gw.request('Interpret',{'records':[{'id':'r1','body':'Simple evidence.'}]},input_budget=4000)
            self.assertIsNone(result)
            self.assertEqual(gw.input_tokens,4200)
            self.assertGreater(gw.meter(),0)

    def test_budget_count_includes_instruction_and_payload(self):
        # Use realistic mixed-word text: repeated 'x' compresses drastically under BPE
        # (tiktoken) so 'x'*3900 fits in 4000 tokens. Word-based text does not compress
        # the same way and reliably exceeds the limit under both tiktoken and the byte fallback.
        _words='the invoice billing owner changed from Kavya to Arjun client record evidence task due '
        big_instruction=_words*300  # ~26 000 chars -> >5000 tokens under tiktoken, >26 000 bytes
        with patch.dict(os.environ,{'TRACEMIND_USE_LLM':'0'},clear=True):
            self.assertFalse(fits_input_budget(big_instruction,{'question':'tiny'},4000))

    def test_json_object_input_embeds_word_json(self):
        """Live OpenAI rejects json_object format unless 'json' appears in the
        input message content. Reproduces the 400 the smoke test hit; the gateway
        must embed the word in the input it sends to the SDK."""
        client=JsonRuleClient()
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','TRACEMIND_MODEL':'gpt-4.1-mini'},clear=True):
            gw=Gateway(client)
            result=gw.request(EVIDENCE_SYSTEM,{'records':[{'id':'r1','body':'Asha owns onboarding.'}]},max_output=500)
        self.assertIsNotNone(result,f'gateway returned None: {gw.errors}')
        self.assertNotIn('BadRequestError',gw.errors)
        self.assertTrue(client.calls,'SDK responses.create was never called')
        blob=' '.join((m.get('content','') if isinstance(m,dict) else str(m)) for m in client.calls[0]['input'])
        self.assertIn('json',blob.lower())

class UnseenLanguageTests(unittest.TestCase):
    def test_new_commitment_phrasings_are_interpretation_candidates(self):
        statements=[
            'Friday tak kar dunga, the proposal is on me.',
            'Kal subah tak bhej dungi vendor onboarding files.',
            'Parso tak ho jayega onboarding verification.',
            'I can deliver the contract tomorrow morning.',
            'The report will be finished before EOD.',
            'As agreed, the supplier documents are now due Friday.',
            'I will complete the QA review before Monday.',
            'I can submit the updated design by tomorrow.',
            'Aaj shaam tak share karungi updated invoices.',
            'The proposal is blocked until approvals arrive.',
            'Actually, billing shifted to Arjun from Kavya.',
            'Our new responsibility is transferred to the London team.',
            'The release deadline was delayed.',
            'I confirm the handoff to Maya Rao.',
            'We agreed to close the customer escalation tomorrow.'
        ]
        for text in statements:
            with self.subTest(text=text):
                record={'type':'chat','visibility':'team','body':text}
                self.assertTrue(HybridMemory.candidate(record))

    def test_parso_in_commitment_means_day_after_tomorrow(self):
        self.assertEqual(interpret_due('parso tak','2026-11-03T10:00:00Z','Asia/Kolkata'),'2026-11-05')

    def test_friday_tak_date_from_source_timezone(self):
        self.assertEqual(interpret_due('Friday tak','2026-11-03T10:00:00Z','Asia/Kolkata'),'2026-11-06')

    def test_model_attempt_occurs_at_most_once_per_question(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'data').mkdir()
            (root/'data/people.json').write_text(json.dumps({'org':{'people':[{'id':'p1','name':'Asha','role':'manager','zone':'UTC'}]}}))
            (root/'data/clients.json').write_text(json.dumps([{'id':'c','name':'Cobaltline'}]))
            with patch.dict(os.environ,{'R3_PACK':str(root),'TRACEMIND_USE_LLM':'0','OPENAI_API_KEY':''},clear=False):
                eng=Engine(db_path=root/'db.sqlite3')
                try:
                    with patch.object(eng.hybrid.gateway,'enabled',return_value=True),patch.object(eng.hybrid,'model_answer',return_value=None) as model:
                        eng.ask('p1','2026-11-06T12:00:00Z','Why was the invoice delayed?')
                        self.assertEqual(model.call_count,1)
                finally:eng.db.close()

if __name__=='__main__':unittest.main()
