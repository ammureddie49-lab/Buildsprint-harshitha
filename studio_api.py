"""TraceMind Intelligence Studio — local demo API, layered over the official CLI.

Demo persona switching is NOT authentication: bind to 127.0.0.1, not a public host.
Studio state is isolated from the official CLI database. All source-facing routes
use Engine.allowed(person, as_of) so private/restricted/org/forget filters apply.
"""
from __future__ import annotations

import collections
import contextlib
import datetime as dt
import json
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tracemind import Engine, datetime_utc, iso_date
from studio_retrieval import retriever

ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')  # optional local-only configuration; never returned to the browser
except ImportError:
    pass
STUDIO_DB = Path(os.environ.get('TRACEMIND_STUDIO_DB') or str(ROOT / '.tracemind_studio.sqlite3'))
DAY0 = dt.date(2026, 11, 2)  # Supplied public fixture's first observation day.
AVAILABLE_DAYS = (1,2,3,4,5)
app = FastAPI(title='TraceMind Intelligence Studio', version='1.0.0', description='Local evidence and memory demonstrator')


@app.middleware('http')
async def enforce_local_demo_only(request: Request, call_next):
    """Persona switching is not authentication; deny non-loopback network use.

    Do not trust HTTP Host or forwarded headers: the ASGI transport's peer
    address is the enforced boundary. A reverse proxy still needs real auth.
    """
    peer=request.client.host if request.client else None
    if peer not in ('127.0.0.1', '::1', 'localhost', 'testclient'):
        return JSONResponse(status_code=403,content={'detail':'Studio is localhost-only; no remote authentication is configured.'})
    return await call_next(request)


def cutoff(day):
    return f'{(DAY0 + dt.timedelta(days=day-1)).isoformat()}T23:59:59Z'


def meeting_date(day):
    return (DAY0 + dt.timedelta(days=day)).isoformat()


def session_engine():
    return Engine(db_path=STUDIO_DB)


@contextlib.contextmanager
def open_engine(person=None):
    eng=session_engine()
    try:
        if person is not None and person not in eng.people_by_id:
            raise HTTPException(status_code=400, detail='Unknown demo persona')
        yield eng
    finally:
        eng.db.close()


def require_day(day):
    if day not in AVAILABLE_DAYS:
        raise HTTPException(400, 'Select a public day from 1 to 5')
    return day


@contextlib.contextmanager
def scoped_engine(person, day):
    """Time-scope both source records AND feedback for historic demo views."""
    with open_engine(person) as eng:
        # A day selector is a genuine historical snapshot: no future records or feedback.
        rows = [r for r in eng._rows() if datetime_utc(r.get('at')) <= datetime_utc(cutoff(day))]
        previous = eng._feedback()
        eng._rows = lambda: rows
        eng._feedback = lambda: [f for f in previous if int(f.get('day') or 0) < day]
        yield eng


def available(eng,person,day,client=None):
    rows=eng.allowed(person,cutoff(day))
    return [r for r in rows if client is None or r.get('client')==client]


def short_record(r,eng):
    return {"id":r['id'],"type":r.get('type','record'),"client":r.get('client'),
            "title":r.get('title') or r.get('subject') or r.get('body','').splitlines()[0][:75] or 'Untitled record',
            "body":(r.get('body') or '')[:330],"author":eng.name(r.get('author')),
            "author_id":r.get('author'),"visibility":r.get('visibility','team'),"at":r.get('at'),
            "day":r.get('day'),"task_id":r.get('task_id'),"status":r.get('status'),
            "due":r.get('due'),"source_id":r['id']}


def seed_demo():
    with open_engine() as eng:
        row=eng.db.execute("SELECT value FROM meta WHERE key='ingested_day'").fetchone()
        current=int(row['value']) if row and row['value'].isdigit() else 0
        for day in AVAILABLE_DAYS:
            if day > current:
                eng.ingest(day,allow_model=False)


@app.on_event('startup')
def init_studio():
    seed_demo()


@app.get('/api/health')
def health():
    with open_engine() as eng:
        return {"ok":True,"records":eng.db.execute('SELECT COUNT(*) FROM records').fetchone()[0],
                "database":"studio_isolated","mode":"local_demo"}


@app.get('/api/bootstrap')
def bootstrap():
    with open_engine() as eng:
        persons=[{"id":pid,"name":p.get('name'),"role":p.get('role'),"org":p.get('org'),
                  "org_name":"Kitepoint Studio" if p.get('org')=='org_kp' else 'Other organization'}
                 for pid,p in eng.people_by_id.items()]
        return {"days":list(AVAILABLE_DAYS),"default_day":3,"default_person":"p02",
                "persons":persons,"clients":eng.clients,
                "meeting_dates":{i:meeting_date(i) for i in AVAILABLE_DAYS},
                "demo_warning":"Demo persona selector is not authentication. Local-only; do not publish this API.",
                "model_configured":bool(os.environ.get('OPENAI_API_KEY') or os.environ.get('TRACEMIND_API_KEY')),
                "hybrid_cli_enabled":__import__('tracemind_hybrid').Gateway.enabled(),
                "remote_allowed":os.environ.get("TRACEMIND_STUDIO_ALLOW_REMOTE_LLM")=="1"}


@app.get('/api/dashboard')
def dashboard(person:str,day:int=Query(3,ge=1,le=5)):
    with scoped_engine(person,day) as eng:
        permitted=available(eng,person,day)
        tasks=eng.task_states(permitted)
        meetings=[r for r in permitted if r.get('type')=='event' and person in r.get('attendees',[])]
        upcoming=[r for r in meetings if iso_date(r.get('start'),eng.zone(person)).isoformat()==meeting_date(day)]
        types=collections.Counter(r.get('type','other') for r in permitted)
        clients=collections.Counter(r.get('client') for r in permitted if r.get('client'))
        by_status=collections.Counter(s.get('status','unknown') for s in tasks.values())
        tasklist=sorted(tasks.values(), key=lambda s:s.get('due') or '9999')[:12]
        signals=[]
        for r in reversed(permitted):
            if r.get('type')=='notification':continue
            sig=eng._business_signal(r)
            if sig:
                signals.append({"text":sig[1],"source":r['id'],"client":r.get('client'),"at":r.get('at'),"priority":sig[0]})
            if len(signals)>=9:break
        return {"person":person,"name":eng.name(person),"org":eng.org(person),"day":day,"as_of":cutoff(day),
                "stats":{"records":len(permitted),"tasks":len(tasks),"meetings":len(upcoming),
                         "blocked":by_status['blocked'],"done":by_status['done'],"sources":len(permitted),
                         "private":sum(1 for r in permitted if r.get('visibility')=='private')},
                "record_types":dict(types),"client_counts":dict(clients),"task_statuses":dict(by_status),
                "tasks":[{"id":s['task_id'],"title":s.get('title'),"status":s.get('status'),"owner":eng.name(s.get('owner')),
                           "due":s.get('due'),"client":s.get('client'),"source":s.get('sources',{}).get('status') or s.get('last_record')} for s in tasklist],
                "meetings":[{"id":r.get('event_id'),"title":r.get('title'),"start":r.get('start'),"client":r.get('client')} for r in upcoming],
                "signals":signals,
                "recent":[short_record(r,eng) for r in reversed(permitted) if r.get('type')!='notification'][:7]}


@app.get('/api/records')
def list_records(person:str,day:int=Query(3,ge=1,le=5),client:str|None=None,type:str|None=None,q:str='',limit:int=Query(30,ge=1,le=80)):
    with scoped_engine(person,day) as eng:
        rows=available(eng,person,day,client)
        if type and type!='all':rows=[r for r in rows if r.get('type')==type]
        if q.strip():
            needle=q.casefold().strip(); rows=[r for r in rows if needle in ' '.join(str(r.get(k,'')) for k in ('body','title','subject','task_id','client')).casefold()]
        total=len(rows)
        return {"total":total,"items":[short_record(r,eng) for r in reversed(rows[-limit:])]}


@app.get('/api/sources/{record_id}')
def source_record(record_id:str,person:str,day:int=Query(3,ge=1,le=5)):
    with scoped_engine(person,day) as eng:
        record=next((r for r in available(eng,person,day) if r['id']==record_id),None)
        if record is None:raise HTTPException(404,'Source not found or inaccessible')
        return {"record":record,"author_name":eng.name(record.get('author'))}


@app.get('/api/briefs')
def briefs(person:str,day:int=Query(3,ge=1,le=5)):
    with scoped_engine(person,day) as eng:
        # Time-bound only in the optional Studio API; official CLI behavior unchanged.
        result=eng.brief(person,meeting_date(day),as_of=cutoff(day),allow_model=False)
        events={r.get('event_id'):r for r in available(eng,person,day) if r.get('type')=='event'}
        return {"day":day,"date":meeting_date(day),"briefs":[{**b,"title":events.get(b['meeting_id'],{}).get('title','Meeting brief'),
             "client":events.get(b['meeting_id'],{}).get('client')} for b in result]}


@app.get('/api/memory')
def memory(person:str,day:int=Query(3,ge=1,le=5)):
    with scoped_engine(person,day) as eng:
        rows=available(eng,person,day)
        fbs=[f for f in eng._feedback() if f.get('person')==person and (f.get('day') or 0) < day]
        # The ledger entries are untrusted derived metadata; source IDs must be visible.
        ids={r['id'] for r in rows}
        facts=[]
        for row in eng.db.execute('SELECT * FROM temporal_facts ORDER BY rowid DESC LIMIT 150'):
            d=dict(row)
            if d.get('source_id') not in ids:continue
            facts.append({k:d.get(k) for k in ('source_id','subject','value','kind','at','client') if k in d})
            if len(facts)==12:break
        return {"feedback":fbs,"forget_topics":[t for t,_ in eng.forget_terms(person)],
                "facts":facts,"record_count":len(rows)}


class AskRequest(BaseModel):
    person:str
    day:int=Field(default=3,ge=1,le=5)
    question:str=Field(min_length=2,max_length=600)
    mode:str='baseline'


@app.post('/api/ask')
def ask(request:AskRequest):
    with scoped_engine(request.person,request.day) as eng:
        t0=time.perf_counter();at=cutoff(request.day)
        result=eng.ask(request.person,at,request.question,allow_model=False)
        sources={r['id'] for r in available(eng,request.person,request.day)}
        # The official engine is trusted for its answer logic; independently verify citation access.
        ans=result.get('answer')
        if ans and not set(ans.get('sources') or []).issubset(sources):
            result['answer']=None;result['refused']={'reason':'Source access validation failed'}
        evidence={"mode":"baseline","neural_used":False,"latency_ms":0,"error":None,"evidence":[]}
        if request.mode in ('lexical','hybrid','vector','model'):
            client=eng.resolve_client(request.question,available(eng,request.person,request.day))
            evidence=retriever.search(request.question,available(eng,request.person,request.day),request.person,request.day,client,mode='lexical' if request.mode=='model' else request.mode,limit=7)
        note="Evidence suggestions are retrieved records, not independently verified answers."
        if request.mode=='model':
            import llm_adapter
            ready=(os.environ.get('TRACEMIND_STUDIO_ALLOW_REMOTE_LLM')=='1' and llm_adapter.enabled())
            if not ready:
                note="External reasoning is disabled. Set explicit environment configuration to opt in."
            elif not result.get('refused') and not result.get('clarify') and (not result.get('answer') or not result['answer'].get('sources')):
                # External model is ALWAYS restricted to permitted TEAM records,
                # even with provider enabled. No private/restricted notes leave the host.
                visible_team={r['id']:r for r in available(eng,request.person,request.day) if r.get('visibility')=='team'}
                subset=[visible_team[x['id']] for x in evidence['evidence'] if x['id'] in visible_team][:7]
                generated=llm_adapter.grounded_ask(request.question,subset,request.person)
                if generated:
                    proposed,model_usage=generated
                    proposed_sources=(proposed.get('answer') or {}).get('sources') or []
                    if set(proposed_sources).issubset(visible_team):
                        result.update(proposed);result['usage']=model_usage
                        note="Optional external reasoning used only visible team evidence and checked source access."
                    else:note="Model citations failed access verification; deterministic response retained."
                else:note="No validated model output; deterministic response retained."
        return {"result":result,"retrieval":evidence,"mode":request.mode,
                "elapsed_ms":round((time.perf_counter()-t0)*1000,1),
                "note":note}


class ForgetRequest(BaseModel):
    person:str
    what:str=Field(min_length=2,max_length=300)


@app.post('/api/forget')
def forget(request:ForgetRequest):
    with open_engine(request.person) as eng:
        return eng.forget(request.person,request.what)


@app.post('/api/demo-reset')
def reset_demo():
    """Explicit local demo reset. Not exposed as a production admin interface."""
    with open_engine() as eng:
        for d in AVAILABLE_DAYS:
            eng.ingest(d,allow_model=False)
        from studio_actions import setup as setup_local
        setup_local(eng.db)
        with eng.db:
            for table in ('studio_actions','studio_memory','studio_items'):
                eng.db.execute(f'DELETE FROM {table}')
    return {"ok":True,"days":list(AVAILABLE_DAYS),"note":"Demo memory reset to the supplied public feed."}


@app.get('/api/evaluation')
def evaluation():
    # Display only actual measured score files from this workspace.
    for path in (ROOT/'runs/studio-score/score.json',ROOT/'runs/final-check/score.json',ROOT/'runs/temporal-v2/score.json'):
        if path.exists():
            try:
                score=json.loads(path.read_text(encoding='utf-8'))
                return {"available":True,"source":str(path.relative_to(ROOT)),"score":{k:score.get(k) for k in ('days','total','max_scored','areas','usefulness','privacy_leaks','per_day')}}
            except (OSError,ValueError):pass
    return {"available":False,"message":"Run the official public scorer to populate verified evaluation data."}


@app.get('/api/vector-status')
def vector_status():
    """Report *actual* dependency availability, not an invented vector count."""
    from importlib.util import find_spec
    import tracemind_vector_db
    return {
        'provider': 'qdrant-local',
        'installed': find_spec('qdrant_client') is not None,
        'embedder_installed': find_spec('sentence_transformers') is not None,
        'database_path': str(tracemind_vector_db.db_path()),
        'requires_openai_key': False,
        'cli_opt_in': tracemind_vector_db.enabled(),
        'status': 'ready_to_open' if (find_spec('qdrant_client') and find_spec('sentence_transformers')) else 'dependencies_missing',
        'note': 'Local embedded Qdrant. Status is not a claim that indexing has completed.'
    }


@app.get('/api/neural-benchmark')
def neural_benchmark():
    for path in (ROOT/'runs/neural_warm.json',ROOT/'runs/neural_benchmark.json'):
        if path.exists():
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                return {"available":True,"source":str(path.relative_to(ROOT)),
                        "dataset":data.get('dataset'),"lexical":data.get('lexical'),
                        "neural":data.get('neural'),"model_load_ms":data.get('model_load_ms')}
            except (OSError,ValueError):pass
    return {"available":False,"message":"Run tools/benchmark_semantic.py to populate the retrieval comparison."}



# ---- TraceMind Workbench: model-directed tools + human-approved actions ----
# Kept outside the scored CLI to preserve its exact protocol.
from studio_actions import (setup as setup_actions, list_actions, list_items,
                            list_memory, confirm as decide_action)
from studio_agent import Agent

class AgentRequest(BaseModel):
    person: str
    day: int = Field(default=3, ge=1, le=5)
    question: str = Field(min_length=2, max_length=850)
    api_key: str = Field(default='', repr=False, max_length=250)
    consent: bool = False
    model: str = 'gpt-4.1-mini'
    retrieval: str = 'lexical'
    history: list[dict] = Field(default_factory=list, max_length=6)

@app.post('/api/agent')
def agent_chat(request:AgentRequest):
    if not request.consent:
        raise HTTPException(400, 'Enable external OpenAI mode explicitly before using it.')
    if request.model not in ('gpt-4.1-mini','gpt-4o-mini','gpt-4.1','gpt-5-mini'):
        raise HTTPException(400, 'Unsupported model; choose an available listed option.')
    if not request.api_key.strip() and not os.environ.get('OPENAI_API_KEY'):
        raise HTTPException(400, 'Provide an OpenAI API key for this session or set OPENAI_API_KEY in the server environment.')
    with scoped_engine(request.person,request.day) as eng:
        try:
            runner=Agent(eng,request.person,request.day,cutoff(request.day),
                         mode=request.retrieval,model=request.model)
            return {'result':runner.ask(request.question,request.history,api_key=request.api_key),
                    'mode':'openai_tools','note':'Only organization-authorized TEAM records may reach OpenAI. Pending actions require separate confirmation.'}
        except Exception as exc:
            # Never echo SDK request parameters, credentials, or private source data.
            raise HTTPException(502, f'OpenAI request failed ({type(exc).__name__}). Verify the key, model access and network.')

class ActionDecision(BaseModel):
    person: str
    day: int = Field(default=3,ge=1,le=5)
    approve: bool

class ManualActionRequest(BaseModel):
    person: str
    type: str
    title: str = Field(min_length=2,max_length=120)
    details: str = ''
    due: str = ''
    target_id: str = ''
    memory_kind: str = 'none'
    source_ids: list[str] = Field(default_factory=list)

@app.post('/api/actions/prepare')
def manual_prepare(req:ManualActionRequest):
    from studio_actions import stage
    with open_engine(req.person) as eng:
        if req.type=='remember' and req.memory_kind=='fact':
            # Human-provided fact memory still needs a valid current visible source.
            visible_ids={r['id'] for r in eng.allowed(req.person)}
            if not req.source_ids or not set(req.source_ids).issubset(visible_ids):
                raise HTTPException(400,'Factual memory requires an accessible source ID.')
        try:
            action=stage(eng.db,req.person,eng.org(req.person),req.type,req.model_dump())
        except ValueError as exc:raise HTTPException(400,str(exc))
        return {'action':action}

@app.get('/api/actions')
def get_actions(person:str,day:int=Query(3,ge=1,le=5)):
    with scoped_engine(person,day) as eng:
        return {'actions':list_actions(eng.db,person,eng.org(person)),
                'items':list_items(eng.db,person,eng.org(person))}

@app.post('/api/actions/{action_id}/decision')
def confirm_action(action_id:str,request:ActionDecision):
    with scoped_engine(request.person,request.day) as eng:
        allowed_ids={r['id'] for r in available(eng,request.person,request.day)}
        try:
            result=decide_action(eng.db,action_id,request.person,eng.org(request.person),
                                 request.approve,allowed_sources=allowed_ids,
                                 forget_callback=eng.forget)
        except PermissionError:raise HTTPException(404,'Action not found for this identity')
        except ValueError as exc:raise HTTPException(400,str(exc))
        return result

@app.get('/api/local-memory')
def local_memory(person:str,day:int=Query(3,ge=1,le=5)):
    with scoped_engine(person,day) as eng:
        ids={r['id'] for r in available(eng,person,day)}
        memo=[m for m in list_memory(eng.db,person,eng.org(person)) if set(m['sources']).issubset(ids)]
        return {'memories':memo}

@app.get('/api/capabilities')
def capabilities():
    return {'available_tools':['search_evidence','read_source','list_tasks','list_meetings',
                               'recall_memory','prepare_action'],
            'approvable_actions':['create_task','update_task','schedule_meeting','schedule_call',
                                   'draft_message','remember','forget'],
            'limits':{'phone_calls':'local scheduling only; no dialing',
                      'messages':'drafted locally; never sent',
                      'meetings':'local schedule only; no provider calendar updates',
                      'shared_records':'never mutated by agent',
                      'memory':'user-approved, person-scoped',
                      'external_evidence':'team only, no private or restricted records'},
            'model_mode':'OpenAI Responses SDK function tools; no LangGraph'}

# Optional static production UI, registered after API routes to prevent shadowing.
DIST = ROOT / "studio-frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="studio")
