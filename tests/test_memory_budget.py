import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import tomllib
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.memory_budget import (
    GIB, LowMemory, WorkerCancelled, WorkerLimit, available_budget, run_worker,
    stop_owned, system_memory)
from test_core import fixture_directory
from ash_unreal_usd601_decals.progress import fraction


def snapshot(available, commit=40, total=32):
    from types import SimpleNamespace
    return SimpleNamespace(total=total*GIB, available=int(available*GIB), available_commit=commit*GIB)


class BudgetTests(unittest.TestCase):
    def test_existing_applications_and_commit_limit_reduce_budget(self):
        self.assertAlmostEqual(available_budget(snapshot(18))[0]/GIB, 16)
        self.assertAlmostEqual(available_budget(snapshot(18, commit=9))[0]/GIB, 7)
        self.assertEqual(available_budget(snapshot(1))[0], 0)
        self.assertEqual(available_budget(snapshot(18))[1]/GIB, 2)
        # A larger machine does not silently enlarge the live reserve.
        self.assertEqual(available_budget(snapshot(18,total=128))[1]/GIB, 2)

    @unittest.skipUnless(os.name == 'nt', 'Windows memory monitoring')
    def test_completed_worker_is_not_stopped_for_a_later_reserve_drop(self):
        process=MagicMock(returncode=1)
        process.poll.side_effect=[None,1,1]
        cancel=MagicMock()
        cancel.is_set.return_value=False;cancel.wait.return_value=False
        with fixture_directory() as folder:
            with patch('ash_unreal_usd601_decals.memory_budget.system_memory',
                       side_effect=[snapshot(18),snapshot(1)]) as memory:
                with patch('ash_unreal_usd601_decals.memory_budget.subprocess.Popen',return_value=process):
                    with patch('ash_unreal_usd601_decals.memory_budget.WorkerLimit'):
                        code=run_worker(['unused'],Path(folder)/'worker.log',cancel,lambda _:None)
            self.assertEqual(code,1)
            self.assertEqual(memory.call_count,1)
            process.terminate.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Objects')
    def test_os_limit_blocks_large_allocation_in_owned_child(self):
        # The child attempts 512 MiB under a 128 MiB cap. The parent stays alive.
        process = subprocess.Popen([sys.executable, '-B', '-c',
            "import sys; sys.stdin.readline(); "
            "\ntry: x=bytearray(512*1024**2); print('UNEXPECTED',flush=True)"
            "\nexcept MemoryError: print('BLOCKED',flush=True)"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        limit = None
        try:
            limit = WorkerLimit(process, 128*1024**2)
            output, _ = process.communicate('\n', timeout=20)
            self.assertEqual(process.returncode, 0, output)
            self.assertIn('BLOCKED', output)
            self.assertNotIn('UNEXPECTED', output)
        finally:
            stop_owned(process)
            if limit: limit.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows memory monitoring')
    def test_live_memory_loss_stops_worker_and_keeps_diagnostic(self):
        launched = []
        with fixture_directory() as folder:
            path = Path(folder)/'worker.log'
            with patch('ash_unreal_usd601_decals.memory_budget.system_memory',
                       side_effect=[snapshot(18), snapshot(1)]):
                with self.assertRaisesRegex(LowMemory, 'physical RAM fell below'):
                    run_worker([sys.executable, '-B', '-c', 'import time; time.sleep(20)'],
                               path, threading.Event(), lambda _:None,
                               process_changed=lambda p: launched.append(p) if p else None)
            self.assertIsNotNone(launched[0].poll())
            record = json.loads(path.with_suffix('.memory.json').read_text())
            self.assertEqual(record['stop_reason'], 'system reserve reached')
            self.assertEqual(record['reserve_gib'], 2)
            self.assertIsNone(record['budget_gib'])
            self.assertEqual(record['requested_limit_gib'],0)
            self.assertEqual(record['policy'],'live_reserve')

    @unittest.skipUnless(os.name == 'nt', 'Windows memory monitoring')
    def test_commit_shortage_is_reported_even_with_free_physical_ram(self):
        with fixture_directory() as folder:
            path=Path(folder)/'worker.log'
            with patch('ash_unreal_usd601_decals.memory_budget.system_memory',
                       side_effect=[snapshot(18),snapshot(18,commit=1)]):
                with self.assertRaisesRegex(LowMemory,'Windows allocation headroom fell below'):
                    run_worker([sys.executable,'-B','-c','import time; time.sleep(20)'],
                               path,threading.Event(),lambda _:None)
            self.assertEqual(json.loads(path.with_suffix('.memory.json').read_text())['stop_reason'],
                             'system reserve reached')

    @unittest.skipUnless(os.name == 'nt', 'Windows memory monitoring')
    def test_freed_ram_can_be_used_and_blueprint_exit_is_not_a_memory_error(self):
        from test_extraction_status import ExtractionStatusTests
        from ash_unreal_usd601_decals.extraction_status import character_only_failure
        with fixture_directory() as folder:
            path,manifest,_,text=ExtractionStatusTests().fixture(folder)
            script=("import sys,time; x=bytearray(256*1024**2); "
                    f"print({text!r},flush=True); time.sleep(1.2); sys.exit(1)")
            calls=iter([snapshot(2.1)])
            def changing_memory():return next(calls,snapshot(18))
            with patch('ash_unreal_usd601_decals.memory_budget.system_memory',side_effect=changing_memory):
                code=run_worker([sys.executable,'-B','-c',script],path,threading.Event(),lambda _:None,
                                minimum_gib=.05)
            self.assertEqual(code,1)
            record=json.loads(path.with_suffix('.memory.json').read_text())
            self.assertIsNone(record['budget_gib'])
            self.assertIsNone(record['stop_reason'])
            self.assertGreater(record['peak_private_gib'],record['initial_headroom_gib'])
            self.assertIn('Environment extraction completed',
                          character_only_failure(code,path,manifest,'/Game/Environment'))

    @unittest.skipUnless(os.name == 'nt', 'Windows memory monitoring')
    def test_explicit_allocation_failure_still_reports_low_memory(self):
        with fixture_directory() as folder:
            path=Path(folder)/'worker.log'
            with patch('ash_unreal_usd601_decals.memory_budget.system_memory',return_value=snapshot(18)):
                with self.assertRaisesRegex(LowMemory,'memory allocation failed'):
                    run_worker([sys.executable,'-B','-c',
                                "import sys; print('LLVM ERROR: out of memory',flush=True); sys.exit(1)"],
                               path,threading.Event(),lambda _:None)
            self.assertEqual(json.loads(path.with_suffix('.memory.json').read_text())['stop_reason'],
                             'worker allocation failed')

    @unittest.skipUnless(os.name == 'nt', 'Windows memory monitoring')
    def test_windows_allocation_failure_status_still_reports_low_memory(self):
        with fixture_directory() as folder:
            path=Path(folder)/'worker.log'
            with patch('ash_unreal_usd601_decals.memory_budget.system_memory',return_value=snapshot(18)):
                with self.assertRaisesRegex(LowMemory,'memory allocation failed'):
                    run_worker([sys.executable,'-B','-c',
                                'import ctypes; ctypes.windll.kernel32.ExitProcess(0xc0000017)'],
                               path,threading.Event(),lambda _:None)

    @unittest.skipUnless(os.name == 'nt', 'Windows memory monitoring')
    def test_cancel_while_waiting_does_not_start_worker(self):
        cancel = threading.Event(); cancel.set()
        with fixture_directory() as folder:
            with patch('ash_unreal_usd601_decals.memory_budget.system_memory', return_value=snapshot(2)):
                with patch('subprocess.Popen') as launch:
                    with self.assertRaises(WorkerCancelled):
                        run_worker(['unused'], Path(folder)/'log', cancel, lambda _:None)
                    launch.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows memory monitoring')
    def test_actual_memory_snapshot_is_valid(self):
        value = system_memory()
        self.assertGreater(value.total, 0)
        self.assertLessEqual(value.available, value.total)
        self.assertGreaterEqual(value.available_commit, 0)



    def test_progress_wait_and_failure_never_report_complete(self):
        value=0
        for message in ['Reading input files','Preparing a temporary project',
                        'Unreal is reading the scene','Waiting for RAM: 3 GiB',
                        'Building USD in a separate process','Translating material 5/10',
                        'Writing geometry 2/3','Writing material 1/10',
                        'Placing object 101/400','Writing foliage: Grass',
                        'BRIDGE_USD_COMPLETE Scene.usda','Preparing shaders 1–8 of 20',
                        'Shaders ready 8/20','Preparing shaders 9–12 of 20',
                        'Shader worker failed']:
            updated=fraction(message,value)
            self.assertGreaterEqual(updated,value)
            self.assertLess(updated,1)
            value=updated
        self.assertEqual(fraction('Waiting for RAM',value),value)
        self.assertEqual(fraction('Conversion complete',value),1)


if __name__ == '__main__': unittest.main()
