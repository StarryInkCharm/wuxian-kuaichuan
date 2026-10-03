"""设备发现模块 - 使用 UDP 广播在局域网内自动发现设备"""
import socket
import json
import threading
import time
import uuid
from typing import Callable, Optional

DISCOVERY_PORT = 53210
DISCOVERY_MAGIC = "WUXIAN_KUAI_CHUAN_V1"
BROADCAST_ADDR = "255.255.255.255"


def get_local_ips() -> list[str]:
    """获取本机所有 IPv4 地址（用于显示和过滤）"""
    ips = ["127.0.0.1"]
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("169.254"):
                ips.append(ip)
    except Exception:
        pass
    # 通过连接外部地址获取主网卡 IP（不实际发包）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        main_ip = s.getsockname()[0]
        s.close()
        if main_ip not in ips:
            ips.insert(0, main_ip)
    except Exception:
        pass
    return ips


def get_device_name() -> str:
    """生成设备名（主机名 + 短 ID）"""
    try:
        hostname = socket.gethostname() or "Unknown"
    except Exception:
        hostname = "Unknown"
    short_id = str(uuid.uuid4())[:4]
    return f"{hostname}-{short_id}"


class Device:
    """已发现的远端设备"""
    __slots__ = ("id", "name", "ip", "port", "last_seen")

    def __init__(self, id: str, name: str, ip: str, port: int):
        self.id = id
        self.name = name
        self.ip = ip
        self.port = port
        self.last_seen = time.time()

    def __repr__(self):
        return f"Device(name={self.name}, ip={self.ip}, port={self.port})"

    def is_expired(self, timeout: float = 15.0) -> bool:
        return time.time() - self.last_seen > timeout

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "ip": self.ip, "port": self.port}


class DiscoveryService:
    """UDP 广播发现服务：周期性广播自身，监听他人广播"""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        transfer_port: int,
        on_device: Optional[Callable[[Device], None]] = None,
        on_expire: Optional[Callable[[str], None]] = None,
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.transfer_port = transfer_port
        self.on_device = on_device
        self.on_expire = on_expire
        self._devices: dict[str, Device] = {}
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._threads: list[threading.Thread] = []
        self._sock_recv: Optional[socket.socket] = None
        self._sock_send: Optional[socket.socket] = None

    def start(self):
        if self._running.is_set():
            return
        self._running.set()
        # 接收 socket - 绑定到所有接口
        self._sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock_recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock_recv.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            pass
        self._sock_recv.bind(("", DISCOVERY_PORT))
        self._sock_recv.settimeout(2.0)

        # 发送 socket
        self._sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock_send.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        t_recv = threading.Thread(target=self._recv_loop, daemon=True, name="discovery-recv")
        t_send = threading.Thread(target=self._send_loop, daemon=True, name="discovery-send")
        t_clean = threading.Thread(target=self._clean_loop, daemon=True, name="discovery-clean")
        t_recv.start(); t_send.start(); t_clean.start()
        self._threads = [t_recv, t_send, t_clean]

    def stop(self):
        self._running.clear()
        for s in (self._sock_recv, self._sock_send):
            if s:
                try: s.close()
                except Exception: pass
        self._sock_recv = self._sock_send = None
        with self._lock:
            self._devices.clear()

    def get_devices(self) -> list[Device]:
        with self._lock:
            return list(self._devices.values())

    def _payload(self) -> bytes:
        return json.dumps({
            "magic": DISCOVERY_MAGIC,
            "id": self.device_id,
            "name": self.device_name,
            "port": self.transfer_port,
        }).encode("utf-8")

    def _send_loop(self):
        while self._running.is_set():
            try:
                if self._sock_send:
                    self._sock_send.sendto(self._payload(), (BROADCAST_ADDR, DISCOVERY_PORT))
            except Exception:
                pass
            for _ in range(20):  # 2 秒内可被快速中断
                if not self._running.is_set():
                    break
                time.sleep(0.1)

    def _recv_loop(self):
        while self._running.is_set():
            try:
                if not self._sock_recv:
                    break
                try:
                    data, addr = self._sock_recv.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    msg = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
                if msg.get("magic") != DISCOVERY_MAGIC:
                    continue
                if msg.get("id") == self.device_id:
                    continue
                dev = Device(
                    id=msg["id"], name=msg.get("name", "Unknown"),
                    ip=addr[0], port=int(msg.get("port", 0))
                )
                is_new = False
                with self._lock:
                    old = self._devices.get(dev.id)
                    if old:
                        old.last_seen = time.time()
                        old.name = dev.name
                        old.port = dev.port
                    else:
                        self._devices[dev.id] = dev
                        is_new = True
                if is_new and self.on_device:
                    try: self.on_device(dev)
                    except Exception: pass
            except Exception:
                pass

    def _clean_loop(self):
        while self._running.is_set():
            expired_ids = []
            with self._lock:
                for did, dev in list(self._devices.items()):
                    if dev.is_expired():
                        expired_ids.append(did)
                        del self._devices[did]
            for did in expired_ids:
                if self.on_expire:
                    try: self.on_expire(did)
                    except Exception: pass
            for _ in range(50):  # 5 秒检查间隔
                if not self._running.is_set():
                    break
                time.sleep(0.1)
