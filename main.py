"""无线快传 - Kivy 应用主入口"""
import os
import sys
import threading
import time
import uuid
from typing import Optional

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty, ListProperty, ObjectProperty, NumericProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.utils import get_color_from_hex

from core.discovery import DiscoveryService, get_local_ips, get_device_name
from core.transfer import TransferServer, TransferClient
from core.utils import format_size, format_speed, format_eta, default_download_dir, ensure_dir

KV = """
#:import get_color_from_hex kivy.utils.get_color_from_hex

<FlatButton@Button>:
    background_normal: ''
    background_color: get_color_from_hex('#2196F3')
    color: 1, 1, 1, 1
    size_hint_y: None
    height: '48dp'
    font_size: '16sp'

<DeviceRow@BoxLayout>:
    orientation: 'horizontal'
    size_hint_y: None
    height: '64dp'
    spacing: '8dp'
    padding: '8dp'
    canvas.before:
        Color:
            rgba: get_color_from_hex('#FFFFFF')
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [8,]
    Label:
        text: root.device_name
        color: get_color_from_hex('#212121')
        font_size: '15sp'
        size_hint_x: 0.55
        text_size: self.size
        halign: 'left'
        valign: 'middle'
    Label:
        text: root.device_info
        color: get_color_from_hex('#757575')
        font_size: '12sp'
        size_hint_x: 0.25
        text_size: self.size
        halign: 'left'
        valign: 'middle'
    Button:
        text: '发送文件'
        background_normal: ''
        background_color: get_color_from_hex('#2196F3')
        color: 1, 1, 1, 1
        size_hint_x: 0.2
        font_size: '13sp'
        on_press: root.dispatch('on_send')
        disabled: root.is_sending

<TransferRow@BoxLayout>:
    orientation: 'vertical'
    size_hint_y: None
    height: '72dp'
    padding: '6dp'
    spacing: '2dp'
    canvas.before:
        Color:
            rgba: get_color_from_hex('#F5F5F5')
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [6,]
    Label:
        text: root.title
        color: get_color_from_hex('#212121')
        font_size: '13sp'
        size_hint_y: None
        height: '18dp'
        text_size: self.size
        halign: 'left'
        valign: 'middle'
    Label:
        text: root.subtitle
        color: get_color_from_hex('#757575')
        font_size: '11sp'
        size_hint_y: None
        height: '16dp'
        text_size: self.size
        halign: 'left'
        valign: 'middle'
    ProgressBar:
        value: root.progress
        size_hint_y: None
        height: '12dp'

BoxLayout:
    orientation: 'vertical'
    padding: '12dp'
    spacing: '10dp'
    canvas.before:
        Color:
            rgba: get_color_from_hex('#FAFAFA')
        Rectangle:
            pos: self.pos
            size: self.size

    # 顶部标题栏
    BoxLayout:
        orientation: 'horizontal'
        size_hint_y: None
        height: '48dp'
        spacing: '10dp'
        Label:
            text: '⚡ 无线快传'
            color: get_color_from_hex('#212121')
            font_size: '22sp'
            bold: True
            size_hint_x: 0.5
            text_size: self.size
            halign: 'left'
            valign: 'center'
        Label:
            id: lbl_local
            text: '本机: 计算中...'
            color: get_color_from_hex('#616161')
            font_size: '12sp'
            size_hint_x: 0.5
            text_size: self.size
            halign: 'right'
            valign: 'center'

    # Tab 切换
    BoxLayout:
        orientation: 'horizontal'
        size_hint_y: None
        height: '40dp'
        spacing: '6dp'
        Button:
            id: tab_devices
            text: '附近设备'
            background_normal: ''
            background_color: get_color_from_hex('#1976D2')
            color: 1, 1, 1, 1
            font_size: '14sp'
            on_press: app.show_tab('devices')
        Button:
            id: tab_transfers
            text: '传输列表'
            background_normal: ''
            background_color: get_color_from_hex('#90CAF9')
            color: 1, 1, 1, 1
            font_size: '14sp'
            on_press: app.show_tab('transfers')
        Button:
            id: tab_received
            text: '已接收'
            background_normal: ''
            background_color: get_color_from_hex('#90CAF9')
            color: 1, 1, 1, 1
            font_size: '14sp'
            on_press: app.show_tab('received')

    # 主内容区
    BoxLayout:
        id: main_area
        orientation: 'vertical'

    # 底部操作栏
    BoxLayout:
        orientation: 'horizontal'
        size_hint_y: None
        height: '56dp'
        spacing: '8dp'
        Button:
            text: '选择文件发送'
            background_normal: ''
            background_color: get_color_from_hex('#2196F3')
            color: 1, 1, 1, 1
            font_size: '15sp'
            on_press: app.choose_files()
        Button:
            text: '设置接收目录'
            background_normal: ''
            background_color: get_color_from_hex('#4CAF50')
            color: 1, 1, 1, 1
            font_size: '15sp'
            on_press: app.choose_save_dir()
"""


class DeviceRow(BoxLayout):
    device_name = StringProperty("")
    device_info = StringProperty("")
    is_sending = BooleanProperty(False)

    def __init__(self, device, on_send_callback, **kwargs):
        self.device = device
        self.device_name = device.name
        self.device_info = f"{device.ip}:{device.port}"
        self._on_send = on_send_callback
        self.register_event_type("on_send")
        super().__init__(**kwargs)

    def on_send(self):
        if self._on_send:
            self._on_send(self.device)


class TransferRow(BoxLayout):
    title = StringProperty("")
    subtitle = StringProperty("")
    progress = NumericProperty(0.0)


class ReceivedRow(BoxLayout):
    title = StringProperty("")
    subtitle = StringProperty("")


class WuxianApp(App):
    """无线快传主应用"""

    local_ips = ListProperty([])
    device_name = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_id = uuid.uuid4().hex[:12]
        self.device_name = get_device_name()
        self.local_ips = get_local_ips()

        self.save_dir = default_download_dir()
        ensure_dir(self.save_dir)

        self.discovery: Optional[DiscoveryService] = None
        self.server: Optional[TransferServer] = None
        self.client: Optional[TransferClient] = None

        self._device_widgets: dict[str, DeviceRow] = {}
        self._transfer_widgets: dict[str, TransferRow] = {}
        self._received_files: list[tuple[str, str]] = []

        # Kivy 必须在主线程创建，但 discovery/server 在后台线程
        # 通过 Clock.schedule_once 在主线程更新 UI

    def build(self):
        Window.clearcolor = get_color_from_hex('#FAFAFA')
        root = Builder.load_string(KV)
        self.root = root
        self.ids = root.ids

        # 主内容三块容器
        self._devices_box = BoxLayout(orientation='vertical', spacing=6, size_hint_y=None)
        self._devices_box.bind(minimum_height=self._devices_box.setter('height'))
        self._devices_scroll = ScrollView()
        self._devices_scroll.add_widget(self._devices_box)

        self._transfers_box = BoxLayout(orientation='vertical', spacing=6, size_hint_y=None)
        self._transfers_box.bind(minimum_height=self._transfers_box.setter('height'))
        self._transfers_scroll = ScrollView()
        self._transfers_scroll.add_widget(self._transfers_box)

        self._received_box = BoxLayout(orientation='vertical', spacing=6, size_hint_y=None)
        self._received_box.bind(minimum_height=self._received_box.setter('height'))
        self._received_scroll = ScrollView()
        self._received_scroll.add_widget(self._received_box)

        self.ids.main_area.add_widget(self._devices_scroll)
        self._add_placeholder(self._devices_box, "正在搜索附近的设备…")
        self._add_placeholder(self._transfers_box, "暂无传输任务")
        self._add_placeholder(self._received_box, "暂无接收的文件")

        self._refresh_local_label()
        self._start_backend()
        self.show_tab('devices')
        return root

    # ---------- UI 辅助 ----------

    def _add_placeholder(self, container, text):
        if len(container.children) == 0 or not getattr(container.children[0], 'is_placeholder', False):
            lbl = Label(text=text, color=get_color_from_hex('#9E9E9E'),
                        font_size='14sp', size_hint_y=None, height='40dp',
                        text_size=(Window.width, 40), halign='center', valign='middle')
            lbl.is_placeholder = True
            container.add_widget(lbl)

    def _clear_placeholder(self, container):
        for child in list(container.children):
            if getattr(child, 'is_placeholder', False):
                container.remove_widget(child)

    def _refresh_local_label(self):
        ip_str = ", ".join(self.local_ips[:2]) if self.local_ips else "未知"
        self.ids.lbl_local.text = f"本机: {self.device_name}  IP: {ip_str}"

    def show_tab(self, tab: str):
        self.ids.main_area.clear_widgets()
        if tab == 'devices':
            self.ids.main_area.add_widget(self._devices_scroll)
            self.ids.tab_devices.background_color = get_color_from_hex('#1976D2')
            self.ids.tab_transfers.background_color = get_color_from_hex('#90CAF9')
            self.ids.tab_received.background_color = get_color_from_hex('#90CAF9')
        elif tab == 'transfers':
            self.ids.main_area.add_widget(self._transfers_scroll)
            self.ids.tab_devices.background_color = get_color_from_hex('#90CAF9')
            self.ids.tab_transfers.background_color = get_color_from_hex('#1976D2')
            self.ids.tab_received.background_color = get_color_from_hex('#90CAF9')
        elif tab == 'received':
            self.ids.main_area.add_widget(self._received_scroll)
            self.ids.tab_devices.background_color = get_color_from_hex('#90CAF9')
            self.ids.tab_transfers.background_color = get_color_from_hex('#90CAF9')
            self.ids.tab_received.background_color = get_color_from_hex('#1976D2')

    # ---------- 后端服务 ----------

    def _start_backend(self):
        # 启动 HTTP 接收服务器
        self.server = TransferServer(
            save_dir=self.save_dir,
            on_request=self._on_incoming_request,
            on_progress=self._on_recv_progress,
            on_done=self._on_recv_done,
        )
        self.server.start()

        # 启动发送客户端
        self.client = TransferClient(
            on_progress=self._on_send_progress,
            on_done=self._on_send_done,
        )

        # 启动设备发现
        self.discovery = DiscoveryService(
            device_id=self.device_id,
            device_name=self.device_name,
            transfer_port=self.server.port,
            on_device=self._on_device_found,
            on_expire=self._on_device_expired,
        )
        self.discovery.start()

    # ---------- 设备发现回调（后台线程 -> 主线程） ----------

    def _on_device_found(self, device):
        Clock.schedule_once(lambda dt: self._ui_add_device(device), 0)

    def _on_device_expired(self, device_id):
        Clock.schedule_once(lambda dt: self._ui_remove_device(device_id), 0)

    def _ui_add_device(self, device):
        self._clear_placeholder(self._devices_box)
        if device.id in self._device_widgets:
            row = self._device_widgets[device.id]
            row.device_name = device.name
            row.device_info = f"{device.ip}:{device.port}"
            return
        row = DeviceRow(device, self._start_send_dialog)
        self._device_widgets[device.id] = row
        self._devices_box.add_widget(row)

    def _ui_remove_device(self, device_id):
        row = self._device_widgets.pop(device_id, None)
        if row:
            self._devices_box.remove_widget(row)
        if not self._device_widgets:
            self._add_placeholder(self._devices_box, "附近没有设备，请确认在同一 WiFi 下")

    # ---------- 文件选择 ----------

    def choose_files(self):
        try:
            from kivy.uix.filechooser import FileChooserListView
            from kivy.uix.popup import Popup
        except Exception:
            self._popup_msg("无法启动文件选择器")
            return

        chooser = FileChooserListView(multiselect=True, dirselect=True)
        chooser.path = os.path.expanduser("~") if os.path.expanduser("~") else os.getcwd()

        box = BoxLayout(orientation='vertical')
        box.add_widget(chooser)
        btn_box = BoxLayout(orientation='horizontal', size_hint_y=None, height='48dp', spacing='6dp')
        ok_btn = Button(text='确认', background_color=get_color_from_hex('#2196F3'),
                        background_normal='', color=(1,1,1,1))
        cancel_btn = Button(text='取消', background_color=get_color_from_hex('#9E9E9E'),
                            background_normal='', color=(1,1,1,1))
        btn_box.add_widget(ok_btn); btn_box.add_widget(cancel_btn)
        box.add_widget(btn_box)

        popup = Popup(title='选择文件或文件夹', content=box, size_hint=(0.95, 0.95))
        ok_btn.bind(on_press=lambda *_: self._on_files_chosen(chooser, popup))
        cancel_btn.bind(on_press=popup.dismiss)
        popup.open()

    def _on_files_chosen(self, chooser, popup):
        popup.dismiss()
        paths = list(chooser.selection)
        if not paths:
            return
        # 收集所有文件
        from core.utils import list_files_in_dir
        files = []
        for p in paths:
            files.extend(list_files_in_dir(p))
        if not files:
            self._popup_msg("未找到可发送的文件")
            return
        # 选择目标设备
        devices = self.discovery.get_devices() if self.discovery else []
        if not devices:
            self._popup_msg("附近没有设备，请先等待对方上线")
            return
        self._show_target_picker(files, devices)

    def _show_target_picker(self, files, devices):
        box = BoxLayout(orientation='vertical', spacing='4dp')
        scroll = ScrollView()
        list_box = BoxLayout(orientation='vertical', spacing='4dp', size_hint_y=None)
        list_box.bind(minimum_height=list_box.setter('height'))
        scroll.add_widget(list_box)
        box.add_widget(scroll)
        for dev in devices:
            b = Button(text=f"{dev.name}  ({dev.ip})", size_hint_y=None, height='48dp',
                       background_color=get_color_from_hex('#2196F3'), background_normal='',
                       color=(1,1,1,1))
            b.bind(on_press=lambda btn, d=dev: self._confirm_send_to(d, files, popup))
            list_box.add_widget(b)
        close_btn = Button(text='关闭', size_hint_y=None, height='40dp',
                            background_color=get_color_from_hex('#9E9E9E'), background_normal='',
                            color=(1,1,1,1))
        close_btn.bind(on_press=lambda *_: popup.dismiss())
        box.add_widget(close_btn)
        popup = Popup(title=f'选择目标设备 ({len(files)} 个文件)', content=box,
                     size_hint=(0.85, 0.7))
        popup.open()

    def _confirm_send_to(self, device, files, popup):
        popup.dismiss()
        for path in files:
            self._send_one(device, path)

    def _start_send_dialog(self, device):
        # 点击设备行的"发送文件"按钮
        self.choose_files()
        # 记录目标设备以便选完文件后直发（简单实现：保存待发送目标）
        self._pending_target = device

    def _send_one(self, device, path: str):
        # 在后台线程发送
        fid = uuid.uuid4().hex[:8]
        fname = os.path.basename(path)
        fsize = os.path.getsize(path)
        title = f"↑ {fname}"
        subtitle = f"{format_size(fsize)} → {device.name}"
        row = TransferRow(title=title, subtitle=subtitle, progress=0)
        self._transfer_widgets[fid] = row
        self._clear_placeholder(self._transfers_box)
        self._transfers_box.add_widget(row)

        def worker():
            try:
                self.client.send_file_async(device.ip, device.port, path, file_id=fid)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_send_failed(fid, str(e)), 0)

        threading.Thread(target=worker, daemon=True).start()

    # ---------- 传输进度回调 ----------

    def _on_send_progress(self, file_id, file_name, sent, total):
        Clock.schedule_once(lambda dt: self._update_progress(file_id, file_name, sent, total, is_send=True), 0)

    def _on_recv_progress(self, file_id, file_name, received, total):
        Clock.schedule_once(lambda dt: self._update_progress(file_id, file_name, received, total, is_send=False), 0)

    def _update_progress(self, file_id, file_name, sent, total, is_send=True):
        row = self._transfer_widgets.get(file_id)
        if not row:
            prefix = "↑ " if is_send else "↓ "
            row = TransferRow(
                title=f"{prefix}{file_name}",
                subtitle=f"{format_size(sent)} / {format_size(total)}",
                progress=0,
            )
            self._clear_placeholder(self._transfers_box)
            self._transfers_box.add_widget(row)
            self._transfer_widgets[file_id] = row
        pct = (sent * 100.0 / total) if total else 0
        row.progress = pct
        row.subtitle = f"{format_size(sent)} / {format_size(total)}"

    def _on_send_done(self, file_id, file_name, ok, info):
        Clock.schedule_once(lambda dt: self._finish_transfer(file_id, file_name, ok, info, is_send=True), 0)

    def _on_recv_done(self, file_id, file_name, ok, info):
        Clock.schedule_once(lambda dt: self._finish_transfer(file_id, file_name, ok, info, is_send=False), 0)
        if ok:
            Clock.schedule_once(lambda dt: self._add_received(file_name, info), 0)

    def _on_incoming_request(self, meta):
        # 新的接收任务开始 - 创建行
        fid = meta.get("id", "?")
        fname = meta.get("name", "?")
        fsize = int(meta.get("size", 0))
        row = TransferRow(
            title=f"↓ {fname}",
            subtitle=f"{format_size(fsize)}",
            progress=0,
        )
        self._clear_placeholder(self._transfers_box)
        self._transfers_box.add_widget(row)
        self._transfer_widgets[fid] = row

    def _finish_transfer(self, file_id, file_name, ok, info, is_send=True):
        row = self._transfer_widgets.get(file_id)
        if not row:
            return
        if ok:
            row.progress = 100
            row.subtitle = "完成 ✓" if is_send else f"已保存: {info}"
        else:
            row.subtitle = f"失败: {info}"

    def _on_send_failed(self, file_id, err):
        row = self._transfer_widgets.get(file_id)
        if row:
            row.subtitle = f"失败: {err}"

    def _add_received(self, name, path):
        self._clear_placeholder(self._received_box)
        row = ReceivedRow(
            title=name,
            subtitle=f"保存于: {path}",
        )
        self._received_box.add_widget(row)
        self._received_files.append((name, path))

    # ---------- 接收目录 ----------

    def choose_save_dir(self):
        try:
            from kivy.uix.filechooser import FileChooserListView
        except Exception:
            self._popup_msg("无法启动文件选择器")
            return
        chooser = FileChooserListView(multiselect=False, dirselect=True)
        chooser.path = self.save_dir
        box = BoxLayout(orientation='vertical')
        box.add_widget(chooser)
        btn_box = BoxLayout(orientation='horizontal', size_hint_y=None, height='48dp', spacing='6dp')
        ok = Button(text='确认', background_normal='', background_color=get_color_from_hex('#4CAF50'), color=(1,1,1,1))
        no = Button(text='取消', background_normal='', background_color=get_color_from_hex('#9E9E9E'), color=(1,1,1,1))
        btn_box.add_widget(ok); btn_box.add_widget(no)
        box.add_widget(btn_box)
        popup = Popup(title='选择接收文件保存目录', content=box, size_hint=(0.95, 0.95))
        ok.bind(on_press=lambda *_: self._set_save_dir(chooser, popup))
        no.bind(on_press=popup.dismiss)
        popup.open()

    def _set_save_dir(self, chooser, popup):
        popup.dismiss()
        if chooser.selection:
            self.save_dir = chooser.selection[0]
            ensure_dir(self.save_dir)
            if self.server:
                self.server.save_dir = self.save_dir
        self._popup_msg(f"接收目录已设为:\n{self.save_dir}")

    # ---------- 通用 ----------

    def _popup_msg(self, msg: str):
        box = BoxLayout(orientation='vertical', padding='12dp', spacing='10dp')
        lbl = Label(text=msg, color=get_color_from_hex('#212121'))
        box.add_widget(lbl)
        btn = Button(text='确定', size_hint_y=None, height='48dp',
                     background_normal='', background_color=get_color_from_hex('#2196F3'),
                     color=(1,1,1,1))
        box.add_widget(btn)
        popup = Popup(title='提示', content=box, size_hint=(0.8, 0.4))
        btn.bind(on_press=popup.dismiss)
        popup.open()

    def on_stop(self):
        try:
            if self.discovery: self.discovery.stop()
            if self.server: self.server.stop()
            if self.client: self.client.stop()
        except Exception:
            pass


def main():
    app = WuxianApp()
    app.run()


if __name__ == "__main__":
    main()
