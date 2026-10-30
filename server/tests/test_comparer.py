import pandas as pd

from app.services import excel_io
from app.services.comparer import (
    MODE_DIFF,
    MODE_SAME,
    STATUS_CHANGED,
    STATUS_ONLY_A,
    STATUS_ONLY_B,
    STATUS_SAME,
    compare_grids,
    compare_tables,
)


def make(rows: dict[str, list[str]]) -> pd.DataFrame:
    # 走与真实读取相同的规范化,保证测试覆盖完整数据管线
    return excel_io._normalize_df(pd.DataFrame(rows))


DF_A = make({"编号": ["1", "2", "3"], "名称": ["甲", "乙", "丙"], "数量": ["10", "20", "30"]})
DF_B = make({"编号": ["1", "2", "4"], "名称": ["甲", "乙改", "丁"], "数量": ["10", "25", "40"]})


def test_diff_mode():
    out = compare_tables(DF_A, DF_B, ["编号"], ["编号"], MODE_DIFF)
    statuses = [r["状态"] for r in out.rows]
    # 编号1 两表一致(不出现),编号2 值不一致,编号3 仅表A,编号4 仅表B
    assert statuses.count(STATUS_CHANGED) == 1
    assert statuses.count(STATUS_ONLY_A) == 1
    assert statuses.count(STATUS_ONLY_B) == 1
    changed = next(r for r in out.rows if r["状态"] == STATUS_CHANGED)
    assert changed["差异列"] == "名称、数量"
    assert changed["名称（A）"] == "乙" and changed["名称（B）"] == "乙改"
    assert out.summary[STATUS_SAME] == 1
    assert out.summary["表A总行数"] == 3 and out.summary["表B总行数"] == 3


def test_same_mode():
    out = compare_tables(DF_A, DF_B, ["编号"], ["编号"], MODE_SAME)
    assert len(out.rows) == 1
    assert out.rows[0]["状态"] == STATUS_SAME
    assert out.rows[0]["编号"] == "1"
    # 编号2 值不一致(1 行);编号3/4 是单侧缺失,不算"值不一致"
    assert out.summary[STATUS_CHANGED] == 1


def test_different_key_names():
    df_b = make({"ID": ["1", "2"], "名称": ["甲", "乙"]})
    out = compare_tables(DF_A, df_b, ["编号"], ["ID"], MODE_SAME)
    assert out.summary[STATUS_SAME] == 2


def test_duplicate_keys_pair_in_order():
    df_a = make({"编号": ["1", "1", "2"], "名称": ["甲", "甲v2", "乙"]})
    df_b = make({"编号": ["1", "2"], "名称": ["甲", "乙"]})
    out = compare_tables(df_a, df_b, ["编号"], ["编号"], MODE_DIFF)
    assert out.summary[STATUS_ONLY_A] == 1  # 第二个"1"配不上
    assert out.summary[STATUS_SAME] == 2


def test_numeric_normalization():
    df_a = make({"编号": ["1"], "数量": ["10"]})
    df_b = make({"编号": ["1"], "数量": ["10.0"]})
    out = compare_tables(df_a, df_b, ["编号"], ["编号"], MODE_SAME)
    # "10" 与 "10.0" 规范化后都是 "10",应视为一致
    assert out.summary[STATUS_SAME] == 1


# -------- 公式层对比(issue #1:公式变了但计算值相同) --------

_COLS = {"编号": 0, "金额": 4}


def _formula_kwargs(fa, fb):
    origins = [1]
    return dict(
        compare_formulas=True,
        formulas_a=fa, row_origins_a=origins, col_origins_a=dict(_COLS),
        formulas_b=fb, row_origins_b=origins, col_origins_b=dict(_COLS),
    )


def test_formula_only_change_detected_when_enabled():
    # 值同为 120000,公式 =C2*D2 改成 =D2*C2:默认判"一致",开启公式对比后计为差异
    df_a = make({"编号": ["1"], "金额": ["120000"]})
    df_b = make({"编号": ["1"], "金额": ["120000"]})
    out = compare_tables(df_a, df_b, ["编号"], ["编号"], MODE_DIFF)
    assert out.summary[STATUS_SAME] == 1  # 默认只比值(与 v0.1.1 行为一致)

    out = compare_tables(
        df_a, df_b, ["编号"], ["编号"], MODE_DIFF,
        **_formula_kwargs({(1, 4): "=C2*D2"}, {(1, 4): "=D2*C2"}),
    )
    assert out.summary[STATUS_CHANGED] == 1
    row = out.rows[0]
    assert row["差异列"] == "金额[公式]"
    # 值相同的情况下,（A）/（B）直接展示新旧公式,差异一目了然
    assert row["金额（A）"] == "=C2*D2" and row["金额（B）"] == "=D2*C2"


def test_same_formula_not_a_diff():
    df_a = make({"编号": ["1"], "金额": ["120000"]})
    df_b = make({"编号": ["1"], "金额": ["120000"]})
    out = compare_tables(
        df_a, df_b, ["编号"], ["编号"], MODE_DIFF,
        **_formula_kwargs({(1, 4): "=C2*D2"}, {(1, 4): "=C2*D2"}),
    )
    assert out.summary[STATUS_SAME] == 1


def test_formula_added_or_removed_counts_as_diff():
    # 一侧有公式、另一侧是普通值:也算公式差异
    df_a = make({"编号": ["1"], "金额": ["120000"]})
    df_b = make({"编号": ["1"], "金额": ["120000"]})
    out = compare_tables(
        df_a, df_b, ["编号"], ["编号"], MODE_DIFF,
        **_formula_kwargs({(1, 4): "=C2*D2"}, {}),
    )
    assert out.rows[0]["差异列"] == "金额[公式]"
    assert out.rows[0]["金额（B）"] == "(无公式)"


def test_same_mode_excludes_formula_only_diff():
    # 找相同 + 开启公式对比:公式不同的行不算"一致",不进入结果
    df_a = make({"编号": ["1"], "金额": ["120000"]})
    df_b = make({"编号": ["1"], "金额": ["120000"]})
    out = compare_tables(
        df_a, df_b, ["编号"], ["编号"], MODE_SAME,
        **_formula_kwargs({(1, 4): "=C2*D2"}, {(1, 4): "=D2*C2"}),
    )
    assert out.rows == []
    assert out.summary[STATUS_CHANGED] == 1 and out.summary[STATUS_SAME] == 0


def test_unmatched_columns_reported():
    # 只在一侧存在的列应如实报告,而不是悄悄从结果里消失
    df_b = make({"编号": ["1", "2", "4"], "名称": ["甲", "乙改", "丁"], "数量": ["10", "25", "40"], "备注": ["a", "b", "c"]})
    out = compare_tables(DF_A, df_b, ["编号"], ["编号"], MODE_DIFF)
    assert out.unmatched_columns == {"仅表A的列": [], "仅表B的列": ["备注"]}
    assert "备注" not in out.columns


def test_export_lists_unmatched_columns():
    import io

    from openpyxl import load_workbook

    from app.services.exporter import to_xlsx

    df_b = make({"编号": ["1"], "名称": ["甲"], "数量": ["10"], "备注": ["x"]})
    df_a = make({"编号": ["1"], "名称": ["甲"], "数量": ["10"]})
    out = compare_tables(df_a, df_b, ["编号"], ["编号"], MODE_SAME)
    wb = load_workbook(io.BytesIO(to_xlsx(out)))
    ws = wb["未对比的列"]
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows == [["所属", "列名"], ["仅表B的列", "备注"]]


# ---------------- 坐标对比模式(compare_grids) ----------------

GRID_A = [["编号", "姓名"], ["1", "甲"], ["2", "乙"], ["3", "丙"]]


def test_cell_mode_basic_change():
    grid_b = [["编号", "姓名"], ["1", "甲"], ["2", "乙改"], ["3", "丙"]]
    out = compare_grids(GRID_A, grid_b)
    assert out.summary["值不一致"] == 1
    assert out.summary["差异格"] == 1
    assert out.summary["仅表A"] == 0 and out.summary["仅表B"] == 0
    row = out.rows[0]
    assert row["差异明细"] == "B3: 乙 → 乙改"  # Excel 坐标:第 3 行 B 列
    assert row["行号(A)"] == "3" and row["行号(B)"] == "3"


def test_cell_mode_formula_only_change():
    # 值相同、公式文本不同:必须报出来(公式差异格)
    grid_b = [r[:] for r in GRID_A]
    fa = {(1, 1): "=A2+1"}
    fb = {(1, 1): "=1+A2"}
    out = compare_grids(GRID_A, grid_b, fa, fb)
    assert out.summary["差异格"] == 1
    assert out.summary["公式差异格"] == 1
    assert "[公式]" in out.rows[0]["差异明细"]


def test_cell_mode_tail_row_added():
    grid_b = GRID_A + [["4", "丁"]]
    out = compare_grids(GRID_A, grid_b)
    assert out.summary["值不一致"] == 0
    assert out.summary["仅表B"] == 1 and out.summary["仅表A"] == 0
    only_b = next(r for r in out.rows if r["状态"] == "仅表B")
    assert only_b["行号(A)"] == "—" and only_b["行号(B)"] == "5"
    assert "丁" in only_b["差异明细"]


def test_cell_mode_tail_row_removed():
    out = compare_grids(GRID_A, GRID_A[:3])
    assert out.summary["仅表A"] == 1 and out.summary["值不一致"] == 0
    only_a = next(r for r in out.rows if r["状态"] == "仅表A")
    assert only_a["行号(A)"] == "4" and only_a["行号(B)"] == "—"


def test_cell_mode_middle_delete_is_coordinate_shift():
    # 坐标范式固有特性:中部删行会让后续行整体错位(2 行值不一致),不是 bug;
    # 业务表遇到这种场景应使用关键列模式
    grid_b = [["编号", "姓名"], ["1", "甲"], ["3", "丙"]]
    out = compare_grids(GRID_A, grid_b)
    assert out.summary["值不一致"] == 1  # "2,乙" 对上了 "3,丙"
    assert out.summary["差异格"] == 2
    assert out.summary["仅表A"] == 1  # 末行 "3,丙" 没有对手


def test_cell_mode_empty_side():
    out = compare_grids(GRID_A, [])
    assert out.summary["仅表A"] == 4  # 含表头行在内的所有行
    assert out.summary["值不一致"] == 0


def test_cell_mode_blank_rows_skipped():
    grid_a = [["a"], [""], ["b"]]
    grid_b = [["a"], [""], ["b"]]
    out = compare_grids(grid_a, grid_b)
    assert out.summary["差异格"] == 0
    assert not out.rows
