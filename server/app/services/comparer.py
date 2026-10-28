"""对比引擎:按关键列匹配行,输出"找不同 / 找相同"结果。

匹配规则:关键列的值拼接为元组作为行的 key;重复 key 按出现顺序两两配对
(第 1 个对第 1 个、第 2 个对第 2 个……),多出的落到"仅单侧"。
"""
from dataclasses import dataclass, field

import pandas as pd

STATUS_ONLY_A = "仅表A"
STATUS_ONLY_B = "仅表B"
STATUS_CHANGED = "值不一致"
STATUS_SAME = "一致"

MODE_DIFF = "diff"
MODE_SAME = "same"


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


def compare_tables(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    keys_a: list[str],
    keys_b: list[str],
    mode: str,
    compare_columns: list[str] | None = None,
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
                diffs = [c for c in compare_columns if df_a.at[ia, c] != df_b.at[ib, c]]
                if diffs:
                    summary[STATUS_CHANGED] += 1
                    if mode == MODE_DIFF:
                        row = {"状态": STATUS_CHANGED, **dict(zip(keys_a, key)), "差异列": "、".join(diffs)}
                        for c in compare_columns:
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
