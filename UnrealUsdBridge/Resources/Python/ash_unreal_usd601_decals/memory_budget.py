"""Monitor live system headroom for bridge-owned workers, without a fixed cap."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time
import math

GIB = 1024 ** 3


class LowMemory(RuntimeError):
    pass


class WorkerCancelled(RuntimeError):
    pass


class SystemMemory(ctypes.Structure):
    _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [
        (name, ctypes.c_ulonglong) for name in (
            'total', 'available', 'total_commit', 'available_commit',
            'total_virtual', 'available_virtual', 'extended')]


class ProcessMemory(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            'peak_ws', 'ws', 'peak_paged', 'paged', 'peak_nonpaged',
            'nonpaged', 'pagefile', 'peak_pagefile', 'private')]


def system_memory():
    if os.name != 'nt':
        raise RuntimeError('This Windows bridge requires Windows memory monitoring')
    value = SystemMemory(); value.length = ctypes.sizeof(value)
    api = ctypes.WinDLL('kernel32', use_last_error=True).GlobalMemoryStatusEx
    api.argtypes = [ctypes.POINTER(SystemMemory)]
    if not api(ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def available_budget(memory, reserve_gib=2.0):
    # This snapshot is only a launch-readiness check, not a worker cap.
    # Later allocations may use RAM freed by other applications. A live check
    # keeps the same small reserve for physical RAM and system commit.
    if not math.isfinite(reserve_gib) or reserve_gib <= 0:
        raise ValueError('The live memory reserve must be a finite positive number')
    reserve = int(reserve_gib * GIB)
    budget = max(0, min(memory.available, memory.available_commit) - reserve)
    return budget, reserve


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        'read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
               ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
               ('max_ws', ctypes.c_size_t), ('processes', wintypes.DWORD),
               ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
               ('scheduling', wintypes.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters),
               ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
               ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]


class WorkerLimit:
    """Own the worker tree for cleanup; an explicit test cap is optional."""
    def __init__(self, process, budget=None):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        value = ExtendedLimits()
        value.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE, without a memory limit
        if budget is not None:
            value.basic.flags |= 0x200  # JOB_MEMORY, only for explicit helper caps
            value.job_memory = budget
        try:
            if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(value), ctypes.sizeof(value)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def stop_owned(process):
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()


def run_worker(command, log, cancel_event, progress, env=None, minimum_gib=1.0,
               reserve_gib=2.0, max_gib=0.0, process_changed=lambda _: None):
    """Wait for launch headroom and stop an owned worker if the live reserve erodes.

    Conversion jobs leave max_gib at zero: no fixed cap is installed. Explicit
    caps remain available to isolated validation helpers. Monitoring is not an
    assertion that Windows never pages memory or that every allocation succeeds.
    The job contains only this newly launched process and its descendants.
    """
    log = Path(log)
    if not math.isfinite(max_gib) or max_gib<0:
        raise ValueError('RAM limit must be a finite nonnegative number; 0 means no fixed cap')
    if max_gib and max_gib<minimum_gib:
        raise ValueError(f'This worker needs a RAM limit of at least {minimum_gib:g} GiB; choose a larger limit or no fixed cap')
    notice = 0
    while True:
        memory = system_memory(); headroom, reserve = available_budget(memory, reserve_gib)
        if headroom >= minimum_gib * GIB: break
        if time.monotonic() >= notice:
            progress(f'Waiting for RAM: {memory.available/GIB:.1f} GiB physical RAM and '
                     f'{memory.available_commit/GIB:.1f} GiB Windows allocation headroom available; '
                     f'{reserve/GIB:.1f} GiB reserve plus {minimum_gib:.1f} GiB startup headroom needed. Cancel is available.')
            notice = time.monotonic() + 10
        if cancel_event.wait(.3): raise WorkerCancelled('Conversion cancelled while waiting for RAM')
    if cancel_event.is_set(): raise WorkerCancelled('Conversion cancelled')
    budget = int(max_gib*GIB) if max_gib else None
    progress((f'Worker RAM cap {budget/GIB:.1f} GiB; ' if budget is not None else 'No fixed worker RAM cap; ')+
             f'keeping a live reserve of {reserve/GIB:.1f} GiB physical RAM and Windows allocation headroom')
    started = time.monotonic(); peak_private = peak_ws = 0; reason = None
    process = limit = None
    read = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    read.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
    try:
        with log.open('w', encoding='utf-8') as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, env=env,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            process_changed(process)
            limit = WorkerLimit(process, budget)
            with log.open('r', encoding='utf-8', errors='replace') as reader:
                while process.poll() is None:
                    if cancel_event.wait(.3):
                        reason = 'cancelled'; raise WorkerCancelled('Conversion cancelled')
                    if process.poll() is not None:
                        break  # Do not diagnose a reserve drop after the worker exited.
                    used = ProcessMemory(); used.cb = ctypes.sizeof(used)
                    if read(int(process._handle), ctypes.byref(used), used.cb):
                        peak_private = max(peak_private, used.private)
                        peak_ws = max(peak_ws, used.peak_ws)
                    current = system_memory()
                    if min(current.available, current.available_commit) < reserve:
                        reason = 'system reserve reached'
                        scarce = 'physical RAM' if current.available < reserve else 'Windows allocation headroom'
                        raise LowMemory(f'Conversion stopped because available {scarce} fell below the '
                                        f'{reserve/GIB:.1f} GiB live reserve '
                                        f'({current.available/GIB:.1f} GiB physical RAM, '
                                        f'{current.available_commit/GIB:.1f} GiB allocation headroom available). '
                                        f'Assets and logs remain in {log.parent}')
                    lines = reader.readlines()
                    if lines: progress(lines[-1].strip())
        code = process.returncode
        memory_error = False
        if code:
            with log.open('rb') as reader:
                reader.seek(max(0, log.stat().st_size-65536))
                tail = reader.read().decode('utf-8',errors='replace').lower()
            memory_error = any(text in tail for text in ('out of memory','memoryerror','std::bad_alloc'))
        # High usage by itself cannot diagnose a failure. Unreal can finish the
        # export and return 1 for unrelated Blueprint errors near any prior cap.
        # Let the caller validate those completed exports. Report low memory only
        # when the worker supplies an allocation failure or Windows memory status.
        if code and (memory_error or (code & 0xffffffff) in (0xc0000017, 0xc000012d)):
            reason = 'worker allocation failed'
            raise LowMemory(f'A worker memory allocation failed. The authored assets are retained; see {log}')
        return code
    finally:
        if process: stop_owned(process)
        if limit: limit.close()
        process_changed(None)
        log.with_suffix('.memory.json').write_text(json.dumps({
            'policy': 'live_reserve' if budget is None else 'explicit_cap_and_live_reserve',
            'budget_gib': budget/GIB if budget is not None else None,
            'initial_headroom_gib': headroom/GIB, 'reserve_gib': reserve/GIB,
            'requested_limit_gib':max_gib,
            'peak_private_gib': peak_private/GIB, 'peak_working_set_gib': peak_ws/GIB,
            'seconds': time.monotonic()-started,
            'exit_code': process.returncode if process else None, 'stop_reason': reason
        }, indent=2), encoding='utf-8')
