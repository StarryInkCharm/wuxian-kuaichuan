# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec - 将 Python+Kivy 应用打包为 Windows EXE
用法: pyinstaller --clean -y build_exe.spec
"""
import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT, Tree

import kivy
import kivy_deps

project_root = os.path.abspath('.')


# 收集 Kivy 在 Windows 上的 SDL2/GLEW/ANGLE 依赖 dll
def _collect_kivy_deps_dlls():
    bins = []
    for dep_name in ('sdl2', 'glew', 'angle'):
        try:
            pkg_dir = os.path.dirname(__import__(f'kivy_deps.{dep_name}').__file__)
        except Exception:
            continue
        if os.path.isdir(pkg_dir):
            for f in os.listdir(pkg_dir):
                if f.lower().endswith('.dll'):
                    bins.append((os.path.join(pkg_dir, f), '.'))
    return bins


binaries = _collect_kivy_deps_dlls()

datas = [
    (os.path.join(os.path.dirname(kivy.__file__), 'data'), 'kivy/data'),
]

# PyInstaller 会通过 import 分析自动收集 main.py 用到的所有模块
a = Analysis(
    ['main.py'],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'core.discovery', 'core.transfer', 'core.utils', 'core',
        'aiohttp', 'aiohttp.web', 'aiohttp.web_app',
        'PIL', 'PIL.Image',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'test', 'distutils'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='无线快传',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI 应用
    disable_windowed_traceback=False,
    target_arch='x86_64',
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    name='无线快传',
    strip=False,
    upx=False,
    upx_exclude=[],
)
