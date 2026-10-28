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


def make_merged_header_xlsx(tmp_path: Path, band_rows: int = 2) -> Path:
    """合并表头:"编号/薪酬/入职日期"纵向合并,"基本信息"横向合并盖住姓名+部门。

    band_rows=2 -> 表头占 2 行;band_rows=3 -> 子表头再纵向合并一行,占 3 行,
    用于模拟两个表表头行数不一致的场景。
    """
    p = tmp_path / "merged.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    ws["A1"] = "编号"
    ws["B1"] = "基本信息"
    ws["B2"] = "姓名"
    ws["C2"] = "部门"
    ws["D1"] = "薪酬(元)"
    ws["E1"] = "入职日期"
    data = [
        ["1001", "张三", "技术部", 8000, "2021-03-15"],
        ["1002", "李四", "技术部", 9500, "2020-07-01"],
    ]
    # 数据固定写在表头带下方(合并后再写会被 openpyxl 静默丢值,故全部显式定位)
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ws.cell(row=band_rows + 1 + i, column=j + 1, value=v)
    ws.merge_cells(start_row=1, start_column=1, end_row=band_rows, end_column=1)
    ws.merge_cells("B1:C1")
    if band_rows == 3:
        ws.merge_cells(start_row=2, start_column=2, end_row=3, end_column=2)
        ws.merge_cells(start_row=2, start_column=3, end_row=3, end_column=3)
    ws.merge_cells(start_row=1, start_column=4, end_row=band_rows, end_column=4)
    ws.merge_cells(start_row=1, start_column=5, end_row=band_rows, end_column=5)
    wb.save(p)
    return p


MERGED_COLUMNS = ["编号", "基本信息-姓名", "基本信息-部门", "薪酬(元)", "入职日期"]


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


def test_merged_header_from_top_row(tmp_path):
    # 选表头带第一行:第二行子表头不泄漏成数据,列名按"上级-下级"拼接
    df = excel_io.read_table(make_merged_header_xlsx(tmp_path), "S", header_row=1)
    assert list(df.columns) == MERGED_COLUMNS
    assert len(df) == 2
    assert df.iloc[0]["编号"] == "1001"  # 不是"姓名"(旧版会把子表头行当数据)


def test_merged_header_from_second_row(tmp_path):
    # 选表头带第二行:向上补齐合并的上级表头,列名与选第一行时一致
    df = excel_io.read_table(make_merged_header_xlsx(tmp_path), "S", header_row=2)
    assert list(df.columns) == MERGED_COLUMNS
    assert len(df) == 2


def test_merged_header_band_height_mismatch(tmp_path):
    # 表A表头占 2 行、表B占 3 行:各自识别表头带,列名仍一一对应
    df_a = excel_io.read_table(make_merged_header_xlsx(tmp_path, band_rows=2), "S")
    df_b = excel_io.read_table(make_merged_header_xlsx(tmp_path, band_rows=3), "S")
    assert list(df_a.columns) == list(df_b.columns) == MERGED_COLUMNS
    assert len(df_a) == len(df_b) == 2


def test_no_unnamed_placeholder(tmp_path):
    # 任何情况下都不应出现 pandas 的 "Unnamed: N" 英文占位列名
    tables = excel_io.read_tables(make_merged_header_xlsx(tmp_path))
    assert not [c for c in tables["S"].columns if c.startswith("Unnamed")]


def test_blank_header_cell_named_by_position(tmp_path):
    # 空表头但有数据的列保留,并按列位置命名(与 CSV 行为一致)
    p = tmp_path / "t.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    ws.append(["编号", None, "数量"])
    ws.append(["1001", "x", 10])
    wb.save(p)
    df = excel_io.read_table(p, "S")
    assert list(df.columns) == ["编号", "未命名2", "数量"]
    assert df.iloc[0]["未命名2"] == "x"


def test_blank_header_cell_named_by_position(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("编号,,数量\n1001,x,10\n", encoding="utf-8")
    df = excel_io.read_table(p, "CSV", header_row=1)
    assert list(df.columns) == ["编号", "未命名2", "数量"]


def test_empty_rows_and_phantom_column_dropped(tmp_path):
    p = tmp_path / "t.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    ws.append(["编号", "名称", None])  # 第三列表头为空
    ws.append(["1001", "甲", None])
    ws.append([None, None, None])  # 整行空行
    ws.append(["1002", "乙", None])
    wb.save(p)
    df = excel_io.read_table(p, "S")
    assert list(df.columns) == ["编号", "名称"]
    assert len(df) == 2


def test_header_row_out_of_range(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        excel_io.read_table(make_xlsx(tmp_path), "S", header_row=99)


def test_csv_header_row(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("标题,备注\n编号,数量\n1001,10\n1002,20\n", encoding="utf-8")
    df = excel_io.read_table(p, "CSV", header_row=2)
    assert list(df.columns) == ["编号", "数量"]
    assert len(df) == 2


def test_csv_gbk_small_file(tmp_path):
    # 只有几个汉字的 GBK 小文件,探测器会给 0 置信度的错误猜测,应兜底到 GBK
    p = tmp_path / "t.csv"
    p.write_bytes("编号,数量\n1001,10\n".encode("gbk"))
    df = excel_io.read_table(p, "CSV")
    assert list(df.columns) == ["编号", "数量"]
    assert df.iloc[0]["数量"] == "10"


def test_csv_utf8_bom(tmp_path):
    p = tmp_path / "t.csv"
    p.write_bytes("编号,数量\n1001,10\n".encode("utf-8-sig"))
    df = excel_io.read_table(p, "CSV")
    assert list(df.columns) == ["编号", "数量"]  # 首列名不带 BOM 前缀


def test_raw_preview_no_header_assumption(tmp_path):
    pv = excel_io.raw_preview(make_xlsx(tmp_path))
    grid = pv["S"]
    assert grid[0][0] == "2026年10月员工名单(内部资料)"
    assert grid[2][:3] == ["编号", "名称", "数量"]
    assert grid[3][0] == "1001"
