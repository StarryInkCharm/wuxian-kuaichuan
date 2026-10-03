"""一键构建 Windows EXE - 包装 PyInstaller，简化命令行"""
import subprocess
import sys
import shutil
import os


def main():
    print("=" * 60)
    print("构建 Windows EXE - 无线快传")
    print("=" * 60)

    # 清理旧产物
    for d in ('build', 'dist'):
        if os.path.exists(d):
            print(f"清理 {d}/ ...")
            shutil.rmtree(d, ignore_errors=True)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean', '-y',
        '--noconfirm',
        '--log-level', 'WARN',
        '--distpath', 'dist',
        '--workpath', 'build',
        'build_exe.spec',
    ]
    print("执行:", ' '.join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"构建失败 (exit={rc})")
        sys.exit(rc)
    exe_path = os.path.join('dist', '无线快传', '无线快传.exe')
    if not os.path.exists(exe_path):
        # PyInstaller 单文件模式
        exe_path = os.path.join('dist', '无线快传.exe')
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"\n✓ 构建成功: {os.path.abspath(exe_path)}  ({size_mb:.1f} MB)")
    else:
        print("\n构建产物未找到，请检查 dist/ 目录")
        sys.exit(1)


if __name__ == "__main__":
    main()
