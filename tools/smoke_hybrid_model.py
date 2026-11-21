#!/usr/bin/env python3
"""One optional, minimal REAL model SDK check with FAKE workplace input.

Does not touch the scored SQLite database, does not read workplace records,
and does not print the API key. This call may incur a small API charge.
"""
import json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from tracemind_hybrid import Gateway, EVIDENCE_SYSTEM

def main():
    gateway=Gateway()
    if not gateway.enabled():
        print('Model unavailable: set OPENAI_API_KEY in your private environment; TRACEMIND_USE_LLM=auto (or 1), not 0.')
        return 2
    output=gateway.request(EVIDENCE_SYSTEM,{'records':[
      {'id':'fake-001','at':'2026-11-02T09:00:00Z','author':'u2',
       'author_name':'Asha','client':'fake_account','type':'chat',
       'body':'No, Asha handles supplier onboarding now, not Rahul.'},
      {'id':'fake-002','at':'2026-11-02T10:00:00Z','author':'u3',
       'author_name':'Pooja','client':'fake_account','type':'chat',
       'body':'Vendor forms kal tak bhej dungi.'},
    ]},max_output=500)
    print(json.dumps({'ok':bool(output),'model':__import__('os').getenv('TRACEMIND_MODEL') or 'gpt-4.1-mini',
        'parsed':output,'usage':gateway.usage(__import__('time').monotonic()),
        'model_errors':gateway.errors},indent=2))
    return 0 if output else 1

if __name__=='__main__':raise SystemExit(main())
