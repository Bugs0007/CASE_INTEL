"""This process's resident memory (RSS), without a psutil dependency.

Used by the process_jobs worker to recycle itself before a long-lived
Python process creeps past what a t3.small can spare (see
core/management/commands/process_jobs.py). Linux reads /proc/self/status
(production); Windows asks the kernel (local development). Anything else
returns None and the worker simply doesn't recycle on memory.
"""

from __future__ import annotations

import sys


def current_rss_mb() -> float | None:
    """Current resident set size in MiB, or None if it can't be read."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", encoding="ascii") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024  # kB -> MiB
        except (OSError, ValueError, IndexError):
            return None
        return None
    if sys.platform == "win32":
        return _windows_working_set_mb()
    return None


def _windows_working_set_mb() -> float | None:
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(ProcessMemoryCounters)
        # Private library handles: setting argtypes on the shared
        # ctypes.windll function objects would change them for every other
        # caller in the process. Without explicit types the 64-bit
        # pseudo-handle is truncated to a C int and the call fails.
        kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD,
        ]
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return counters.WorkingSetSize / (1024 * 1024)
    except Exception:  # noqa: BLE001 -- best effort; None means "unknown"
        return None
