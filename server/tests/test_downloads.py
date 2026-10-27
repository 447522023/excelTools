from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers import downloads as downloads_module
from app.routers.downloads import (
    bump_download,
    download_file,
    downloads_dir,
    list_downloads,
)

WINDOWS_PKG = "excel-compare-0.1.0-windows-x64.exe"
LINUX_PKG = "excel-compare-0.1.0-linux-x64.tar.gz"


def make_pkg(root: Path, name: str) -> None:
    (root / name).write_bytes(b"fake-binary")
    (root / f"{name}.sha256").write_text("", encoding="ascii")


def test_list_downloads(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCEL_TOOLS_DOWNLOADS_DIR", str(tmp_path))
    make_pkg(tmp_path, WINDOWS_PKG)
    make_pkg(tmp_path, LINUX_PKG)
    make_pkg(tmp_path, "excel-compare-0.1.0-macos-arm64.tar.gz")

    items = list_downloads()
    # .sha256 附属文件不列出;平台从文件名识别
    assert {i.platform for i in items} == {"windows", "macos", "linux"}
    assert all(i.url == f"/downloads/{i.filename}" for i in items)
    assert all(i.size == len(b"fake-binary") for i in items)
    assert all(i.downloads == 0 for i in items)


def test_list_downloads_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCEL_TOOLS_DOWNLOADS_DIR", str(tmp_path))
    assert list_downloads() == []


def test_dir_env_override_and_autocreate(tmp_path, monkeypatch):
    target = tmp_path / "sub" / "dir"
    monkeypatch.setenv("EXCEL_TOOLS_DOWNLOADS_DIR", str(target))
    assert downloads_dir() == target
    assert target.is_dir()


def test_dir_default_is_server_downloads(monkeypatch):
    # 未设环境变量时,默认指向 server/downloads(app/routers/ 往上三级)
    monkeypatch.delenv("EXCEL_TOOLS_DOWNLOADS_DIR", raising=False)
    assert downloads_dir() == Path(downloads_module.__file__).resolve().parent.parent.parent / "downloads"


def test_download_counts_by_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCEL_TOOLS_DOWNLOADS_DIR", str(tmp_path))
    make_pkg(tmp_path, WINDOWS_PKG)

    res = download_file(WINDOWS_PKG)
    assert res.filename == WINDOWS_PKG
    res = download_file(WINDOWS_PKG)
    assert res.filename == WINDOWS_PKG
    bump_download("windows")

    items = {i.platform: i for i in list_downloads()}
    assert items["windows"].downloads == 3  # 按平台累计,换版本文件名不清零


def test_download_404_cases(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCEL_TOOLS_DOWNLOADS_DIR", str(tmp_path))
    make_pkg(tmp_path, WINDOWS_PKG)
    (tmp_path / ".stats.json").write_text("{}", encoding="utf-8")

    with pytest.raises(HTTPException) as e:
        download_file("../secret.txt")
    assert e.value.status_code == 404

    with pytest.raises(HTTPException):
        download_file("不存在.txt")

    with pytest.raises(HTTPException):
        download_file(".stats.json")  # 统计文件不许下载

    # .sha256 校验文件可下载,且不计入下载量
    res = download_file(f"{WINDOWS_PKG}.sha256")
    assert res.filename == f"{WINDOWS_PKG}.sha256"
    assert list_downloads()[0].downloads == 0
