from pathlib import Path

from openpyxl import Workbook

from app.services import excel_io

# 模拟常见格式:标题行 + 空行 + 真正的表头 + 数据
ROWS = [
    ["2026年10月员工名单(内部资料)"],
    [],
    ["编号", "名称", "数量"],
    ["1001", "甲", 10],
    ["1002", "乙", 20],
]


def make_xlsx(tmp_path: Path) -> Path:
    p = tmp_path / "t.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    for r in ROWS:
        ws.append(r)
    wb.save(p)
    return p


def test_default_header_is_first_row(tmp_path):
    tables = excel_io.read_tables(make_xlsx(tmp_path))
    assert tables["S"].columns[0] == "2026年10月员工名单(内部资料)"


def test_read_table_with_header_row(tmp_path):
    p = make_xlsx(tmp_path)
    df = excel_io.read_table(p, "S", header_row=3)
    assert list(df.columns) == ["编号", "名称", "数量"]
    assert len(df) == 2
    assert df.iloc[0]["编号"] == "1001"
    assert df.iloc[0]["数量"] == "10"


def test_csv_header_row(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("标题,备注\n编号,数量\n1001,10\n1002,20\n", encoding="utf-8")
    df = excel_io.read_table(p, "CSV", header_row=2)
    assert list(df.columns) == ["编号", "数量"]
    assert len(df) == 2


def test_raw_preview_no_header_assumption(tmp_path):
    pv = excel_io.raw_preview(make_xlsx(tmp_path))
    grid = pv["S"]
    assert grid[0][0] == "2026年10月员工名单(内部资料)"
    assert grid[2][:3] == ["编号", "名称", "数量"]
    assert grid[3][0] == "1001"
