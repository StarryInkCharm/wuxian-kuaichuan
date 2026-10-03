"""文件传输模块 - HTTP 服务端（接收方）+ HTTP 客户端（发送方）"""
import os
import json
import asyncio
import time
import socket
import threading
import hashlib
from typing import Callable, Optional, Awaitable
from concurrent.futures import ThreadPoolExecutor

from aiohttp import web, ClientSession, TCPConnector, MultipartWriter

# 每次写入磁盘的块大小 - 8 MB 兼顾性能与内存
CHUNK_SIZE = 8 * 1024 * 1024


def _sha256_file(path: str, max_size: int = 1 << 30) -> str:
    """计算文件 SHA256（小文件才校验，>1GB 跳过避免性能问题）"""
    try:
        size = os.path.getsize(path)
        if size > max_size:
            return ""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()
    except Exception:
        return ""


def _get_local_ip_for(remote_ip: str) -> str:
    """获取到达 remote_ip 用的本机 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((remote_ip, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _pick_free_port(preferred: int = 0) -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", preferred))
    port = s.getsockname()[1]
    s.close()
    return port


# ===================== 服务端（接收方） =====================

class TransferServer:
    """HTTP 服务器，接收文件并保存到指定目录"""

    def __init__(
        self,
        save_dir: str,
        on_request: Optional[Callable[[dict], None]] = None,
        on_progress: Optional[Callable[[str, str, int, int], None]] = None,
        on_done: Optional[Callable[[str, str, bool, str], None]] = None,
        host: str = "0.0.0.0",
    ):
        self.save_dir = save_dir
        self.on_request = on_request
        self.on_progress = on_progress
        self.on_done = on_done
        self.host = host
        self.port = _pick_free_port()
        self._app = web.Application(client_max_size=1024 * 1024 * 1024 * 16)
        self._app.router.add_post("/file", self._handle_file)
        self._app.router.add_get("/info", self._handle_info)
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            loop.run_until_complete(self._serve())
            loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True, name="transfer-server")
        self._thread.start()

    async def _serve(self):
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

    def stop(self):
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        if self._thread:
            self._thread.join(timeout=3.0)

    async def _shutdown(self):
        if self._runner:
            await self._runner.cleanup()

    async def _handle_info(self, request: web.Request):
        return web.json_response({"ok": True, "service": "wuxian-kuai-chuan"})

    async def _handle_file(self, request: web.Request):
        # 用 multipart 上传，避免整体载入内存
        reader = await request.multipart()
        meta = None
        save_path = None
        try:
            while True:
                part = await reader.next()
                if part is None:
                    break
                if part.name == "meta":
                    meta = json.loads(await part.read())
                    if self.on_request:
                        try: self.on_request(meta)
                        except Exception: pass
                    save_path = self._build_save_path(meta)
                elif part.name == "data" and save_path is not None:
                    total = int(meta.get("size", 0)) if meta else 0
                    received = 0
                    file_id = meta.get("id", "unknown") if meta else "unknown"
                    file_name = meta.get("name", "file") if meta else "file"
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    tmp_path = save_path + ".part"
                    with open(tmp_path, "wb") as f:
                        while True:
                            chunk = await part.read_chunk(CHUNK_SIZE)
                            if not chunk:
                                break
                            f.write(chunk)
                            received += len(chunk)
                            if self.on_progress:
                                try:
                                    self.on_progress(file_id, file_name, received, total)
                                except Exception:
                                    pass
                    os.replace(tmp_path, save_path)
                    if self.on_done:
                        try:
                            self.on_done(file_id, file_name, True, save_path)
                        except Exception:
                            pass
                else:
                    # 未知部分直接读完丢弃
                    await part.read()
            return web.json_response({"ok": True, "path": save_path})
        except Exception as e:
            if save_path and self.on_done:
                try:
                    self.on_done(meta.get("id", "?") if meta else "?",
                                 meta.get("name", "?") if meta else "?",
                                 False, str(e))
                except Exception:
                    pass
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    def _build_save_path(self, meta: dict) -> str:
        name = meta.get("name", "file.bin")
        # 简单去路径分隔符，避免目录穿越
        name = name.replace("/", "_").replace("\\", "_").strip()
        if not name:
            name = "file.bin"
        # 若已存在，加序号
        target = os.path.join(self.save_dir, name)
        if os.path.exists(target):
            base, ext = os.path.splitext(name)
            i = 1
            while os.path.exists(os.path.join(self.save_dir, f"{base} ({i}){ext}")):
                i += 1
            target = os.path.join(self.save_dir, f"{base} ({i}){ext}")
        return target


# ===================== 客户端（发送方） =====================

class TransferClient:
    """HTTP 客户端，向远端设备发送文件"""

    def __init__(
        self,
        on_progress: Optional[Callable[[str, str, int, int], None]] = None,
        on_done: Optional[Callable[[str, str, bool, str], None]] = None,
        chunk_size: int = CHUNK_SIZE,
    ):
        self.on_progress = on_progress
        self.on_done = on_done
        self.chunk_size = chunk_size
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._loop = asyncio.new_event_loop()

    def stop(self):
        self._executor.shutdown(wait=False)
        try:
            self._loop.close()
        except Exception:
            pass

    def send_file_async(self, host: str, port: int, path: str, file_id: Optional[str] = None) -> str:
        """同步阻塞调用，返回服务端返回的保存路径。出错抛出异常"""
        return asyncio.run_coroutine_threadsafe(
            self._send_file(host, port, path, file_id), self._loop
        ).result()

    async def _send_file(self, host: str, port: int, path: str, file_id: Optional[str]) -> str:
        import uuid as _uuid
        file_id = file_id or _uuid.uuid4().hex[:8]
        file_name = os.path.basename(path)
        file_size = os.path.getsize(path)
        url = f"http://{host}:{port}/file"
        # 流式 multipart - 边读边发，避免一次性载入
        connector = TCPConnector(limit=8, force_close=False)
        timeout = aiohttp_timeout(file_size)
        async with ClientSession(connector=connector, timeout=timeout) as session:
            with MultipartWriter("form-data") as mp:
                mp.append_json({
                    "id": file_id, "name": file_name, "size": file_size,
                    "sha256": _sha256_file(path),
                }, headers={"Content-Disposition": 'form-data; name="meta"'})
                # 流式读取文件的 part
                f = open(path, "rb")
                try:
                    mp.append(f, headers={
                        "Content-Disposition": f'form-data; name="data"; filename="{file_name}"',
                        "Content-Length": str(file_size),
                    })
                    # 自定义流式写入：包装 MultipartWriter 的 append 后，我们用 stream API
                    # aiohttp 会自动按 chunk 推送，但我们要触发进度回调，所以用自定义 writer
                finally:
                    pass
                # 用自定义流推送：aiohttp 默认就把大文件按 64KB 切片发，我们 wrap 一下读取以触发回调
                # 这里改为手动构造 body
                # —— 简化：使用 multipart + 文件对象，依赖 aiohttp 内部切片；用 monitor 包装 file 读取
                monitor = _ProgressFile(f, file_id, file_name, file_size, self.on_progress)
                mp.parts[-1].body = _StreamBody(monitor, file_size)
                async with session.post(url, data=mp) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        if self.on_done:
                            try: self.on_done(file_id, file_name, False, text)
                            except Exception: pass
                        raise RuntimeError(f"远端返回 {resp.status}: {text}")
                    try:
                        result = json.loads(text)
                    except Exception:
                        result = {"ok": False, "error": text}
                    if self.on_done:
                        ok = bool(result.get("ok"))
                        try:
                            self.on_done(file_id, file_name, ok, result.get("path") or result.get("error", ""))
                        except Exception:
                            pass
                    f.close()
                    if not result.get("ok"):
                        raise RuntimeError(result.get("error", "传输失败"))
                    return result.get("path", "")


def aiohttp_timeout(file_size: int):
    from aiohttp import ClientTimeout
    seconds = max(60, file_size / (1 * 1024 * 1024))  # 至少 60s，按 1MB/s 兜底
    return ClientTimeout(total=int(seconds) + 30)


class _ProgressFile:
    """包装文件对象，每次读取触发进度回调"""

    def __init__(self, f, file_id: str, file_name: str, total: int,
                 cb: Optional[Callable[[str, str, int, int], None]]):
        self._f = f
        self._file_id = file_id
        self._file_name = file_name
        self._total = total
        self._cb = cb
        self._sent = 0
        self._last_ts = time.time()

    def read(self, n: int = -1):
        if n is None or n < 0:
            data = self._f.read()
        else:
            data = self._f.read(n)
        if data:
            self._sent += len(data)
            now = time.time()
            if self._cb and (now - self._last_ts >= 0.1 or self._sent >= self._total):
                self._last_ts = now
                try:
                    self._cb(self._file_id, self._file_name, self._sent, self._total)
                except Exception:
                    pass
        return data

    def seek(self, *a, **kw):
        return self._f.seek(*a, **kw)

    def tell(self):
        return self._f.tell()

    def close(self):
        return self._f.close()

    def __iter__(self):
        return self

    def __next__(self):
        data = self.read(65536)
        if not data:
            raise StopIteration
        return data


class _StreamBody:
    """aiohttp 兼容的流式 body"""

    def __init__(self, monitor: _ProgressFile, size: int):
        self._monitor = monitor
        self.size = size

    async def read(self, n: int = -1):
        return self._monitor.read(n if n and n > 0 else 65536)

    async def readany(self):
        return self._monitor.read(65536)

    async def readchunk(self):
        return self._monitor.read(65536)

    def write(self, writer):
        # 同步 fallback（一般不会走到）
        while True:
            data = self._monitor.read(65536)
            if not data:
                break
            writer.write(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        data = self._monitor.read(65536)
        if not data:
            raise StopAsyncIteration
        return data
