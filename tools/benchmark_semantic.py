#!/usr/bin/env python3
"""Independent synthetic retrieval benchmark: lexical vs local MiniLM.

No official answer keys are read. The neural mode loads a local SentenceTransformer
model (and may download weights on first use). Records are fictional and public.
"""
from __future__ import annotations
import argparse, json, pathlib, sys, time

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tracemind_semantic import HybridEvidenceRetriever, LocalEmbeddingModel

# Distinct fictional cases intentionally require some semantic paraphrasing.
CASES=[
    ("Are supplier payments stuck awaiting finance?", "pay", "alpha"),
    ("Who is responsible for bringing new vendors aboard?", "vendor", "alpha"),
    ("Has the customer extended the commercial agreement?", "contract", "alpha"),
    ("Which item covers identity verification before account access?", "login", "alpha"),
    ("Was quality assurance finished before the launch?", "qa", "alpha"),
    ("What is stopping shipment fulfillment?", "shipment", "beta"),
    ("Who manages the revised financial forecast?", "finance", "beta"),
    ("Did the data transfer checks finish?", "transfer", "beta"),
]
DOCUMENTS=[
    ("pay","Invoices require approval from the accounting department before disbursement.","alpha"),
    ("vendor","The partner induction and supplier setup process is led by Dev Kumar.","alpha"),
    ("contract","The account manager confirmed an extension to the service contract.","alpha"),
    ("login","The authentication team finished identity proofing for sign-in flows.","alpha"),
    ("qa","Regression test signoff was completed for the release candidate.","alpha"),
    ("shipment","Warehouse dispatch remains blocked due to missing courier tracking.","beta"),
    ("finance","The updated cash-flow projection is assigned to Mira Patel.","beta"),
    ("transfer","The migration reconciliation checks have passed.","beta"),
    ("distractor1","A team social event will take place in the office.","alpha"),
    ("distractor2","The newsletter draft is ready for approval.","beta"),
    ("distractor3","Purchase approvals are pending but only for corporate catering.","beta"),
    ("distractor4","A design review for the website was postponed.","alpha"),
]
RECORDS=[{'id':k,'body':body,'client':client,'type':'mail','at':'2026-11-03T09:00:00Z'} for k,body,client in DOCUMENTS]


def evaluate(embedder=None, topk=3):
    total=0;recall=0;rr=0.0;times=[];examples=[];neural_calls=0
    for question,gold,client in CASES:
        started=time.perf_counter()
        retriever=HybridEvidenceRetriever(RECORDS,embedder=embedder)
        hits=retriever.search(question,client=client,limit=topk)
        ids=[hit.record['id'] for hit in hits]
        times.append((time.perf_counter()-started)*1000)
        neural_calls+=bool(retriever.model_used)
        total+=1
        if gold in ids:
            recall+=1;rr+=1.0/(ids.index(gold)+1)
        examples.append({'query':question,'gold':gold,'retrieved':ids,'correct':gold in ids})
    return {'queries':total,'recall_at_3':round(recall/total,3),'mrr_at_3':round(rr/total,3),
            'avg_ms_per_query':round(sum(times)/total,1),'neural_queries':neural_calls,'examples':examples}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--lexical-only',action='store_true',help='Run without model or downloads')
    p.add_argument('--model',default='sentence-transformers/all-MiniLM-L6-v2')
    p.add_argument('--out',help='Write measured JSON report')
    args=p.parse_args()
    report={'benchmark':'synthetic paraphrase retrieval','dataset':'8 synthetic labelled queries, 12 fake workplace records',
            'lexical':evaluate(),'neural':None}
    if not args.lexical_only:
        try:
            embedder=LocalEmbeddingModel(args.model)
            # Load once before timing individual queries; model warm-up is reported separately.
            started=time.perf_counter();embedder.encode(['Warm-up sentence'])
            report['model_load_ms']=round((time.perf_counter()-started)*1000,1)
            report['neural']=evaluate(embedder)
            report['neural_model']=args.model
        except Exception as exc:
            report['neural_error']=f'{type(exc).__name__}: {exc}'
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    if not args.lexical_only and not report['neural']:
        print('Neural benchmark was NOT run; install the model/dependency before claiming a neural score.',file=sys.stderr)
        raise SystemExit(2)

if __name__=='__main__':main()
