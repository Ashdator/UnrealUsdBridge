"""Standalone USD worker supervisor; no Isaac application or renderer is opened."""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback

from ash_unreal_usd601_decals.memory_budget import run_worker, WorkerCancelled
from ash_unreal_usd601_decals.progress import fraction


def find_runtime(isaac):
    isaac = Path(isaac).resolve()
    python = isaac/'kit/python/python.exe'
    candidates = sorted((isaac/'extscache').glob(
        f'omni.usd.libs-*.wx64.r.cp{sys.version_info.major}{sys.version_info.minor}'))
    if not python.is_file() or not candidates:
        raise ValueError('Choose the Isaac Sim 6.0.1 installation folder containing kit/python and extscache/omni.usd.libs')
    return python, candidates[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--isaac', required=True, type=Path)
    parser.add_argument('--decals', choices=['0', '1'], default='1')
    parser.add_argument('--cameras', choices=['0', '1'], default='1')
    parser.add_argument('--lights', choices=['0', '1'], default='1')
    parser.add_argument('--console', action='store_true', help='Print status updates in this command window')
    args = parser.parse_args()
    run = args.manifest.resolve().parent
    cancel = threading.Event()
    finished = threading.Event()
    previous = .35

    def status(state, message, value=None):
        nonlocal previous
        if args.console:
            print(f'[{datetime.datetime.now().strftime("%H:%M:%S")}] {message}', flush=True)
        previous = fraction(message, previous) if value is None else value
        data = dict(state=state, message=message, fraction=previous, time=time.time())
        temporary = run/'editor-status.json.writing'
        temporary.write_text(json.dumps(data), encoding='utf-8')
        # Unreal can briefly hold the status file open while reading it.
        for attempt in range(20):
            try:
                temporary.replace(run/'editor-status.json')
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.05)

    def watch():
        while not finished.wait(.2):
            if (run/'cancel.request').exists():
                cancel.set()
                return

    try:
        python, usd = find_runtime(args.isaac)
        threading.Thread(target=watch, daemon=True).start()
        status('running', 'Building USD in a separate process')
        command = [str(python), '-B', '-u', str(Path(__file__).with_name('ash_unreal_usd601_decals')/'conversion_worker.py'),
                   str(args.manifest.resolve()), str(usd), '1', args.decals, '0', args.cameras, args.lights]
        code = run_worker(command, run/'usd-conversion.log', cancel,
                          lambda line: status('running', line), minimum_gib=1.0)
        if code:
            raise RuntimeError(f'USD conversion failed (exit {code}); see usd-conversion.log')
        if not (run/'Scene.usdc').is_file():
            raise RuntimeError('Worker exited without Scene.usdc')
        report=json.loads((run/'conversion-report.json').read_text(encoding='utf-8'))
        counts=report.get('counts',{});total=counts.get('materials',0);translated=counts.get('translated_materials',0)
        status('complete', f'Conversion complete: {translated}/{total} materials translated; {total-translated} unsupported. See conversion-report.json.', 1.0)
        return 0
    except WorkerCancelled:
        status('cancelled', 'Conversion cancelled; source assets unchanged')
        return 2
    except Exception as exc:
        (run/'editor-worker-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        status('failed', str(exc))
        return 1
    finally:
        finished.set()


if __name__ == '__main__':
    sys.exit(main())
