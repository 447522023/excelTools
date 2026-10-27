"""上传文件的临时存储:磁盘文件 + meta.json 元信息(进程重启后仍可找回)

默认存系统临时目录;可用环境变量 EXCEL_TOOLS_UPLOAD_DIR 指定自定义目录
(例如线上多用户部署时,指向项目目录以避开 /tmp 的权限冲突与系统清理)。
"""
import json
import os
import tempfile
import uuid
from pathlib import Path
from threading import Lock


def _default_root() -> Path:
    env = os.environ.get("EXCEL_TOOLS_UPLOAD_DIR")
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()) / "excel_tools_uploads"


class FileStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else _default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._meta_path = self.root / "meta.json"
        self._lock = Lock()
        self._meta: dict[str, dict] = {}
        if self._meta_path.is_file():
            try:
                self._meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            except Exception:
                self._meta = {}

    def save(self, filename: str, suffix: str, stream) -> str:
        file_id = uuid.uuid4().hex
        path = self.root / f"{file_id}{suffix}"
        with open(path, "wb") as f:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        with self._lock:
            self._meta[file_id] = {"filename": filename, "suffix": suffix}
            self._meta_path.write_text(
                json.dumps(self._meta, ensure_ascii=False), encoding="utf-8"
            )
        return file_id

    def info(self, file_id: str) -> dict | None:
        return self._meta.get(file_id)

    def path(self, file_id: str) -> Path | None:
        info = self._meta.get(file_id)
        if not info:
            return None
        p = self.root / f"{file_id}{info['suffix']}"
        return p if p.is_file() else None
