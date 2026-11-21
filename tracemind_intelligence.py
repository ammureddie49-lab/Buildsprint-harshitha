"""TraceMind intelligence add-on: permission-first retrieval and generic responsibility facts.

This module never loads the official answer keys, and never reads records from disk.
Callers must supply ONLY records that have passed visibility, time, and forget filters.

The default retrieval system is a local SQLite FTS5 BM25 index combined with
character n-gram similarity. Optional local SentenceTransformer embeddings can be
opted in; none are downloaded or used by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import math
import os
import re
import sqlite3
from typing import Iterable, Mapping

_TOKEN = re.compile(r"[\w]+", re.UNICODE)
_STOP = set("a an the for of to with from is are who who's whom what which person on at in now currently please could you tell me handles handle owns owner responsible accountability ownership work project task company client account and or does do did be will was were this that status update someone".split())
# General workplace vocabulary expansions, never person/client-specific aliases.
_EQUIV = (
    {"invoice", "invoicing", "billing", "payments", "payment"},
    {"handoff", "handover", "transfer", "ownership", "assignment", "assigned"},
    {"testing", "test", "qa", "verification", "quality"},
    {"deadline", "due", "deliver", "delivery", "date"},
    {"deploy", "deployment", "release", "rollout"},
    {"meeting", "sync", "checkin"},
)


def tokens(text: object) -> list[str]:
    return [s.lower() for s in _TOKEN.findall(str(text or "")) if len(s) > 1]


def terms(text: object) -> set[str]:
    return set(tokens(text)) - _STOP


def expanded_terms(text: object) -> set[str]:
    result = terms(text)
    for group in _EQUIV:
        if result & group:
            result.update(group)
    return result


def cosine_ngrams(left: str, right: str) -> float:
    def gram(s: str) -> Counter:
        s = " ".join(tokens(s))
        if len(s) < 3:
            return Counter([s]) if s else Counter()
        return Counter(s[i:i + 3] for i in range(len(s) - 2))
    a, b = gram(left), gram(right)
    if not a or not b:
        return 0.0
    numerator = sum(v * b[k] for k, v in a.items())
    return numerator / math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))


@dataclass(frozen=True)
class Hit:
    record: dict
    score: float
    lexical: float
    bm25: float


class EvidenceIndex:
    """Transient index over already-authorized records; never index forbidden rows.

    The SQLite index exists only in memory for one request. In addition to text
    search, a lexical synonym/character similarity layer helps queries with
    different wording. It does not claim to provide neural semantic search.
    """

    def __init__(self, authorized_records: Iterable[dict]):
        self.records = [r for r in authorized_records if r.get("id") and r.get("type") != "notification"]

    @staticmethod
    def content(r: dict) -> str:
        return " ".join(str(r.get(k) or "") for k in ("title", "subject", "name", "body"))

    def search(self, question: str, client: str | None = None, limit: int = 18) -> list[Hit]:
        # Filtering is done before any indexing or scoring to avoid leaked hints.
        records = [r for r in self.records if client is None or r.get("client") == client]
        if not records or not terms(question):
            return []
        docs = [(r, self.content(r)) for r in records]
        query = expanded_terms(question)
        bm25_rank = {}
        db = sqlite3.connect(":memory:")
        try:
            db.execute("CREATE VIRTUAL TABLE docs USING fts5(body, tokenize='unicode61')")
            db.executemany("INSERT INTO docs(rowid,body) VALUES(?,?)", ((i+1, txt) for i, (_,txt) in enumerate(docs)))
            # Escape all tokens by quoting them. This is an FTS query, never SQL interpolation.
            ftsquery = " OR ".join('"' + x.replace('"','') + '"' for x in sorted(query) if len(x)>1)
            if ftsquery:
                try:
                    for row, rank in db.execute("SELECT rowid, bm25(docs) FROM docs WHERE docs MATCH ? ORDER BY bm25(docs) LIMIT 80", (ftsquery,)):
                        bm25_rank[row-1] = max(0.0, -float(rank))
                except sqlite3.OperationalError:
                    pass
        finally:
            db.close()
        results = []
        qterms = terms(question)
        for i, (record, text) in enumerate(docs):
            dterms = terms(text)
            overlap = len(query & dterms) / max(1, len(qterms))
            exact = len(qterms & dterms) / max(1, len(qterms))
            phrase = 1.0 if " ".join(tokens(question)) in " ".join(tokens(text)) else 0.0
            # Char-gram similarity is useful for inflections; it is not treated
            # as sufficient evidence by itself.
            fuzzy = cosine_ngrams(question, text[:1500])
            lexical = 0.58 * exact + 0.27 * overlap + 0.1 * fuzzy + 0.05 * phrase
            score = lexical + 0.08 * min(1.0, bm25_rank.get(i, 0.0))
            if score >= 0.09 and (exact > 0 or overlap > 0):
                results.append(Hit(record, score, lexical, bm25_rank.get(i, 0.0)))
        return sorted(results, key=lambda h: (h.score, h.record.get("at", "")), reverse=True)[:limit]


@dataclass(frozen=True)
class Responsibility:
    subject_id: str
    role: str
    record_id: str
    at: str
    authority: int
    source_type: str
    client: str | None


def _authority(r: dict, people: Mapping[str, dict]) -> int:
    role = people.get(r.get("author"), {}).get("role", "").lower()
    if "founder" in role or "director" in role:
        return 4
    if "manager" in role or "lead" in role:
        return 3
    if "intern" in role:
        return 1
    return 2


def _candidate_names(people: Mapping[str, dict], org: str | None):
    # prefer full names over first names; first names only when unambiguous.
    choices = {}
    firsts = Counter(p.get("name", "").split()[0].casefold()
                     for p in people.values() if p.get("org") == org and p.get("name"))
    for pid, p in people.items():
        if p.get("org") != org:
            continue
        full = p.get("name", "")
        if full:
            choices[full.casefold()] = pid
            first = full.split()[0]
            if firsts[first.casefold()] == 1:
                choices.setdefault(first.casefold(), pid)
    return sorted(choices.items(), key=lambda pair: len(pair[0]), reverse=True)


def extract_responsibilities(records: Iterable[dict], people: Mapping[str, dict], org: str | None):
    """Extract explicit workplace responsibility claims from visible messages.

    Pattern matching is deliberately conservative: no guesses from proximity,
    instructions, negated claims or hypothetical statements.
    """
    names = _candidate_names(people, org)
    for r in records:
        if r.get("org") != org or r.get("type") not in ("chat", "mail", "note", "doc"):
            continue
        for line in re.split(r"[\n.!?]+", r.get("body", "") or ""):
            line = line.strip()
            if not line or len(line) > 400:
                continue
            if re.search(r"(?i)\b(?:if|maybe|perhaps|might|could|should|hypothetically|don't|not|never|no longer)\b", line):
                continue
            if re.search(r"(?i)\b(?:assistant|system|ignore previous|override instructions)\s*:", line):
                continue
            for name, pid in names:
                escaped = re.escape(name)
                # 'Anita will handle vendor onboarding' or 'Anita now owns vendor onboarding'
                pat = (r"(?i)(?<!\w)" + escaped + r"(?!\w)\s+"
                       r"(?:(?:is\s+)?(?:now\s+)?(?:responsible\s+for|accountable\s+for|handling|leading|in charge of)"
                       r"|(?:will\s+)?(?:handle|own|lead|manage|coordinate)"
                       r"|(?:is\s+)?taking\s+over|takes\s+over|now\s+owns)\s+"
                       r"(?:the\s+)?(?P<role>[\w\-/ &]{3,110})")
                for match in re.finditer(pat, line):
                    role = match.group("role").strip(" .,:;-")
                    role = re.sub(r"(?i)\s+(?:from now on|going forward|starting today|effective today)$", "", role).strip()
                    if not terms(role) or len(terms(role)) > 14:
                        continue
                    yield Responsibility(pid, role, r["id"], r.get("at", ""), _authority(r, people),r.get("type",""),r.get("client"))



def extract_retractions(records: Iterable[dict], people: Mapping[str, dict], org: str | None):
    """Find explicit, authoritative revocations of an earlier responsibility claim."""
    names = _candidate_names(people, org)
    for r in records:
        if r.get('org') != org or r.get('type') not in ('chat', 'mail', 'note', 'doc'):
            continue
        for line in re.split(r"[\n.!?]+", r.get('body', '') or ''):
            if re.search(r'(?i)\b(?:if|maybe|might|could|hypothetically)\b', line):
                continue
            for name, pid in names:
                pat = (r'(?i)(?<!\w)' + re.escape(name) + r'(?!\w)\s+'
                       r'(?:is\s+)?no\s+longer\s+'
                       r'(?:responsible\s+for|handling|in\s+charge\s+of|owns|handles|manages|leading)\s+'
                       r'(?:the\s+)?(?P<role>[\w\-/ &]{3,110})')
                m = re.search(pat, line)
                if m and terms(m.group('role')):
                    yield Responsibility(pid, m.group('role').strip(' .,:;-'),r['id'],
                                         r.get('at',''), _authority(r, people),r.get('type',''),r.get('client'))


def responsibility_answer(question: str, authorized_records: Iterable[dict],
                          people: Mapping[str, dict], requester_org: str | None,
                          client: str | None = None):
    """Return an answer only for a clear, evidence-supported 'who owns X' request.

    Records must be prefiltered for visibility, time and forgetting by Engine.allowed.
    """
    if not re.search(r"(?i)\b(?:who|whom)\b", question):
        return None
    if not re.search(r"(?i)\b(?:responsible|owns?|handling|handles?|leads?|manages?|accountable|in charge)\b", question):
        return None
    rows = list(authorized_records)
    scoped = [r for r in rows if client is None or r.get("client") == client]
    # Remove wh-question boilerplate and explicit client names before matching.
    content = terms(question)
    if client:
        content -= terms(client)
    for p in people.values():
        if p.get("org") == requester_org:
            content -= terms(p.get("name", ""))
    if not content:
        return None
    candidates=[]
    for fact in extract_responsibilities(scoped, people, requester_org):
        fterms=terms(fact.role)
        if not fterms:
            continue
        target = expanded_terms(" ".join(content))
        related = expanded_terms(fact.role)
        overlap = len(target & related) / max(1, len(content))
        # Require at least one meaningful shared word, or a very strong overlap
        # via a domain-level synonym group.
        if overlap < 0.55:
            continue
        candidates.append((overlap, fact))
    if not candidates:
        return None
    # A later, equally authoritative explicit revocation invalidates an earlier
    # claim without inventing a replacement owner.
    retractions=list(extract_retractions(scoped, people, requester_org))
    live=[]
    for similarity,fact in candidates:
        revoked=any(
            neg.subject_id==fact.subject_id and neg.at >= fact.at
            and neg.authority >= fact.authority
            and (len(expanded_terms(neg.role)&expanded_terms(fact.role)) /
                 max(1,len(terms(fact.role)))) >= 0.55
            for neg in retractions
        )
        if not revoked:
            live.append((similarity,fact))
    candidates=live
    if not candidates:
        return None
    # Topic similarity is primary for selecting WHAT fact is relevant; authority
    # then timestamp resolve WHO wins within that topic.
    best_sim=max(c[0] for c in candidates)
    close=[fact for sim, fact in candidates if sim >= best_sim - 0.12]
    close.sort(key=lambda f:(f.authority, f.at), reverse=True)
    selected=close[0]
    # If equal-strength conflicting evidence is truly simultaneous, abstain.
    if len(close)>1 and close[1].subject_id!=selected.subject_id and (close[1].authority,close[1].at)==(selected.authority,selected.at):
        return None
    name=people.get(selected.subject_id,{}).get("name",selected.subject_id)
    return {
        "text": f"{name} ({selected.subject_id}) is responsible for {selected.role}.",
        "sources": [selected.record_id],
        "matched": [{"phrase": selected.role, "id": selected.subject_id, "sources": [selected.record_id]}]
    }
