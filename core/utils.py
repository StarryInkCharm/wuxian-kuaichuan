"""通用工具：格式化、文件操作"""
import os
import time
import socket
from typing import Iterable


def format_size(n: int) -> str:
    if n is None:
        return "-"
    if n < 1024:
        return f"{n} B"
    units = ["KB", "MB", "GB", "TB"]
    v = n / 1024
    for u in units:
        if v < 1024 or u == "TB":
            return f"{v:.2f} {u}"
        v /= 1024
    return f"{n} B"


def format_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec <= 0:
        return "0 B/s"
    return format_size(int(bytes_per_sec)) + "/s"


def format_eta(remaining_bytes: int, speed: float) -> str:
    if speed <= 0 or remaining_bytes <= 0:
        return "--:--"
    s = int(remaining_bytes / speed)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def list_files_in_dir(path: str) -> list[str]:
    if not path or not os.path.exists(path):
        return []
    if os.path.isfile(path):
        return [path]
    out = []
    for root, _dirs, files in os.walk(path):
        for f in files:
            out.append(os.path.join(root, f))
    return out


def ensure_dir(path: str):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def default_download_dir() -> str:
    candidates = []
    for env_var in ("USERPROFILE", "HOME"):
        if os.environ.get(env_var):
            home = os.environ[env_var]
            for sub in ("Downloads", "下载", "Documents", "桌面"):
                candidates.append(os.path.join(home, sub))
            candidates.append(home)
    for c in candidates:
        if os.path.isdir(c):
            return c
    return os.getcwd()
