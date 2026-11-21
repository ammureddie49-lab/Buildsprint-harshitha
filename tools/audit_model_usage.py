#!/usr/bin/env python3
"""Read saved public-run answers/briefs and evaluate reported output usage.

This does NOT include model calls done by ingest, which the organizer runner
logs only as status (not ingested stdout); track those in separate CLI output.
It cannot replace server-side metering or an actual model-on public score.
"""
import argparse,json,pathlib,sys

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',required=True)
    a=parser.parse_args()
    root=pathlib.Path(a.run)
    if not root.is_dir():
        print(f'No run folder: {root}',file=sys.stderr);return 2
    report={'asks':0,'briefs':0,'reported_input_tokens':0,'reported_output_tokens':0,
            'reported_cost_usd':0.0,'question_over_budget':[],'brief_over_budget':[],
            'missing_usage':[], 'limitations':['Ingest calls are excluded: runner discards ingest stdout.',
                'Model-on token counts require a real-key run; zero counts alone prove nothing.']}
    for filename in sorted(root.glob('day-*/*.json')):
        if filename.name.startswith('ask-'):
            family='ask'; items=[json.loads(filename.read_text(encoding='utf-8'))]
        elif filename.name.startswith('brief-'):
            family='brief'; obj=json.loads(filename.read_text(encoding='utf-8'))
            items=obj if isinstance(obj,list) else [obj]
        else:continue
        for item in items:
            report[family+'s']+=1
            usage=item.get('usage')
            if not isinstance(usage,dict):
                report['missing_usage'].append(str(filename));continue
            i,o=int(usage.get('input_tokens') or 0),int(usage.get('output_tokens') or 0)
            report['reported_input_tokens']+=i
            report['reported_output_tokens']+=o
            report['reported_cost_usd']+=float(usage.get('cost_usd') or 0)
            if i>(4000 if family=='ask' else 8000):report['question_over_budget' if family=='ask' else 'brief_over_budget'].append(str(filename))
    report['reported_cost_usd']=round(report['reported_cost_usd'],8)
    report['status']='FAIL' if report['question_over_budget'] or report['brief_over_budget'] or report['missing_usage'] else 'PASS'
    print(json.dumps(report,indent=2))
    return 1 if report['status']=='FAIL' else 0

if __name__=='__main__':raise SystemExit(main())
