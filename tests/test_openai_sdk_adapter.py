"""No network calls. Verify the optional scored-CLI adapter uses OpenAI SDK correctly."""
import os
import sys
import types
import unittest
from unittest.mock import patch
import llm_adapter

class FakeSDK:
    captured=[]
    def __init__(self,**kwargs):self.captured.append(('client',kwargs))
    @property
    def responses(self):return self
    def create(self,**kwargs):
        self.captured.append(('response',kwargs))
        from types import SimpleNamespace as O
        return O(output_text='{"answer":"Nina owns the invoice workflow","sources":["source-77"],"matched":[],"clarify":null,"refused":null}',
                 usage=O(input_tokens=170,output_tokens=35))

class BadRequestError(Exception):
    """Mimics the live OpenAI Responses-API 400 raised when json_object format
    is requested but the input messages do not contain the word 'json'."""

class JsonRuleSDK:
    """Stands in for the openai SDK; enforces the live Responses-API rule that
    text.format=json_object requires the word 'json' in the input content."""
    captured=[]
    def __init__(self,**kwargs):JsonRuleSDK.captured.append(('client',kwargs))
    @property
    def responses(self):return self
    def create(self,**kwargs):
        JsonRuleSDK.captured.append(('response',kwargs))
        fmt=((kwargs.get('text') or {}).get('format') or {})
        if fmt.get('type')=='json_object':
            msgs=kwargs.get('input') or []
            if not isinstance(msgs,list):msgs=[msgs]
            blob=' '.join((m.get('content','') if isinstance(m,dict) else str(m)) for m in msgs)
            if 'json' not in blob.lower():
                raise BadRequestError("Response input messages must contain the word 'json'.")
        from types import SimpleNamespace as O
        return O(output_text='{"answer":null,"sources":[],"matched":[],"clarify":null,"refused":{"reason":"private"}}',
                 usage=O(input_tokens=170,output_tokens=35))


class AdapterSDKTests(unittest.TestCase):
    def test_offline_default_does_not_call_sdk(self):
        with patch.dict(os.environ,{'TRACEMIND_USE_LLM':'0'}):
            self.assertFalse(llm_adapter.enabled())
            self.assertIsNone(llm_adapter.grounded_ask('Who owns?',[], 'p02'))

    def test_opt_in_uses_responses_sdk_with_metered_tokens(self):
        FakeSDK.captured=[]
        env={'TRACEMIND_USE_LLM':'1','TRACEMIND_API_KEY':'test-not-real',
             'TRACEMIND_MODEL':'gpt-4.1-mini',
             'TRACEMIND_PRICE_INPUT_PER_M':'0.40','TRACEMIND_PRICE_OUTPUT_PER_M':'1.60'}
        record={'id':'source-77','type':'mail','author':'p02','at':'2026-11-03T12:00:00Z',
                'client':'client_1','body':'Nina owns the invoice workflow.'}
        with patch.dict(os.environ,env),patch.dict(sys.modules,{'openai':types.SimpleNamespace(OpenAI=FakeSDK)}):
            result=llm_adapter.grounded_ask('Who owns the invoice workflow?', [record],'p02')
        self.assertIsNotNone(result)
        answer, usage=result
        self.assertEqual(answer['answer']['sources'],['source-77'])
        self.assertEqual(usage['input_tokens'],170)
        self.assertGreater(usage['cost_usd'],0)
        self.assertEqual(FakeSDK.captured[1][1]['model'],'gpt-4.1-mini')
        self.assertFalse(FakeSDK.captured[1][1]['store'])

    def test_grounded_ask_embeds_json_word_in_input(self):
        """Live OpenAI rejects json_object format unless 'json' appears in the
        input message content. Reproduces the 400; grounded_ask must embed it."""
        JsonRuleSDK.captured=[]
        env={'TRACEMIND_USE_LLM':'1','TRACEMIND_API_KEY':'test-not-real',
             'TRACEMIND_MODEL':'gpt-4.1-mini',
             'TRACEMIND_PRICE_INPUT_PER_M':'0.40','TRACEMIND_PRICE_OUTPUT_PER_M':'1.60'}
        record={'id':'source-77','type':'mail','author':'p02','at':'2026-11-03T12:00:00Z',
                'client':'client_1','body':'Nina owns the invoice workflow.'}
        with patch.dict(os.environ,env),patch.dict(sys.modules,{'openai':types.SimpleNamespace(OpenAI=JsonRuleSDK)}):
            result=llm_adapter.grounded_ask('Who owns the invoice workflow?', [record],'p02')
        self.assertIsNotNone(result,'grounded_ask returned None; the json-in-input 400 was raised')
        create_kwargs=[kw for tag,kw in JsonRuleSDK.captured if tag=='response'][0]
        blob=' '.join((m.get('content','') if isinstance(m,dict) else str(m)) for m in create_kwargs['input'])
        self.assertIn('json',blob.lower())

if __name__=='__main__':unittest.main()
