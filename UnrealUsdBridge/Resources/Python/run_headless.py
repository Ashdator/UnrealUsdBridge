"""Visible console supervisor: wait for saved editor shutdown, extract, author USD."""
import argparse
import ctypes
from ctypes import wintypes
import datetime
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import traceback

from ash_unreal_usd601_decals.memory_budget import run_worker, WorkerCancelled
from ash_unreal_usd601_decals.progress import fraction
from run_conversion import find_runtime


def write_json(path, value):
    path=Path(path);temporary=path.with_name(path.name+'.writing')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8')
    for attempt in range(20):
        try:
            temporary.replace(path);return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.05)


def validate_job(job,job_file):
    if job.get('schema_version')!=1:raise ValueError('Unsupported headless job schema')
    token=job.get('job_id','')
    if len(token)!=32 or any(c not in '0123456789abcdefABCDEF' for c in token):raise ValueError('Invalid job identity')
    if type(job.get('editor_pid')) is not int or job['editor_pid']<=0:raise ValueError('Missing original editor PID')
    run=Path(job['run']).resolve()
    if run!=Path(job_file).resolve().parent:raise ValueError('Headless output must be the job folder')
    for key in ('project','engine','plugin','source_file'):
        if not Path(job[key]).is_file():raise ValueError(f'Missing {key}: {job[key]}')
    if Path(job['project']).suffix.lower()!='.uproject':raise ValueError('Invalid Unreal project')
    if Path(job['engine']).name.lower()!='unrealeditor-cmd.exe':raise ValueError('Invalid Unreal commandlet executable')
    if job.get('kind') not in ('map','asset'):raise ValueError('Headless mode requires a saved map or static mesh asset')
    expected='.umap' if job['kind']=='map' else '.uasset'
    if Path(job['source_file']).suffix.lower()!=expected:raise ValueError('Source package type does not match export scope')
    if not job.get('package','').startswith('/') or '..' in job['package'].split('/'):raise ValueError('Invalid source package')
    if not (Path(job['plugin']).parent/'Binaries/Win64/UnrealEditor-UnrealUsdBridge.dll').is_file():raise ValueError('Compiled extraction plugin is missing')
    python,usd=find_runtime(job['isaac'])
    options=job['options']
    for key in ('include_decals','export_cameras','export_lights','export_skeletal_meshes','exclude_hidden','optimize'):
        if type(options.get(key)) is not bool:raise ValueError('Invalid option: '+key)
    for key in ('threshold','target','lod'):
        if type(options.get(key)) is not int:raise ValueError('Invalid integer option: '+key)
    if not 4<=options['target']<=options['threshold'] or options['threshold']<100 or not 0<=options['lod']<=8:
        raise ValueError('Invalid mesh optimization limits')
    if not math.isfinite(options['max_error_cm']) or options['max_error_cm']<=0:raise ValueError('Invalid simplification error')
    if (run/'Scene.usdc').exists() or (run/'manifest.json').exists():raise ValueError('Output already contains an extraction or scene; choose a fresh conversion')
    return run,python,usd


class EditorProcess:
    """Hold the original process handle; never kill or signal that editor."""
    def __init__(self,pid):
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.api.OpenProcess.restype=wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        self.api.WaitForSingleObject.restype=wintypes.DWORD
        self.api.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.api.OpenProcess(0x00100000,False,pid) # SYNCHRONIZE only
        if not self.handle:raise RuntimeError('Cannot monitor original editor. It will not be closed automatically.')
    def exited(self):
        state=self.api.WaitForSingleObject(self.handle,0)
        if state==0:return True
        if state==258:return False
        raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.handle:self.api.CloseHandle(self.handle);self.handle=None


def wait_for_editor(job,run,cancel,progress,editor,timeout=300):
    # Publish readiness only after the original PID has been opened. C++ writes
    # approval immediately before requesting the normal editor Close command.
    write_json(run/'headless-ready.json',dict(job_id=job['job_id'],state='ready',runner_pid=os.getpid()))
    start=time.monotonic();notice=0
    while True:
        if cancel.is_set() or (run/'cancel.request').exists():raise WorkerCancelled('Headless startup cancelled')
        approved=False
        approval=run/'headless-close-approved'
        if approval.is_file():approved=approval.read_text(encoding='utf-8-sig').strip()==job['job_id']
        if approved and editor.exited():
            progress('Original editor has exited. Starting headless extraction.');return
        if time.monotonic()-start>=timeout:raise RuntimeError('Editor did not finish closing; conversion was not started. Save/close may have been cancelled.')
        if time.monotonic()>=notice:
            progress('Waiting for the saved Unreal editor to close; no second Unreal process has started.')
            notice=time.monotonic()+5
        cancel.wait(.2)


def extraction_command(job,run):
    o=job['options']
    command=[job['engine'],job['project'],'-run=UnrealUsdExtract',f"-PLUGIN={job['plugin']}",'-EnablePlugins=UnrealUsdBridge',
        f"-{'BridgeMap' if job['kind']=='map' else 'BridgeAsset'}={job['package']}",f'-BridgeOut={run}',
        '-unattended','-nop4','-nosplash','-nosound','-NullRHI','-NoShaderCompile','-stdout','-FullStdOutLogOutput',
        f'-abslog={run}/unreal-engine.log','-AsyncStaticMeshCompilation=1','-AsyncStaticMeshCompilationMaxConcurrency=1']
    for key,flag,enabled in [('include_decals','BridgeNoDecals',False),('export_cameras','BridgeNoCameras',False),
                           ('export_lights','BridgeNoLights',False),('export_skeletal_meshes','BridgeExportSkeletalMeshes',True),
                           ('exclude_hidden','BridgeExcludeHidden',True),('optimize','BridgeOptimize',True)]:
        if o[key]==enabled:command.append('-'+flag)
    for key,flag in [('threshold','BridgeThreshold'),('target','BridgeTarget'),('lod','BridgeLOD'),('max_error_cm','BridgeMaxError')]:
        command.append(f'-{flag}={o[key]}')
    if o['exclude_hidden']:command.append(f'-BridgeHiddenSnapshot={run}/headless-visibility.json')
    return [str(x) for x in command]


def run(job_file,worker=run_worker,editor_factory=EditorProcess,handoff_timeout=300,output=print):
    job_file=Path(job_file).resolve();run=job_file.parent;cancel=threading.Event();finished=threading.Event()
    previous=.02;stage='validating';editor=None;started=time.monotonic()
    def status(message,state=None):
        nonlocal previous
        previous=fraction(message,previous)
        output(f'[{datetime.datetime.now().strftime("%H:%M:%S")}] {message}',flush=True)
        write_json(run/'headless-status.json',dict(state=state or stage,message=message,fraction=previous,seconds=time.monotonic()-started))
    def watch():
        while not finished.wait(.2):
            if (run/'cancel.request').exists():cancel.set();return
    try:
        job=json.loads(job_file.read_text(encoding='utf-8-sig'));run,python,usd=validate_job(job,job_file)
        write_json(run/'headless-visibility.json',job.get('visibility_snapshot',{'actors':[],'components':[]}))
        editor=editor_factory(job['editor_pid'])
        threading.Thread(target=watch,daemon=True).start()
        stage='waiting_for_editor'
        o=job['options']
        status(f"Mesh optimization: {'ON' if o['optimize'] else 'OFF'} | threshold {o['threshold']} triangles | target {o['target']} | preferred LOD {o['lod']} | maximum error {o['max_error_cm']} cm")
        status('Headless job validated. Saved project: '+job['project'])
        status('Export package: '+job['package']);status('Output: '+str(run))
        wait_for_editor(job,run,cancel,status,editor,timeout=handoff_timeout)
        editor.close();editor=None
        stage='extracting';status('Unreal extraction: reading saved assets without a viewport; percentage is unknown during loading.')
        code=worker(extraction_command(job,run),run/'unreal.log',cancel,lambda line:status('Unreal: '+line),minimum_gib=1.0)
        manifest=run/'manifest.json'
        if code or not manifest.is_file():
            from ash_unreal_usd601_decals.extraction_status import character_only_failure
            recovered=character_only_failure(code,run/'unreal.log',manifest,job['package']) if manifest.is_file() else None
            if not recovered:raise RuntimeError(f'Unreal extraction did not complete (exit {code}). See unreal.log and unreal-engine.log.')
            status(recovered)
        stage='authoring';status('Building USD in a separate process')
        o=job['options']
        command=[str(python),'-B','-u',str(Path(__file__).with_name('ash_unreal_usd601_decals')/'conversion_worker.py'),
                 str(manifest),str(usd),'1',str(int(o['include_decals'])),'0',str(int(o['export_cameras'])),str(int(o['export_lights']))]
        code=worker(command,run/'usd-conversion.log',cancel,lambda line:status('USD: '+line) if not line.startswith(('Writing','Translating','Placing','Grouping','Preparing','BRIDGE_USD_COMPLETE')) else status(line),minimum_gib=1.0)
        if code or not (run/'Scene.usdc').is_file():raise RuntimeError(f'USD conversion failed (exit {code}); see usd-conversion.log')
        report_path=run/'conversion-report.json';report=json.loads(report_path.read_text(encoding='utf-8'))
        report['headless']=dict(editor_closed_before_extraction=True,project=job['project'],package=job['package'],job_id=job['job_id'])
        write_json(report_path,report)
        counts=report.get('counts',{});total=counts.get('materials',0);translated=counts.get('translated_materials',0)
        status(f'Materials: {translated}/{total} translated; {total-translated} unsupported. See conversion-report.json.')
        status('Conversion complete','complete')
        status('Scene: '+str(run/'Scene.usdc'),'complete');return 0
    except (WorkerCancelled,KeyboardInterrupt):
        cancel.set();status('Headless conversion cancelled. Saved project and generated logs are retained.','cancelled');return 2
    except Exception as exc:
        (run/'headless-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        status(str(exc),'failed');return 1
    finally:
        finished.set()
        if editor:editor.close()


class Tee:
    def __init__(self,display,log):self.display,self.log=display,log
    def write(self,text):self.display.write(text);self.log.write(text);self.flush()
    def flush(self):self.display.flush();self.log.flush()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True,type=Path);parser.add_argument('--keep-open',action='store_true')
    args=parser.parse_args()
    # Console remains inspectable after completion/failure. No shell evaluates
    # the job's project paths or settings.
    with (args.job.parent/'headless-console.log').open('w',encoding='utf-8') as log:
        original=sys.stdout;sys.stdout=Tee(original,log)
        try:
            print('Unreal to Isaac USD 0.6.6 - headless conversion',flush=True)
            print('Ctrl+C cancels conversion workers. The original editor is closed normally, never force-killed.',flush=True)
            code=run(args.job)
            if args.keep_open:
                try:input('Press Enter to close this command window...')
                except (EOFError,KeyboardInterrupt):pass
            return code
        finally:sys.stdout=original


if __name__=='__main__':sys.exit(main())
