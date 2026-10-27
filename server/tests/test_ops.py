import base64
from pathlib import Path

import pytest

from app.services import ops
from app.storage import FileStore

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "test_files"


@pytest.fixture()
def store(tmp_path):
    return FileStore(root=tmp_path / "uploads")


def _read(p: str) -> bytes:
    return (DATA_DIR / p).read_bytes()


def test_full_flow_upload_parse_compare_export(store):
    up_a = ops.upload_bytes(store, "a.xlsx", _read("员工名单A_10月.xlsx"))
    up_b = ops.upload_bytes(store, "b.csv", _read("员工名单B_10月.csv"))  # GBK
    assert up_b["sheets"][0]["columns"][0] == "编号"

    parsed = ops.parse_sheet(store, up_b["file_id"], "CSV", header_row=1)
    assert parsed["row_count"] == 11

    payload = {
        "left_file_id": up_a["file_id"], "left_sheet": "10月名单", "left_header_row": 1,
        "right_file_id": up_b["file_id"], "right_sheet": "CSV", "right_header_row": 1,
        "left_keys": ["编号"], "right_keys": ["编号"], "mode": "diff",
        "compare_columns": None, "page": 1, "page_size": 0,
    }
    res = ops.compare_page(store, payload)
    assert res["total"] == 7 and len(res["rows"]) == 7
    assert res["mode"] == "diff"

    filename, data = ops.export_result(store, {**payload, "format": "xlsx"})
    assert filename.endswith(".xlsx") and len(data) > 1000


def test_upload_rejects_bad_type(store):
    with pytest.raises(ops.OpError) as e:
        ops.upload_bytes(store, "x.txt", b"hello")
    assert "不支持的文件类型" in e.value.message


def test_compare_key_mismatch(store):
    up_a = ops.upload_bytes(store, "a.xlsx", _read("员工名单A_10月.xlsx"))
    up_b = ops.upload_bytes(store, "b.csv", _read("员工名单B_10月.csv"))
    payload = {
        "left_file_id": up_a["file_id"], "left_sheet": "10月名单", "left_header_row": 1,
        "right_file_id": up_b["file_id"], "right_sheet": "CSV", "right_header_row": 1,
        "left_keys": ["编号", "姓名"], "right_keys": ["编号"], "mode": "diff",
        "compare_columns": None, "page": 1, "page_size": 0,
    }
    with pytest.raises(ops.OpError) as e:
        ops.compare_page(store, payload)
    assert "数量不一致" in e.value.message


def test_base64_roundtrip_matches_bridge_usage(store):
    """离线客户端桥接层用 base64 传文件,验证该路径等价"""
    raw = _read("员工名单D_带标题行.xlsx")
    up = ops.upload_bytes(store, "d.xlsx", base64.b64decode(base64.b64encode(raw)))
    parsed = ops.parse_sheet(store, up["file_id"], "名单", header_row=3)
    assert parsed["columns"] == ["编号", "姓名", "部门", "基本工资", "入职日期"]
    assert parsed["row_count"] == 6
