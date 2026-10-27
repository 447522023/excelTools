"""离线客户端入口(无 HTTP 服务):pywebview 桌面窗口 + JS 桥接直调 Python。

页面(window.pywebview.api.*)与 Python 之间通过 pywebview 消息通道通信,
全程不创建任何 socket,更不监听端口;前端为单文件 index.html,以 file:// 加载。
"""
import base64
import sys
from pathlib import Path

# 源码运行时把 server/ 加入模块路径(打包后已在包内,跳过)
ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
if SERVER.is_dir() and str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app.services import ops  # noqa: E402
from app.storage import FileStore  # noqa: E402

import webview  # noqa: E402


def _webapp_index() -> Path:
    """前端单文件页面:打包后在 _MEIPASS/webapp,源码运行在 web/dist-offline"""
    if getattr(sys, "_MEIPASS", None):
        path = Path(sys._MEIPASS) / "webapp" / "index.html"
    else:
        path = ROOT / "web" / "dist-offline" / "index.html"
    if not path.is_file():
        raise SystemExit(f"未找到前端页面:{path}\n请先在 web/ 执行 npm run build:offline")
    return path


class Bridge:
    """暴露给前端 window.pywebview.api 的方法,出错时返回 {"error": 中文提示}"""

    def __init__(self):
        self.store = FileStore()

    def upload(self, filename: str, data_b64: str) -> dict:
        try:
            return ops.upload_bytes(self.store, filename, base64.b64decode(data_b64))
        except ops.OpError as e:
            return {"error": e.message}

    def parse_sheet(self, file_id: str, sheet: str, header_row: int = 1) -> dict:
        try:
            return ops.parse_sheet(self.store, file_id, sheet, header_row)
        except ops.OpError as e:
            return {"error": e.message}

    def compare(self, payload: dict) -> dict:
        try:
            return ops.compare_page(self.store, payload)
        except ops.OpError as e:
            return {"error": e.message}

    def export(self, payload: dict) -> dict:
        try:
            filename, data = ops.export_result(self.store, payload)
        except ops.OpError as e:
            return {"error": e.message}
        target = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG, save_filename=filename
        )
        if not target:
            return {"cancelled": True}
        if isinstance(target, (tuple, list)):
            target = target[0]
        with open(target, "wb") as f:
            f.write(data)
        return {"saved": str(target)}


def main() -> None:
    webview.create_window(
        "表格对比工具",
        _webapp_index().as_uri(),
        js_api=Bridge(),
        width=1280,
        height=840,
        min_size=(980, 640),
    )
    webview.start()  # 阻塞直到窗口关闭


if __name__ == "__main__":
    main()
