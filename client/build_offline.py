"""一键打包离线版:构建单文件前端 → PyInstaller 打包 → 产物进 server/downloads。

PyInstaller 不支持交叉编译,每个平台的包必须在对应系统上跑本脚本:
  - Windows:产出 excel-compare-<ver>-windows-x64.exe
  - macOS  :产出 excel-compare-<ver>-macos-<arch>.tar.gz
  - Linux  :产出 excel-compare-<ver>-linux-<arch>.tar.gz
            (需先 pip install "pywebview[gtk]",并装好 GTK / WebKit2GTK 系统库)
没有三台机器时,用 .github/workflows/build-offline.yml 的 CI 矩阵构建。

用法:激活 excel_tools 环境后,在仓库根目录执行
    python client/build_offline.py
产物:server/downloads/(页面"下载离线版"入口读取该目录)+ 同名 .sha256 校验文件
"""
import hashlib
import os
import platform as pf
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SERVER = ROOT / "server"
CLIENT = ROOT / "client"
WEBAPP = CLIENT / "webapp"
DOWNLOADS = SERVER / "downloads"

# 版本号取自 FastAPI 应用定义,保持与 API 一致
sys.path.insert(0, str(SERVER))
from app.main import app as _app  # noqa: E402

VERSION = _app.version

# Windows 下 npm 实际是 npm.cmd,subprocess 按全名找不到,用 which 解析
NPM = shutil.which("npm") or shutil.which("npm.cmd") or "npm"


def run(cmd: list) -> None:
    print(">>", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def target() -> tuple[str, str]:
    plat = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = pf.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        machine, machine
    )
    return plat, arch


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pack_tar(binary: Path, out: Path) -> None:
    # 浏览器直接下载二进制会丢执行位,tar.gz 里保留 +x,解压即可运行
    with tarfile.open(out, "w:gz") as tar:
        info = tar.gettarinfo(str(binary))
        info.mode = 0o755
        info.name = binary.name
        with open(binary, "rb") as f:
            tar.addfile(info, f)


def main() -> None:
    plat, arch = target()

    # 1. 构建单文件前端(JS/CSS 全部内联进 index.html)
    run([NPM, "--prefix", WEB, "run", "build:offline"])

    # 2. 拷贝到 client/webapp(launcher 以 file:// 加载它)
    if WEBAPP.exists():
        shutil.rmtree(WEBAPP)
    shutil.copytree(WEB / "dist-offline", WEBAPP)
    print(f">> 前端单文件已拷贝到 {WEBAPP}")

    # 3. PyInstaller 打包。
    # Anaconda 环境必须把 Library\bin 加进 PATH,否则 _ctypes 等模块依赖的
    # DLL(ffi.dll 等)解析不到,打出的 exe 运行时报 "DLL load failed"
    conda_bin = Path(sys.prefix) / "Library" / "bin"
    if conda_bin.is_dir():
        os.environ["PATH"] = str(conda_bin) + os.pathsep + os.environ.get("PATH", "")
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--name",
            "excel-compare",  # ASCII 名,避免 mac/linux 下的中文名兼容问题
            "--windowed",
            "--onefile",
            f"--paths={SERVER}",
            # 分隔符随系统:Windows 是 ;,macOS/Linux 是 :
            f"--add-data={WEBAPP}{os.pathsep}webapp",
            # 打包各库的配套资源(编码探测频率表 / webview 运行文件)
            "--collect-data=charset_normalizer",
            "--collect-all=webview",
            "--distpath",
            CLIENT / "dist",
            "--workpath",
            CLIENT / "build",
            "--specpath",
            CLIENT,
            CLIENT / "launcher.py",
        ]
    )
    binary = CLIENT / "dist" / ("excel-compare.exe" if plat == "windows" else "excel-compare")

    # 4. 产物入下载目录:Windows 直接放 exe,macOS/Linux 打 tar.gz 保留执行位
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    final = DOWNLOADS / (
        f"excel-compare-{VERSION}-{plat}-{arch}"
        + (".exe" if plat == "windows" else ".tar.gz")
    )
    if plat == "windows":
        shutil.copy2(binary, final)
    else:
        pack_tar(binary, final)

    # 5. 同名 .sha256 校验文件(下载清单接口会忽略)
    digest = sha256_file(final)
    (final.with_name(final.name + ".sha256")).write_text(f"{digest}  {final.name}\n", encoding="ascii")

    print(f"\n打包完成:{final}")
    print(f"校验文件:{final.name}.sha256")
    print('页面"下载离线版"入口读取 server/downloads/,线上部署时随 server/ 一起发布该目录。')


if __name__ == "__main__":
    main()
