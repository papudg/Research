"""Capture the hardware and fixed solver configuration used for regeneration."""
from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import platform
import sys

import ortools

from icaa.paths import results_path


def total_memory_bytes():
    if platform.system() == 'Windows':
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ('length', ctypes.c_ulong), ('memory_load', ctypes.c_ulong),
                ('total_physical', ctypes.c_ulonglong), ('available_physical', ctypes.c_ulonglong),
                ('total_page_file', ctypes.c_ulonglong), ('available_page_file', ctypes.c_ulonglong),
                ('total_virtual', ctypes.c_ulonglong), ('available_virtual', ctypes.c_ulonglong),
                ('available_extended_virtual', ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return int(status.total_physical)
    return None


def cpu_model():
    if platform.system() == 'Windows':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                return winreg.QueryValueEx(key, 'ProcessorNameString')[0]
        except OSError:
            return None
    return platform.processor() or None


def capture():
    return {
        'platform': platform.platform(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'processor_identifier': os.environ.get('PROCESSOR_IDENTIFIER'),
        'cpu_model': cpu_model(),
        'logical_cpu_count': multiprocessing.cpu_count(),
        'physical_memory_bytes': total_memory_bytes(),
        'python_version': sys.version,
        'ortools_version': ortools.__version__,
        'solver_parameters': {
            'max_time_in_seconds': 30,
            'random_seed': 1,
            'num_search_workers': 1,
        },
        'pythonhashseed_required': '0',
    }


if __name__ == '__main__':
    result = capture()
    with open(results_path('results_environment.json'), 'w', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result, indent=2))
