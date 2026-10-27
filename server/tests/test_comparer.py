import pandas as pd

from app.services import excel_io
from app.services.comparer import (
    MODE_DIFF,
    MODE_SAME,
    STATUS_CHANGED,
    STATUS_ONLY_A,
    STATUS_ONLY_B,
    STATUS_SAME,
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
