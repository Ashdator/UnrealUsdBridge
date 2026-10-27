import copy,json,os,subprocess,sys,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from test_core import fixture_directory
import test_usd
import run_headless as h


class HeadlessTests(unittest.TestCase):
    def job(self,root):
        source=root/'source paths & Unicode';source.mkdir();run=root/'run';run.mkdir()
        for name in ('Project.uproject','UnrealEditor-Cmd.exe','SavedMap.umap','UnrealUsdBridge.uplugin'):(source/name).touch()
        binaries=source/'Binaries/Win64';binaries.mkdir(parents=True);(binaries/'UnrealEditor-UnrealUsdBridge.dll').touch()
        job=dict(schema_version=1,job_id='a'*32,editor_pid=12345,run=str(run),project=str(source/'Project.uproject'),
                 engine=str(source/'UnrealEditor-Cmd.exe'),plugin=str(source/'UnrealUsdBridge.uplugin'),
                 source_file=str(source/'SavedMap.umap'),package='/Game/Maps/SavedMap',kind='map',
                 isaac=os.environ['UNREAL_USD_BRIDGE_ISAAC'],visibility_snapshot={'actors':[],'components':[]},
                 options=dict(include_decals=False,export_cameras=False,export_lights=False,export_skeletal_meshes=True,
                              exclude_hidden=True,optimize=True,threshold=500000,target=250000,lod=0,max_error_cm=.5))
        path=run/'headless-job.json';h.write_json(path,job);return path,job,run

    def test_options_and_paths_are_argument_data_without_shell(self):
        with fixture_directory() as root:
            path,job,run=self.job(root);h.validate_job(job,path)
            command=h.extraction_command(job,run)
            self.assertEqual(command[1],job['project'])
            for flag in ('-NullRHI','-NoShaderCompile','-AsyncStaticMeshCompilationMaxConcurrency=1','-BridgeNoDecals',
                         '-BridgeNoCameras','-BridgeNoLights','-BridgeExportSkeletalMeshes','-BridgeExcludeHidden','-BridgeOptimize',
                         '-BridgeLOD=0','-BridgeMaxError=0.5'):
                self.assertIn(flag,command)
            self.assertNotIn('-BridgeCurrentWorld',command);self.assertNotIn('-BridgeSelected',command)
            job['options']['optimize']=False
            self.assertNotIn('-BridgeOptimize',h.extraction_command(job,run))
            self.assertIn('-BridgeTarget=250000',h.extraction_command(job,run))

    def test_invalid_paths_never_signal_ready_or_launch_workers(self):
        with fixture_directory() as root:
            path,job,run=self.job(root);job['engine']='X:/missing/UnrealEditor-Cmd.exe';h.write_json(path,job)
            calls=[];code=h.run(path,worker=lambda *a,**k:calls.append(a),editor_factory=lambda _:self.fail('Editor must not be touched'),output=lambda *a,**k:None)
            self.assertEqual(code,1);self.assertFalse(calls);self.assertFalse((run/'headless-ready.json').exists())

    def test_close_cancellation_or_veto_never_starts_second_unreal(self):
        with fixture_directory() as root:
            path,job,run=self.job(root)
            class Editor:
                def exited(self):return False
                def close(self):pass
            calls=[];code=h.run(path,worker=lambda *a,**k:calls.append(a),editor_factory=lambda _:Editor(),handoff_timeout=.05,output=lambda *a,**k:None)
            self.assertEqual(code,1);self.assertFalse(calls)
            self.assertEqual(json.loads((run/'headless-status.json').read_text())['state'],'failed')

    def test_cancel_while_waiting_does_not_close_editor(self):
        with fixture_directory() as root:
            path,job,run=self.job(root);(run/'cancel.request').touch()
            class Editor:
                def exited(self):self.fail('Cancelled handoff must not start waiting on exit')
                def close(self):pass
            calls=[];code=h.run(path,worker=lambda *a,**k:calls.append(a),editor_factory=lambda _:Editor(),output=lambda *a,**k:None)
            self.assertEqual(code,2);self.assertFalse(calls)

    def test_complete_handoff_real_usd_worker_and_progress(self):
        with fixture_directory() as root:
            path,job,run=self.job(root);exited=threading.Event();calls=[];messages=[]
            class Editor:
                def exited(self):return exited.is_set()
                def close(self):pass
            def approve():
                while not (run/'headless-ready.json').is_file():time.sleep(.01)
                (run/'headless-close-approved').write_text(job['job_id']);exited.set()
            thread=threading.Thread(target=approve);thread.start()
            def worker(command,log,cancel,progress,**kwargs):
                self.assertTrue(exited.is_set(),'Worker started before editor exit')
                calls.append(command)
                if len(calls)==1:
                    test_usd.UsdIntegrationTests().fixture(run)
                    progress('BRIDGE_COMPLETE: extraction complete');return 0
                return h.run_worker(command,log,cancel,progress,**kwargs)
            code=h.run(path,worker=worker,editor_factory=lambda _:Editor(),output=lambda message,**_:messages.append(message))
            thread.join(2);self.assertEqual(code,0);self.assertEqual(len(calls),2)
            state=json.loads((run/'headless-status.json').read_text());self.assertEqual(state['state'],'complete');self.assertEqual(state['fraction'],1)
            report=json.loads((run/'conversion-report.json').read_text());self.assertTrue(report['headless']['editor_closed_before_extraction'])
            self.assertEqual(report['counts']['cameras'],0);self.assertEqual(report['counts']['lights'],0)
            self.assertTrue(any('Original editor has exited' in m for m in messages))
            self.assertTrue(any('Mesh optimization: ON' in m for m in messages))

    def test_silent_unreal_exit_without_manifest_is_failure(self):
        with fixture_directory() as root:
            path,job,run=self.job(root);(run/'headless-close-approved').write_text(job['job_id'])
            class Editor:
                def exited(self):return True
                def close(self):pass
            calls=[]
            def worker(*a,**k):calls.append(a);return 0
            self.assertEqual(h.run(path,worker=worker,editor_factory=lambda _:Editor(),output=lambda *a,**k:None),1)
            self.assertEqual(len(calls),1);self.assertFalse((run/'Scene.usdc').exists())

    def test_actual_windows_process_handle_waits_for_exit(self):
        # A tiny owned Python process tests Windows PID/handle behavior, not an
        # Unreal editor session or its shutdown UI.
        process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.7)'],creationflags=subprocess.CREATE_NO_WINDOW)
        editor=h.EditorProcess(process.pid)
        try:
            self.assertFalse(editor.exited());process.wait(timeout=5);self.assertTrue(editor.exited())
        finally:
            editor.close()
            if process.poll() is None:process.terminate();process.wait()

    def test_existing_output_is_not_overwritten(self):
        with fixture_directory() as root:
            path,job,run=self.job(root);(run/'Scene.usdc').write_text('keep')
            with self.assertRaisesRegex(ValueError,'already contains'):h.validate_job(job,path)
            self.assertEqual((run/'Scene.usdc').read_text(),'keep')
