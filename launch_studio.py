"""Start the optional TraceMind Studio bound to localhost only.

A precompiled frontend is included in the complete release. If Vite/node_modules
are unavailable, the FastAPI server serves the compiled UI at port 8765.
Use TRACEMIND_STUDIO_DEV=1 for a two-server React/Vite development session.
The four graded CLI commands do not depend on this launcher or on Node.js.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FRONT=ROOT/'studio-frontend'


def main():
    npm=shutil.which('npm') or shutil.which('npm.cmd')
    dev=os.environ.get('TRACEMIND_STUDIO_DEV','0')=='1'
    compiled=(FRONT/'dist/index.html').is_file()
    if dev and (npm is None or not (FRONT/'node_modules').exists()):
        print('Development mode requires Node.js and npm install in studio-frontend.',file=sys.stderr)
        return 1
    if not compiled and (npm is None or not (FRONT/'node_modules').exists()):
        print('Build the frontend with npm install && npm run build, or use the complete ZIP containing dist/.',file=sys.stderr)
        return 1
    procs=[]
    try:
        api=['-m','uvicorn','studio_api:app','--host','127.0.0.1','--port','8765']
        print('TraceMind Studio — localhost-only API http://127.0.0.1:8765',flush=True)
        procs.append(subprocess.Popen([sys.executable,*api],cwd=ROOT))
        if dev or not compiled:
            procs.append(subprocess.Popen([npm,'run','dev'],cwd=FRONT))
            url='http://127.0.0.1:5173'
        else:
            url='http://127.0.0.1:8765'
        time.sleep(2)
        if all(proc.poll() is None for proc in procs):
            print('Open '+url,flush=True)
            webbrowser.open(url)
        while all(proc.poll() is None for proc in procs):
            time.sleep(0.5)
        print('A Studio process stopped. See its stderr for details.',file=sys.stderr)
        return 1
    except KeyboardInterrupt:return 0
    finally:
        for proc in procs:
            if proc.poll() is None:proc.terminate()
        for proc in procs:
            try:proc.wait(timeout=4)
            except subprocess.TimeoutExpired:proc.kill()


if __name__=='__main__':raise SystemExit(main())
