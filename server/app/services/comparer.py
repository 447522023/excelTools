"""对比引擎。

两种范式:
- 关键列模式(找不同/找相同):按关键列的值匹配行,适合业务表(工号/单号对齐),
  天然免疫插行、删行、行序打乱;
- 坐标模式(坐标对比):按单元格坐标逐格比较值与公式,适合无关键列的表
  (值班表/矩阵),与"专业 diff 工具"语义一致,行级聚合输出。

匹配规则(关键列模式):关键列的值拼接为元组作为行的 key;重复 key 按出现顺序
两两配对(第 1 个对第 1 个、第 2 个对第 2 个……),多出的落到"仅单侧"。
"""
from dataclasses import dataclass, field

import pandas as pd
from openpyxl.utils import get_column_letter

STATUS_ONLY_A = "仅表A"
STATUS_ONLY_B = "仅表B"
STATUS_CHANGED = "值不一致"
STATUS_SAME = "一致"

MODE_DIFF = "diff"
MODE_SAME = "same"
MODE_CELL = "cell"


@dataclass
class CompareOutcome:
    columns: list[str]
    rows: list[dict]
    summary: dict[str, int]
    # 名字对不上、只在一侧存在的列(无法参与对比),如实报告而不是悄悄丢弃
    unmatched_columns: dict[str, list[str]] = field(default_factory=dict)


def _group_rows(df: pd.DataFrame, key_cols: list[str]) -> dict[tuple, list[int]]:
    groups: dict[tuple, list[int]] = {}
    for idx, key in enumerate(zip(*(df[c].tolist() for c in key_cols))):
        groups.setdefault(tuple(key), []).append(idx)
    return groups


def _formula_at(
    formulas: dict | None,
    row_origins: list[int] | None,
    col_origins: dict[str, int] | None,
    i: int,
    col: str,
) -> str | None:
    """第 i 行数据在 col 列的公式文本(经原始坐标映射;无公式层信息时返回 None)"""
    if not formulas or not row_origins or not col_origins or col not in col_origins:
        return None
    return formulas.get((row_origins[i], col_origins[col]))


def compare_tables(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    keys_a: list[str],
    keys_b: list[str],
    mode: str,
    compare_columns: list[str] | None = None,
    *,
    compare_formulas: bool = False,
    formulas_a: dict | None = None,
    row_origins_a: list[int] | None = None,
    col_origins_a: dict[str, int] | None = None,
    formulas_b: dict | None = None,
    row_origins_b: list[int] | None = None,
    col_origins_b: dict[str, int] | None = None,
) -> CompareOutcome:
    shared = [c for c in df_a.columns if c in df_b.columns]
    unmatched_columns = {
        "仅表A的列": [c for c in df_a.columns if c not in df_b.columns],
        "仅表B的列": [c for c in df_b.columns if c not in df_a.columns],
    }
    if compare_columns is None:
        compare_columns = [c for c in shared if c not in keys_a]
    else:
        compare_columns = [c for c in compare_columns if c in shared and c not in keys_a]

    columns = ["状态", *keys_a]
    if mode == MODE_DIFF:
        columns += ["差异列"]
        columns += [f"{c}（A）" for c in compare_columns]
        columns += [f"{c}（B）" for c in compare_columns]
    else:
        columns += compare_columns

    groups_a = _group_rows(df_a, keys_a)
    groups_b = _group_rows(df_b, keys_b)

    summary = {
        "表A总行数": len(df_a),
        "表B总行数": len(df_b),
        STATUS_SAME: 0,
        STATUS_CHANGED: 0,
        STATUS_ONLY_A: 0,
        STATUS_ONLY_B: 0,
    }
    rows: list[dict] = []

    # 先按表A的顺序,再补表B独有的 key,保证结果顺序稳定
    ordered_keys = list(dict.fromkeys([*groups_a.keys(), *groups_b.keys()]))
    for key in ordered_keys:
        list_a = groups_a.get(key, [])
        list_b = groups_b.get(key, [])
        for i in range(max(len(list_a), len(list_b))):
            has_a, has_b = i < len(list_a), i < len(list_b)
            if has_a and has_b:
                ia, ib = list_a[i], list_b[i]
                diffs: list[str] = []
                formula_changed: dict[str, tuple[str, str]] = {}
                for c in compare_columns:
                    va, vb = df_a.at[ia, c], df_b.at[ib, c]
                    if va != vb:
                        diffs.append(c)
                    elif compare_formulas:
                        # 值相同再查公式层:公式文本不同也算差异,差异列标记 [公式]
                        fa_t = _formula_at(formulas_a, row_origins_a, col_origins_a, ia, c)
                        fb_t = _formula_at(formulas_b, row_origins_b, col_origins_b, ib, c)
                        if (fa_t or None) != (fb_t or None):
                            diffs.append(f"{c}[公式]")
                            formula_changed[c] = (fa_t or "(无公式)", fb_t or "(无公式)")
                if diffs:
                    summary[STATUS_CHANGED] += 1
                    if mode == MODE_DIFF:
                        row = {"状态": STATUS_CHANGED, **dict(zip(keys_a, key)), "差异列": "、".join(diffs)}
                        for c in compare_columns:
                            # 公式变动(值相同)的列直接展示新旧公式,差异一目了然
                            if c in formula_changed:
                                row[f"{c}（A）"] = formula_changed[c][0]
                                row[f"{c}（B）"] = formula_changed[c][1]
                            else:
                                row[f"{c}（A）"] = df_a.at[ia, c]
                                row[f"{c}（B）"] = df_b.at[ib, c]
                        rows.append(row)
                else:
                    summary[STATUS_SAME] += 1
                    if mode == MODE_SAME:
                        row = {"状态": STATUS_SAME, **dict(zip(keys_a, key))}
                        row.update({c: df_a.at[ia, c] for c in compare_columns})
                        rows.append(row)
            elif has_a:
                summary[STATUS_ONLY_A] += 1
                if mode == MODE_DIFF:
                    row = {"状态": STATUS_ONLY_A, **dict(zip(keys_a, key)), "差异列": ""}
                    for c in compare_columns:
                        row[f"{c}（A）"] = df_a.at[list_a[i], c]
                        row[f"{c}（B）"] = "—"
                    rows.append(row)
            else:
                summary[STATUS_ONLY_B] += 1
                if mode == MODE_DIFF:
                    row = {"状态": STATUS_ONLY_B, **dict(zip(keys_a, key)), "差异列": ""}
                    for c in compare_columns:
                        row[f"{c}（A）"] = "—"
                        row[f"{c}（B）"] = df_b.at[list_b[i], c]
                    rows.append(row)

    return CompareOutcome(
        columns=columns, rows=rows, summary=summary, unmatched_columns=unmatched_columns
    )


# ---------------- 坐标模式:按单元格坐标逐格比较(值 + 公式) ----------------


def _display(v: str | None) -> str:
    return "(空)" if v is None or v == "" else v


def _row_digest(values: list[str], side: str) -> str:
    """单侧独有行的内容摘要:非空值取前若干个,避免整行刷屏"""
    picked = [v for v in values if v != ""][:8]
    text = "、".join(picked)
    if len(text) > 100:
        text = text[:100] + "…"
    return f"整行仅{side}存在" + (f":{text}" if text else "")


def compare_grids(
    grid_a: list[list[str]],
    grid_b: list[list[str]],
    formulas_a: dict[tuple[int, int], str] | None = None,
    formulas_b: dict[tuple[int, int], str] | None = None,
    mode: str = MODE_DIFF,
) -> CompareOutcome:
    """坐标对比:第 i 行对第 i 行、第 j 列对第 j 列,输出行级聚合差异。

    - 值不一致的格:明细为 "B6: 旧 → 新";
    - 仅公式文本变化(值相同):明细为 "B1: [公式] =A1+1 → =1+A1";
    - 一侧多出的行:按行报"仅表A/仅表B",附内容摘要。
    """
    formulas_a = formulas_a or {}
    formulas_b = formulas_b or {}
    columns = ["状态", "行号(A)", "行号(B)", "差异格数", "差异明细"]
    summary = {
        "表A总行数": len(grid_a),
        "表B总行数": len(grid_b),
        STATUS_CHANGED: 0,
        STATUS_ONLY_A: 0,
        STATUS_ONLY_B: 0,
        "差异格": 0,
        "公式差异格": 0,
    }
    rows: list[dict] = []

    common = min(len(grid_a), len(grid_b))
    for r in range(common):
        row_a, row_b = grid_a[r], grid_b[r]
        blank_a = all(v == "" for v in row_a)
        blank_b = all(v == "" for v in row_b)
        if blank_a and blank_b:
            continue
        parts: list[str] = []
        for c in range(max(len(row_a), len(row_b))):
            va = row_a[c] if c < len(row_a) else ""
            vb = row_b[c] if c < len(row_b) else ""
            fa = formulas_a.get((r, c))
            fb = formulas_b.get((r, c))
            value_diff = va != vb
            formula_diff = (fa or None) != (fb or None)
            if not value_diff and not formula_diff:
                continue
            addr = f"{get_column_letter(c + 1)}{r + 1}"
            summary["差异格"] += 1
            if formula_diff:
                summary["公式差异格"] += 1
            if value_diff and formula_diff:
                parts.append(f"{addr}: {_display(va)} → {_display(vb)}（公式 {_display(fa)} → {_display(fb)}）")
            elif value_diff:
                parts.append(f"{addr}: {_display(va)} → {_display(vb)}")
            else:
                parts.append(f"{addr}: [公式] {_display(fa)} → {_display(fb)}")
        if parts:
            summary[STATUS_CHANGED] += 1
            if mode == MODE_DIFF:
                rows.append(
                    {
                        "状态": STATUS_CHANGED,
                        "行号(A)": str(r + 1),
                        "行号(B)": str(r + 1),
                        "差异格数": str(len(parts)),
                        "差异明细": "；".join(parts),
                    }
                )
        elif mode == MODE_SAME:
            rows.append(
                {"状态": STATUS_SAME, "行号(A)": str(r + 1), "行号(B)": str(r + 1),
                 "差异格数": "0", "差异明细": ""}
            )

    for r in range(common, len(grid_a)):
        if all(v == "" for v in grid_a[r]):
            continue
        summary[STATUS_ONLY_A] += 1
        if mode == MODE_DIFF:
            rows.append(
                {"状态": STATUS_ONLY_A, "行号(A)": str(r + 1), "行号(B)": "—", "差异格数": "",
                 "差异明细": _row_digest(grid_a[r], "表A")}
            )
    for r in range(common, len(grid_b)):
        if all(v == "" for v in grid_b[r]):
            continue
        summary[STATUS_ONLY_B] += 1
        if mode == MODE_DIFF:
            rows.append(
                {"状态": STATUS_ONLY_B, "行号(A)": "—", "行号(B)": str(r + 1), "差异格数": "",
                 "差异明细": _row_digest(grid_b[r], "表B")}
            )

    return CompareOutcome(columns=columns, rows=rows, summary=summary)
