"""Windows のプロセス CPU 使用率サンプラ.

パフォーマンスモニターの ``Process\\% Processor Time`` と同じ定義で計算する。

    % Processor Time = (カーネル時間 + ユーザー時間 の増分) / 経過時間 * 100

論理コア数では割らないため、マルチスレッドのプロセスでは 100% を超え、
最大で ``論理コア数 * 100%`` まで到達する（perfmon と同じ挙動）。
タスクマネージャーの「CPU」列は同じ値を論理コア数で割ったものなので、
UI 側の「コア数で正規化」オプションで切り替えられる。

同名プロセスが複数起動している場合は、その名前のインスタンス全部の合計を返す
（perfmon で ``sldworks``, ``sldworks#1`` ... を足し合わせたものに相当）。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, field

IS_WINDOWS = sys.platform == "win32"

MAX_PATH = 260
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
PROCESS_QUERY_INFORMATION = 0x00000400
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_PARAMETER = 87
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# FILETIME は 100 ナノ秒単位
FILETIME_PER_SEC = 10_000_000.0


@dataclass
class ProcessSample:
    """1 プロセス名ぶんの 1 サンプル."""

    name: str
    percent: float = 0.0          # % Processor Time (コア数で割らない値)
    instances: int = 0            # 起動中のインスタンス数
    pids: list = field(default_factory=list)
    access_denied: int = 0        # 開けなかったインスタンス数 (要管理者権限)
    valid: bool = True            # 前回サンプルとの差分が取れたか


if IS_WINDOWS:

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * MAX_PATH),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi = ctypes.WinDLL("advapi32", use_last_error=True)

    _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.Process32FirstW.restype = wintypes.BOOL
    _k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.Process32NextW.restype = wintypes.BOOL
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    _k32.GetProcessTimes.restype = wintypes.BOOL
    _k32.GetCurrentProcess.argtypes = []
    _k32.GetCurrentProcess.restype = wintypes.HANDLE

    _advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    _advapi.OpenProcessToken.restype = wintypes.BOOL
    _advapi.LookupPrivilegeValueW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
    _advapi.LookupPrivilegeValueW.restype = wintypes.BOOL
    _advapi.AdjustTokenPrivileges.argtypes = [
        wintypes.HANDLE, wintypes.BOOL, ctypes.c_void_p,
        wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    _advapi.AdjustTokenPrivileges.restype = wintypes.BOOL


def _ft_to_int(ft) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def enable_debug_privilege() -> bool:
    """SeDebugPrivilege を有効化する（管理者で実行している場合のみ成功）.

    別ユーザー / サービスとして動いているプロセス（EdmServerV6.exe など）の
    CPU 時間を読むために必要になることがある。
    """
    if not IS_WINDOWS:
        return False

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", ctypes.c_long)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("PrivilegeCount", wintypes.DWORD),
                    ("Privileges", LUID_AND_ATTRIBUTES * 1)]

    TOKEN_ADJUST_PRIVILEGES = 0x0020
    TOKEN_QUERY = 0x0008
    SE_PRIVILEGE_ENABLED = 0x0002

    token = wintypes.HANDLE()
    if not _advapi.OpenProcessToken(
        _k32.GetCurrentProcess(),
        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
        ctypes.byref(token),
    ):
        return False
    try:
        luid = LUID()
        if not _advapi.LookupPrivilegeValueW(None, "SeDebugPrivilege", ctypes.byref(luid)):
            return False
        tp = TOKEN_PRIVILEGES()
        tp.PrivilegeCount = 1
        tp.Privileges[0].Luid = luid
        tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        ok = _advapi.AdjustTokenPrivileges(token, False, ctypes.byref(tp), 0, None, None)
        return bool(ok) and ctypes.get_last_error() == 0
    finally:
        _k32.CloseHandle(token)


def is_elevated() -> bool:
    """管理者権限で実行中かどうか."""
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def logical_processor_count() -> int:
    return os.cpu_count() or 1


def list_processes() -> list:
    """(pid, 実行ファイル名) の一覧を返す."""
    if not IS_WINDOWS:
        return []
    snapshot = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE or not snapshot:
        return []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        result = []
        ok = _k32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            result.append((int(entry.th32ProcessID), entry.szExeFile))
            ok = _k32.Process32NextW(snapshot, ctypes.byref(entry))
        return result
    finally:
        _k32.CloseHandle(snapshot)


class _Tracked:
    """OpenProcess したハンドルと前回の CPU 時間."""

    __slots__ = ("handle", "created", "cpu_100ns", "denied")

    def __init__(self, handle, created, cpu_100ns, denied=False):
        self.handle = handle
        self.created = created
        self.cpu_100ns = cpu_100ns
        self.denied = denied


class ProcessCpuSampler:
    """対象プロセス名の % Processor Time を周期的に計測する."""

    def __init__(self, names):
        self.set_names(names)
        self._tracked = {}       # pid -> _Tracked
        self._last_perf = None   # 前回サンプル時刻 (perf_counter)

    # ------------------------------------------------------------------
    def set_names(self, names):
        self.names = [n.strip() for n in names if n and n.strip()]
        self._lookup = {n.lower(): n for n in self.names}

    def close(self):
        for tracked in self._tracked.values():
            if tracked.handle:
                _k32.CloseHandle(tracked.handle)
        self._tracked.clear()
        self._last_perf = None

    def reset(self):
        """次のサンプルを「初回」扱いに戻す（一時停止からの復帰など）."""
        self._last_perf = None

    # ------------------------------------------------------------------
    def _open(self, pid):
        handle = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            if err == ERROR_INVALID_PARAMETER:
                # Windows 7 以前など。旧アクセス権でリトライ。
                handle = _k32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
                if handle:
                    return handle, False
                err = ctypes.get_last_error()
            return None, err == ERROR_ACCESS_DENIED
        return handle, False

    def _read_times(self, handle):
        """(生成時刻, カーネル+ユーザー時間) を 100ns 単位で返す. 失敗時 None."""
        creation = wintypes.FILETIME()
        exit_ = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not _k32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        return _ft_to_int(creation), _ft_to_int(kernel) + _ft_to_int(user)

    # ------------------------------------------------------------------
    def sample(self):
        """1 回計測して {プロセス名: ProcessSample} を返す.

        初回呼び出しは差分が取れないので percent=0 / valid=False になる。
        """
        now = time.perf_counter()
        elapsed = None if self._last_perf is None else now - self._last_perf
        self._last_perf = now

        results = {name: ProcessSample(name=name, valid=elapsed is not None)
                   for name in self.names}
        if not IS_WINDOWS:
            return results

        alive = set()
        cpu_delta = {name: 0 for name in self.names}

        for pid, exe in list_processes():
            name = self._lookup.get(exe.lower())
            if name is None:
                continue
            alive.add(pid)
            sample = results[name]
            sample.instances += 1
            sample.pids.append(pid)

            tracked = self._tracked.get(pid)
            if tracked is None:
                handle, denied = self._open(pid)
                tracked = _Tracked(handle, None, None, denied)
                self._tracked[pid] = tracked
            if tracked.handle is None:
                if tracked.denied:
                    sample.access_denied += 1
                continue

            times = self._read_times(tracked.handle)
            if times is None:
                _k32.CloseHandle(tracked.handle)
                tracked.handle = None
                continue
            created, total = times

            if tracked.created == created and tracked.cpu_100ns is not None:
                cpu_delta[name] += max(0, total - tracked.cpu_100ns)
            tracked.created = created
            tracked.cpu_100ns = total

        # 終了したプロセスのハンドルを解放
        for pid in [p for p in self._tracked if p not in alive]:
            tracked = self._tracked.pop(pid)
            if tracked.handle:
                _k32.CloseHandle(tracked.handle)

        if elapsed and elapsed > 0:
            for name, delta in cpu_delta.items():
                results[name].percent = (delta / FILETIME_PER_SEC) / elapsed * 100.0

        return results
