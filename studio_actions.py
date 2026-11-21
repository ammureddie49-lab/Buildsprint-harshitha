"""Local, auditable action proposals and user-scoped memory for TraceMind Studio.

These tables are deliberately NOT part of the scored CLI. Actions are prepared by
models, but only a human can confirm them through the local demo UI. No SMS, email,
telephone, calendar-provider or other external action is performed.
"""
from __future__ import annotations
import datetime as dt
import json
import re
import sqlite3
import uuid

KINDS = {'create_task', 'update_task', 'schedule_meeting', 'schedule_call', 'draft_message', 'remember', 'forget'}
MEMORY_KINDS = {'preference', 'fact', 'note'}

def _now(): return dt.datetime.now(dt.timezone.utc).isoformat()

def setup(db:sqlite3.Connection):
    db.execute('''CREATE TABLE IF NOT EXISTS studio_actions (
      id TEXT PRIMARY KEY, person TEXT NOT NULL, org TEXT NOT NULL, type TEXT NOT NULL,
      args TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL,
      resolved TEXT, result TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS studio_memory (
      id TEXT PRIMARY KEY, person TEXT NOT NULL, org TEXT NOT NULL, kind TEXT NOT NULL,
      topic TEXT NOT NULL, value TEXT NOT NULL, sources TEXT NOT NULL, at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'active', superseded_by TEXT, valid_until TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS studio_items (
      id TEXT PRIMARY KEY, person TEXT NOT NULL, org TEXT NOT NULL, type TEXT NOT NULL,
      title TEXT NOT NULL, details TEXT, when_at TEXT, status TEXT NOT NULL,
      created TEXT NOT NULL)''')
    # Backward-compatible migration for an already-used Studio database.
    names={row[1] for row in db.execute('PRAGMA table_info(studio_memory)')}
    for column, ddl in (('status',"TEXT NOT NULL DEFAULT 'active'"),
                        ('superseded_by','TEXT'),('valid_until','TEXT')):
        if column not in names:
            db.execute(f'ALTER TABLE studio_memory ADD COLUMN {column} {ddl}')
    db.commit()

def _text(s, maxlen=300): return str(s or '').strip()[:maxlen]

def stage(db, person, org, kind, args):
    setup(db)
    if kind not in KINDS: raise ValueError('Unsupported action')
    if not person or not org:raise ValueError('Unknown demo identity')
    data = {
      'title':_text(args.get('title'),110),
      'details':_text(args.get('details'),650),
      'due':_text(args.get('due'),40),
      'target_id':_text(args.get('target_id'),80),
      'memory_kind':_text(args.get('memory_kind'),20),
      'source_ids':list(dict.fromkeys([_text(x,80) for x in (args.get('source_ids') or []) if _text(x,80)]))[:6],
    }
    if kind in {'create_task','schedule_meeting','schedule_call','draft_message','remember','forget'} and not data['title']:
        raise ValueError('A title/topic is required')
    if kind == 'update_task' and not data['target_id']:
        raise ValueError('Provide the ID of a Studio-created task to update')
    if kind == 'remember' and data['memory_kind'] not in MEMORY_KINDS:
        raise ValueError('Memory type must be preference, note or fact')
    aid='act_'+uuid.uuid4().hex[:12]
    with db:
        db.execute('INSERT INTO studio_actions VALUES (?,?,?,?,?,?,?,?,?)',
                   (aid,person,org,kind,json.dumps(data), 'pending',_now(),None,None))
    return {'id':aid,'type':kind,'args':data,'status':'pending'}

def _row(db, aid):
    row=db.execute('SELECT * FROM studio_actions WHERE id=?',(aid,)).fetchone()
    return dict(row) if row else None

def list_actions(db,person,org,limit=30):
    setup(db)
    rows=db.execute('SELECT * FROM studio_actions WHERE person=? AND org=? ORDER BY created DESC LIMIT ?', (person,org,min(limit,80))).fetchall()
    return [{**dict(r),'args':json.loads(r['args']),'result':json.loads(r['result']) if r['result'] else None} for r in rows]

def list_items(db,person,org):
    setup(db)
    return [dict(r) for r in db.execute('SELECT * FROM studio_items WHERE person=? AND org=? ORDER BY created DESC',(person,org))]

def list_memory(db,person,org):
    setup(db)
    rows=db.execute('SELECT * FROM studio_memory WHERE person=? AND org=? ORDER BY at DESC',(person,org)).fetchall()
    today=dt.datetime.now(dt.timezone.utc).date().isoformat()
    return [{**dict(r),'sources':json.loads(r['sources']),
             'status':'expired' if r['status']=='active' and r['valid_until'] and r['valid_until']<today else r['status']}
            for r in rows]

def confirm(db,aid,person,org,approved,allowed_sources=None,forget_callback=None):
    setup(db)
    row=_row(db,aid)
    if not row or row['person']!=person or row['org']!=org:raise PermissionError('Action not found for this identity')
    if row['status']!='pending':raise ValueError('Action already resolved')
    args=json.loads(row['args']);kind=row['type']
    result={'approved':bool(approved)}
    if approved:
        if kind == 'remember':
            sources=args['source_ids']; allowed=set(allowed_sources or [])
            if sources and not set(sources).issubset(allowed):raise PermissionError('Memory source not accessible')
            if args['memory_kind']=='fact' and not sources:
                raise ValueError('Factual memory needs an accessible source ID')
            mid='mem_'+uuid.uuid4().hex[:12]
            db.execute('UPDATE studio_memory SET status=?,superseded_by=? WHERE person=? AND org=? AND kind=? AND lower(topic)=lower(?) AND status=?',
                       ('superseded',mid,person,org,args['memory_kind'],args['title'],'active'))
            valid_until=args['due'] if re.fullmatch(r'\d{4}-\d{2}-\d{2}',args['due']) else None
            db.execute('INSERT INTO studio_memory (id,person,org,kind,topic,value,sources,at,status,superseded_by,valid_until) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (mid,person,org,args['memory_kind'],args['title'],args['details'],json.dumps(sources),_now(),'active',None,valid_until))
            result['memory_id']=mid
        elif kind == 'forget':
            if forget_callback is None:raise ValueError('Forget handler missing')
            forget_callback(person,args['title'])
            # Also clear model-generated personal memories on the named topic.
            q=args['title'].lower()
            db.execute('DELETE FROM studio_memory WHERE person=? AND org=? AND (lower(topic) LIKE ? OR lower(value) LIKE ?)',(person,org,'%'+q+'%','%'+q+'%'))
            db.execute('DELETE FROM studio_items WHERE person=? AND org=? AND (lower(title) LIKE ? OR lower(coalesce(details,"")) LIKE ?)',
                       (person,org,'%'+q+'%','%'+q+'%'))
            db.execute("DELETE FROM studio_actions WHERE person=? AND org=? AND type!='forget' AND lower(args) LIKE ?",(person,org,'%'+q+'%'))
            result['forgot']=args['title']
        elif kind == 'update_task':
            local=db.execute('SELECT id FROM studio_items WHERE id=? AND person=? AND org=? AND type=?',
               (args['target_id'],person,org,'task')).fetchone()
            if not local: raise PermissionError('Only locally created tasks can be updated')
            if args['title']:
                db.execute('UPDATE studio_items SET title=? WHERE id=?',(args['title'],args['target_id']))
            if args['details']:
                db.execute('UPDATE studio_items SET details=? WHERE id=?',(args['details'],args['target_id']))
            if args['due']:
                db.execute('UPDATE studio_items SET when_at=? WHERE id=?',(args['due'],args['target_id']))
            result['item_id']=args['target_id']
        else:
            local_type={'create_task':'task','schedule_meeting':'meeting','schedule_call':'call','draft_message':'draft'}[kind]
            itemid='local_'+uuid.uuid4().hex[:12]
            db.execute('INSERT INTO studio_items VALUES (?,?,?,?,?,?,?,?,?)',
                       (itemid,person,org,local_type,args['title'],args['details'],args['due'],
                        'draft' if local_type=='draft' else 'planned',_now()))
            result.update({'item_id':itemid,'local_only':True})
    status='approved' if approved else 'rejected'
    db.execute('UPDATE studio_actions SET status=?,resolved=?,result=? WHERE id=?',
              (status,_now(),json.dumps(result),aid))
    db.commit()
    return {'id':aid,'type':kind,'status':status,'result':result}
