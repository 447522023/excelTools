"""FastAPI 入口:API + 托管前端静态资源(web/dist 或打包后的 server/static)"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import compare, downloads, files

app = FastAPI(title="表格对比工具", version="0.2.0")

# 开发期 web 跑在 vite(5173),通过 proxy 转发 /api;生产/离线模式同源,不需要 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files.router)
app.include_router(compare.router)
app.include_router(downloads.router)
# 安装包文件本体(/downloads/<filename>),由 downloads 路由提供并统计下载量
app.include_router(downloads.file_router)


def _static_dir() -> Path | None:
    candidates = [
        Path(os.environ["EXCEL_TOOLS_STATIC_DIR"]) if os.environ.get("EXCEL_TOOLS_STATIC_DIR") else None,
        Path(__file__).resolve().parent.parent / "static",            # server/static(离线打包)
        Path(__file__).resolve().parent.parent.parent / "web" / "dist",  # 仓库 web/dist(开发联调)
    ]
    for c in candidates:
        if c and (c / "index.html").is_file():
            return c
    return None


_static = _static_dir()
if _static:
    app.mount("/", StaticFiles(directory=_static, html=True), name="web")
