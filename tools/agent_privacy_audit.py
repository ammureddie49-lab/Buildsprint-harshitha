#!/usr/bin/env python3
"""Offline adversarial privacy/source audit over every supplied public persona.

This is an *independent invariant check*, not the organizer's hidden-day score.
It does not read answer keys, call OpenAI, run Qdrant, or use a persistent DB.
It deliberately queries historical time after all public days have been ingested.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACK=Path(os.environ.get('R3_PACK') or ROOT).resolve()
sys.path.insert(0,str(ROOT))
os.environ['TRACEMIND_USE_LLM']='0'
os.environ['TRACEMIND_VECTOR_DB']='0'
os.environ['R3_PACK']=str(PACK)
from tracemind import Engine, datetime_utc


def main():
    checks={'person_day_scopes':0,'authorized_records_checked':0,'forbidden_records_checked':0,
            'derived_fact_sources_checked':0,'brief_citations_checked':0,
            'question_citations_checked':0}
    failures=[]
    if not (PACK/'data/days/day-01.jsonl').is_file():
        print('Set R3_PACK to the organizer pack containing data/days/day-01.jsonl', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix='tracemind-security-audit-') as temp:
        engine=Engine(db_path=Path(temp)/'ephemeral.sqlite3')
        try:
            for day in range(1,6):
                output=engine.ingest(day,allow_model=False)
                if not output.get('ok'):failures.append(f'Failed ingest day {day}')
            all_rows=engine._rows()
            for person in sorted(engine.people_by_id):
                for day in range(1,6):
                    daydate=f'2026-11-{day+1:02d}'
                    cutoff=f'{daydate}T23:59:59Z'
                    allowed=engine.allowed(person,cutoff)
                    ids={r['id'] for r in allowed}
                    checks['person_day_scopes']+=1
                    for r in all_rows:
                        eligible=(engine.visible(r,person) and
                                  datetime_utc(r.get('at'))<=datetime_utc(cutoff) and
                                  not engine.is_forgotten(r,person))
                        key='authorized_records_checked' if eligible else 'forbidden_records_checked'
                        checks[key]+=1
                        if (r['id'] in ids)!=bool(eligible):
                            failures.append(f'Access mismatch for {person}, {day}, {r["id"]}')
                    for row in engine.deadlines.db.execute('SELECT source_id FROM temporal_facts'):
                        if row['source_id'] in ids:
                            checks['derived_fact_sources_checked']+=1
                    for brief in engine.brief(person,f'2026-11-{day+2:02d}',as_of=cutoff,allow_model=False):
                        refs=[]
                        for change in brief.get('changed',[]):refs+=change.get('sources',[])
                        for promise in brief.get('promises',[]):refs+=promise.get('sources',[])
                        for opened in brief.get('open_these',[]):refs.append(opened.get('record'))
                        question=brief.get('question_to_ask') or {}
                        refs+=question.get('sources',[])
                        checks['brief_citations_checked']+=len(refs)
                        if not set(refs).issubset(ids):
                            failures.append(f'Unauthorized brief sources for {person} on day {day}')
            for day in range(1,6):
                tasks=json.loads((PACK/f'data/tasks/day-{day:02d}.json').read_text(encoding='utf-8'))
                for q in tasks.get('asks',[]):
                    person=q['person'];at=q['at']
                    answer=engine.ask(person,at,q['ask'],allow_model=False)
                    sources=(answer.get('answer') or {}).get('sources',[])
                    for matched in answer.get('matched',[]):sources+=matched.get('sources',[])
                    ids={r['id'] for r in engine.allowed(person,at)}
                    checks['question_citations_checked']+=len(sources)
                    if not set(sources).issubset(ids):
                        failures.append(f'Unauthorized question sources {q.get("qid")}')
        finally:engine.db.close()
    result={'status':'PASS' if not failures else 'FAIL','checks':checks,'violations':failures[:30],
            'limitations':['Public fixture only','Permission/citation invariants, not semantic entailment',
                           'OpenAI and real Qdrant runtimes not invoked','Not authenticated multi-user penetration testing']}
    print(json.dumps(result,indent=2))
    return 0 if not failures else 1


if __name__=='__main__':raise SystemExit(main())
