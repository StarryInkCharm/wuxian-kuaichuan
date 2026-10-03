# 无线快传 ⚡

一个基于局域网的无线、无速度限制的文件快传应用，单一代码库同时打包为 **Windows EXE** 与 **Android APK**。

## 特性

- 同一 WiFi 下自动发现设备（UDP 广播，无需手动输入 IP）
- HTTP 流式传输，无文件大小上限、无速度限制（瓶颈仅为你的 WiFi 带宽）
- 多文件批量发送，实时进度显示
- 自动按命名冲突规避保存
- 跨平台单代码库（Windows + Android）

## 项目结构

```
无线快传/
├── main.py              # Kivy 应用入口 + UI
├── core/
│   ├── discovery.py     # UDP 设备发现
│   ├── transfer.py      # HTTP 文件传输（服务端 + 客户端）
│   └── utils.py         # 工具函数
├── requirements.txt
├── build_exe.spec       # PyInstaller 配置（Windows）
├── build_exe.py         # 一键构建 EXE
├── buildozer.spec       # Buildozer 配置（Android）
└── .github/workflows/build-apk.yml   # 云端构建 APK
```

## Windows EXE 构建与运行

### 直接运行（开发模式）
```powershell
pip install -r requirements.txt
python main.py
```

### 打包为 EXE
```powershell
python build_exe.py
```
产物位于 `dist/无线快传/无线快传.exe`，约 86 MB（含 Kivy + Python 运行时）。

## Android APK 构建

由于 Buildozer 必须在 Linux 环境运行，本仓库提供两种方式构建 APK：

### 方式 A：GitHub Actions 云端构建（推荐，零配置）
1. 将本仓库推到 GitHub
2. 在 GitHub 仓库的 **Actions** 标签页手动触发 `Build Android APK` workflow
3. 等 ~25 分钟构建完成，从 workflow 的 Artifacts 区域下载 `wuxian-kuaichuan-apk`

### 方式 B：本地 WSL/Ubuntu 构建
```bash
# 在 WSL Ubuntu 里：
sudo apt-get install -y zip unzip openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libffi-dev libssl-dev ccache git
pip install buildozer cython==0.29.36
buildozer android debug
# 产物在 bin/*.apk
```

## 使用说明

1. 两台设备连接**同一 WiFi**
2. 启动本应用（Windows EXE 或 Android APK）
3. 等待几秒，"附近设备"列表中会出现对方
4. 点"选择文件发送"，选好文件后点目标设备即开始传输
5. 接收的文件默认保存在 `Downloads` 目录，可在"设置接收目录"中更改

## 技术原理

| 模块 | 协议 | 端口 |
|------|------|------|
| 设备发现 | UDP 广播 | 53210 |
| 文件传输 | HTTP POST multipart | 随机端口（启动时分配）|

UDP 广播每 2 秒向外宣布自身存在；接收端 5 秒未刷新则视为离线。
文件传输采用 HTTP `multipart/form-data` + 8 MB 分块流式读写，避免整体载入内存。
