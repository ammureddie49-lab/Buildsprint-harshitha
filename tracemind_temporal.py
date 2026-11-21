"""Durable, source-linked, permission-scoped temporal facts for TraceMind.

Explicit deadline claims only. Evidence text is NEVER treated as instructions.
The containing Engine must filter permitted source records before any query.
No external dependencies or model calls.
"""
from __future__ import annotations
import datetime as dt
import re
import sqlite3
from dataclasses import dataclass

MONTHS={month.lower():i+1 for i,month in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])}
DATE_PAT=(r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+'
          r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*(?:\d{4})?'
          r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+'
          r'\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)')
DATE_RE=re.compile(DATE_PAT,re.I)
TOKEN_RE=re.compile(r'[a-z0-9]+',re.I)
SKIP={'the','a','an','on','for','of','is','are','due','date','deadline','target','when','what',
      'was','will','now','moved','to','from','by','new','that','project','client','account',
      'did','does','have','has','be','at','we','our','my','please','tell','me','this','scheduled'}
LEADING=re.compile(r'^(?:hi|hello|fyi|update|heads up|note|the|our|new|revised)\b[\s,:-]*',re.I)


def subject_terms(s):
    return set(x for x in TOKEN_RE.findall(s.lower()) if len(x)>1 and x not in SKIP)


def clean_subject(s):
    s=re.sub(r'\s+',' ',s).strip(' \t,.:-')
    s=re.sub(r'(?i)^(?:the|our)\s+','',s)
    for _ in range(2):s=LEADING.sub('',s)
    return s.strip(' \t,.:-')[:125]


def date_value(text,observed):
    try:
        match=DATE_RE.search(text)
        if not match:return None
        s=match.group(0).strip().replace(',','')
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',s):return dt.date.fromisoformat(s).isoformat()
        parts=s.split()
        year=int(parts[-1]) if re.fullmatch(r'\d{4}',parts[-1]) else int(observed[:4])
        if parts[0].rstrip('0123456789').lower()[:3] in MONTHS:
            month=MONTHS[parts[0].lower()[:3]]
            day=int(re.sub(r'(st|nd|rd|th)$','',parts[1],flags=re.I))
        else:
            day=int(re.sub(r'(st|nd|rd|th)$','',parts[0],flags=re.I))
            month=MONTHS[parts[1].lower()[:3]]
        return dt.date(year,month,day).isoformat()
    except (ValueError, IndexError, TypeError):return None


def extract(record):
    if record.get('type') not in {'mail','chat','note','doc'}:return []
    text=record.get('body') or ''
    if not text or len(text)>10000:return []
    # A directive embedded in workplace content never becomes fact evidence,
    # even when the directive and bogus fact are separate sentences.
    if re.search(r'(?i)\b(?:assistant|system)\s*:\s*|\bignore\s+(?:all\s+)?previous\s+(?:instructions|rules)\b',text):return []
    out=[]
    patterns=[
        # 'Product rollout deadline moved from Nov 10 to Nov 18'
        re.compile(r'(?P<subject>[\w][\w\s/&\-]{3,105}?)\s+(?:is\s+|was\s+)?(?:now\s+)?(?:due\s+date|deadline|delivery\s+date|target\s+date)?\s*(?:is\s+|has\s+been\s+)?(?:moved|shifted|postponed|rescheduled|changed)\s+(?:from\s+'+DATE_PAT+r'\s+)?to\s+(?P<date>'+DATE_PAT+r')',re.I),
        # 'Product rollout is due on Nov 18' / 'Product rollout deadline: Nov 18'
        re.compile(r'(?P<subject>[\w][\w\s/&\-]{3,105}?)\s+(?:is\s+|was\s+)?(?:now\s+)?(?:due\s+date|deadline|delivery\s+date|target\s+date|due)\s*(?:(?:is|set for|on|by|at|for|:)\s*)*(?P<date>'+DATE_PAT+r')',re.I),
        # 'Deadline for product rollout is Nov 18'
        re.compile(r'^(?:new\s+|updated\s+)?(?:deadline|due\s+date|target\s+date|delivery\s+date)\s+for\s+(?P<subject>[\w][\w\s/&\-]{3,105}?)\s+(?:is\b|now\b|on\b|by\b|moved\s+to\b|[:=])\s*(?P<date>'+DATE_PAT+r')',re.I),
        # 'Release date: 10 Nov 2026'
        re.compile(r'(?P<subject>[\w][\w\s/&\-]{3,70}?(?:launch|release|delivery|handoff|rollout))\s+date\s*:\s*(?P<date>'+DATE_PAT+r')',re.I),
    ]
    revoke=re.compile(r'(?P<subject>[\w][\w\s/&\-]{3,105}?)\s+(?:is\s+|was\s+)?no\s+longer\s+due\s+(?:on|by)?\s*(?P<date>'+DATE_PAT+r')',re.I)
    for line in text.splitlines():
        for sentence in re.split(r'(?<=[.!?])\s+',line):
            sentence=sentence.strip().strip('•*- ')
            if not sentence or len(sentence)>350:continue
            if re.search(r'(?i)(?:\bif\b|\bmight\b|\bmaybe\b|\bcould\b|\bperhaps\b|\bhypothetically\b|\bignore\s+previous\b|\bassistant\s*:|\bsystem\s*:)',sentence):continue
            if sentence.endswith('?'):continue
            kind='due';matches=[]
            rev=revoke.search(sentence)
            if rev:matches=[rev];kind='retracted'
            else:
                for pattern in patterns:
                    m=pattern.search(sentence)
                    if m:matches=[m];break
            for m in matches:
                subject=clean_subject(m.group('subject'))
                day=date_value(m.group('date'),record.get('at','2026-11-01'))
                if not day or not subject_terms(subject) or len(subject_terms(subject))>14:continue
                out.append((subject,day,kind))
    return list(dict.fromkeys(out))


class DeadlineLedger:
    def __init__(self,connection:sqlite3.Connection):
        self.db=connection
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS temporal_facts (
          source_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
          org TEXT, client TEXT, at TEXT NOT NULL, author TEXT,
          subject TEXT NOT NULL, value TEXT NOT NULL, kind TEXT NOT NULL,
          PRIMARY KEY(source_id,ordinal));
        CREATE INDEX IF NOT EXISTS idx_temporal_facts ON temporal_facts(org,client,at);
        ''')

    def ingest(self, records):
        for record in records:
            for index,(subject,value,kind) in enumerate(extract(record)):
                self.db.execute('''INSERT OR IGNORE INTO temporal_facts
                  (source_id,ordinal,org,client,at,author,subject,value,kind)
                  VALUES (?,?,?,?,?,?,?,?,?)''',(
                    record['id'],index,record.get('org'),record.get('client'),
                    record.get('at',''),record.get('author'),subject,value,kind))

    def purge(self,source_ids):
        for source_id in source_ids:
            self.db.execute('DELETE FROM temporal_facts WHERE source_id=?',(source_id,))

    def answer(self,question,allowed_records,people,client=None):
        """Only consult fact source IDs available to this requester at this timestamp."""
        if not re.search(r'(?i)\b(?:when|deadline|due\s+date|date\s+for)\b',question):return None
        if not re.search(r'(?i)\b(?:due|deadline|scheduled|date|happening)\b',question):return None
        allowed={r['id']:r for r in allowed_records}
        if not allowed:return None
        topic=re.sub(r'(?i)\b(?:when\s+(?:is|was|will|does)|what\s+(?:is|was|\'s)|deadline\s+(?:for|of)|due\s+date\s+(?:for|of)|is\s+the|the|for|on|by|due|date|scheduled|happening|client)\b',' ',question)
        topic_terms=subject_terms(topic)
        if not topic_terms:return None
        if client:
            topic_terms-=subject_terms(client)
        if not topic_terms:return None
        matches=[]
        for row in self.db.execute('SELECT source_id, org, client, at, author, subject, value, kind FROM temporal_facts'):
            if row['source_id'] not in allowed:continue
            if client is not None and row['client']!=client:continue
            record=allowed[row['source_id']]
            if row['client'] and row['client'] in topic_terms:
                pass
            fact_terms=subject_terms(row['subject'])
            common=topic_terms&fact_terms
            coverage=len(common)/max(1,len(topic_terms))
            precision=len(common)/max(1,len(fact_terms))
            if not common or coverage<0.6 or precision<0.45:continue
            role=people.get(row['author'],{}).get('role','').lower()
            authority=4 if any(x in role for x in ('founder','director')) else 3 if any(x in role for x in ('manager','lead')) else 1 if 'intern' in role else 2
            matches.append((0.7*coverage+0.3*precision,authority,row))
        if not matches:return None
        max_relevance=max(x[0] for x in matches)
        near=[x for x in matches if x[0]>=max_relevance-0.09]
        # Without client context, competing clients with the same relevant topic are ambiguous.
        if client is None and len({x[2]['client'] for x in near})>1:return None
        # Different subjects with indistinguishable evidence must not be guessed.
        best_topic=max(near,key=lambda x:(x[0],x[1],x[2]['at']))[2]['subject']
        best_terms=subject_terms(best_topic)
        near=[x for x in near if len(subject_terms(x[2]['subject'])&best_terms)/max(1,len(best_terms))>=0.65]
        near.sort(key=lambda x:(x[1],x[2]['at'],x[0]),reverse=True)
        best=near[0][2]
        if best['kind']=='retracted':return None
        return {'text':f"{best['subject']} is due {best['value']}.",'sources':[best['source_id']]}
