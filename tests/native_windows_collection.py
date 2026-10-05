"""Opt-in REAL Windows 11 / website-account acceptance; never imported by pytest.

Run from the repository with the browser extra installed and a manually signed-in
Chrome dedicated profile listening on loopback CDP. This sends fixture texts to the
chosen provider and consumes account quota. It does not automate login or mock a model.
"""
import argparse
import asyncio
import json
import sys
import platform
from pathlib import Path
from datetime import datetime, timezone
from filelock import FileLock


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--books',type=Path,required=True,help='Existing fixture directory containing long Markdown and EPUB books')
    p.add_argument('--provider',choices=['chatgpt','claude','deepseek'],required=True)
    p.add_argument('--approve-collection-disclosure',action='store_true')
    p.add_argument('--timeout',type=int,default=3600)
    args=p.parse_args()
    if sys.platform!='win32' or sys.getwindowsversion().build<22000:
        p.exit(2,'BLOCKED: this acceptance requires native Windows 11 (build 22000+). Linux/WSL is not native Windows evidence.\n')
    if not args.approve_collection_disclosure:
        p.exit(2,'Consent required: --approve-collection-disclosure authorizes this fixture collection and derived evidence to the selected website account in your dedicated browser profile.\n')
    from par.db import Store
    from par.collections import Collections
    from par.local_inference import LocalModelConfig
    store=Store(args.data_root)
    with FileLock(str(store.root/'runtime.lock'),timeout=0):
        store.recover()
        service=Collections(store)
        service.semantic.config(LocalModelConfig(backend='browser',browser_provider=args.provider,dedicated_browser_profile=True))
        old_ids={j['id'] for j in store.list('collection_jobs')}
        job=service.prepare(f'Read all the books in "{args.books.resolve()}". Build an idea graph across the collection, merge duplicate concepts where justified, and preserve citations.')
        if job['id'] in old_ids:
            p.exit(2,'Existing operation found: do not label cached results as a fresh live acceptance. Use a new data root for a new test, or inspect/resume the old operation in the app.\n')
        formats=[Path(m.get('path','')).suffix.lower() for m in job['manifest']]
        if formats.count('.md')<2 or formats.count('.epub')<2:
            p.exit(2,'Acceptance fixture requires at least two Markdown and two EPUB books; use create_collection_fixture.py. No source text was sent.\n')
        if job['status']=='awaiting_approval':service.approve(job['id'],args.provider)
        if job['status'] in {'paused','needs_attention'}:
            p.exit(2,'Prior job needs human inspection. Open the app for its failure/uncertainty state; this script will not blindly resend.\n')
        async def execute():
            try:await asyncio.wait_for(service.execute(job['id']),args.timeout)
            except TimeoutError:pass
        asyncio.run(execute())
        result=service.result(job['id'])
        runs=result['runs']
        live=[r for r in runs if r.get('worker_metadata',{}).get('semantic',{}).get('metadata',{}).get('transport')=='playwright-cdp' and r['worker_metadata']['semantic']['metadata'].get('provider')==args.provider]
        summary=result['summary']
        passed=(result['job']['status']=='completed' and summary['total_batches']>1 and summary['completed_passages']==summary['passages']
                and len(live)==len(runs) and bool(summary['cross_book_connections']) and summary['reused_identities']>0)
        report={'at':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),'python':sys.version,
                'provider':args.provider,'job_id':job['id'],'result':'PASS' if passed else 'FAIL_OR_BLOCKED',
                'scope':'Real website responses for supplied fixture books; this does not certify arbitrary libraries or semantic correctness.',
                'operation_status':result['job']['status'],'error':result['job']['error'],'summary':summary,
                'run_evidence':[{'id':r['id'],'status':r['status'],'error':r['error'],'acceptance':r.get('acceptance',{})} for r in runs]}
        target=store.root/'native-windows-acceptance.json';target.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'result':report['result'],'job_id':job['id'],'local_report':str(target)},indent=2))
        raise SystemExit(0 if passed else 1)

if __name__=='__main__':main()
