"""离线版安装包:清单接口 + 文件下载(带下载量统计)。

包文件由 client/build_offline.py 在各平台构建后放入下载目录,命名约定:
    excel-compare-<version>-<platform>-<arch>.exe|.tar.gz
目录默认为 server/downloads,可用环境变量 EXCEL_TOOLS_DOWNLOADS_DIR 指定。
下载量按平台累计在 <目录>/.stats.json,版本升级不清零。
"""
import json
import os
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas import DownloadInfo

router = APIRouter(prefix="/api", tags=["downloads"])
# 文件本体挂在 /downloads(不带 /api 前缀,前端直链下载)
file_router = APIRouter(tags=["downloads"])

PLATFORMS = ("windows", "macos", "linux")
STATS_FILE = ".stats.json"

_stats_lock = Lock()


def downloads_dir() -> Path:
    env = os.environ.get("EXCEL_TOOLS_DOWNLOADS_DIR")
    root = Path(env) if env else Path(__file__).resolve().parent.parent.parent / "downloads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_stats(root: Path) -> dict[str, int]:
    try:
        return json.loads((root / STATS_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def bump_download(platform: str) -> int:
    """某平台下载量 +1 并落盘,返回累计值"""
    root = downloads_dir()
    with _stats_lock:
        stats = _read_stats(root)
        stats[platform] = stats.get(platform, 0) + 1
        (root / STATS_FILE).write_text(json.dumps(stats), encoding="utf-8")
        return stats[platform]


@router.get("/downloads", response_model=list[DownloadInfo])
def list_downloads() -> list[DownloadInfo]:
    root = downloads_dir()
    stats = _read_stats(root)
    items: list[DownloadInfo] = []
    for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file() or p.name.endswith(".sha256"):
            continue
        matched = [pf for pf in PLATFORMS if f"-{pf}-" in p.name]
        if not matched:
            continue  # 只列安装包,忽略 .sha256 校验文件等附属产物
        st = p.stat()
        items.append(
            DownloadInfo(
                platform=matched[0],
                filename=p.name,
                size=st.st_size,
                mtime=int(st.st_mtime),
                url=f"/downloads/{p.name}",
                downloads=stats.get(matched[0], 0),
            )
        )
    return items


@file_router.get("/downloads/{filename}")
def download_file(filename: str) -> FileResponse:
    root = downloads_dir()
    path = (root / filename).resolve()
    # 只允许下载目录内的安装包与 .sha256 校验文件(拒绝路径穿越与 .stats.json)
    if root.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    is_sum = path.name.endswith(".sha256")
    # 校验文件名同样含平台字样(如 xxx-windows-x64.exe.sha256),先排除再判包
    is_pkg = not is_sum and any(f"-{pf}-" in path.name for pf in PLATFORMS)
    if not is_pkg and not is_sum:
        raise HTTPException(status_code=404, detail="文件不存在")
    if is_pkg:
        platform = next(pf for pf in PLATFORMS if f"-{pf}-" in path.name)
        bump_download(platform)
    return FileResponse(path, filename=path.name)
