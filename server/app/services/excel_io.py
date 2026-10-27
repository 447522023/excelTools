"""统一读取 xls / xlsx / xlsm / csv 为"全部规范化字符串"的 DataFrame。

规范化规则:空值 -> "";整数浮点 1.0 -> "1";其余 str() 后去首尾空白。
这样 1 与 "1"、1.0 与 1 在对比时视为相同。
"""
import math
import re
from pathlib import Path

import pandas as pd
from charset_normalizer import from_path

SUPPORTED_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv"}

# 纯数字且小数部分全为 0 的字符串,如 "10.0",去掉浮点尾巴变 "10"(保留前导零,如 "00123.0" -> "00123")
_TRAILING_ZERO_FLOAT = re.compile(r"^-?\d+\.0+$")


def normalize_value(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return str(int(v)) if v.is_integer() else str(v)
    s = str(v).strip()
    if _TRAILING_ZERO_FLOAT.fullmatch(s):
        return s.split(".")[0]
    return s


def _dedupe_columns(cols) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for c in cols:
        name = str(c).strip() if str(c).strip() else "未命名"
        if name in seen:
            seen[name] += 1
            out.append(f"{name}.{seen[name]}")
        else:
            seen[name] = 1
            out.append(name)
    return out


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = _dedupe_columns(df.columns)
    elementwise = df.map if hasattr(df, "map") else df.applymap
    return elementwise(normalize_value)


def _detect_encoding(path: Path) -> str | None:
    try:
        best = from_path(str(path)).best()
        return best.encoding if best else None
    except Exception:
        return None


def read_tables(path: Path, header_row: int = 1) -> dict[str, pd.DataFrame]:
    """读取整个文件,返回 {sheet名: DataFrame}。csv 视为单个名为 CSV 的表。

    header_row:表头所在行数(1 起);该行之上 的内容会被忽略,该行作为列名。
    """
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的文件类型:{suffix},仅支持 {', '.join(sorted(SUPPORTED_SUFFIXES))}")
    hr = max(1, header_row) - 1

    if suffix == ".csv":
        encoding = _detect_encoding(path) or "utf-8"
        # sep=None + python 引擎自动嗅探分隔符(逗号/制表符等)
        df = pd.read_csv(
            path, encoding=encoding, sep=None, engine="python",
            dtype=object, keep_default_na=False, header=hr,
        )
        return {"CSV": _normalize_df(df)}

    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    tables = pd.read_excel(path, sheet_name=None, engine=engine, dtype=object, header=hr)
    return {name: _normalize_df(df) for name, df in tables.items()}


def read_table(path: Path, sheet: str, header_row: int = 1) -> pd.DataFrame:
    """只读取指定工作表(表头行可指定),避免其他工作表的解析问题影响本次请求"""
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的文件类型:{suffix},仅支持 {', '.join(sorted(SUPPORTED_SUFFIXES))}")
    hr = max(1, header_row) - 1

    if suffix == ".csv":
        if sheet != "CSV":
            raise ValueError(f"CSV 文件只有一个名为 CSV 的表,没有“{sheet}”")
        encoding = _detect_encoding(path) or "utf-8"
        df = pd.read_csv(
            path, encoding=encoding, sep=None, engine="python",
            dtype=object, keep_default_na=False, header=hr,
        )
        return _normalize_df(df)

    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    try:
        df = pd.read_excel(path, sheet_name=sheet, engine=engine, dtype=object, header=hr)
    except ValueError as e:
        # sheet 名不存在 / 表头行超出范围等
        raise ValueError(str(e)) from e
    return _normalize_df(df)


def raw_preview(path: Path, max_rows: int = 8, max_cols: int = 20) -> dict[str, list[list[str]]]:
    """每个 sheet 前 N 行的原始文本(不做任何表头假设),供前端展示、帮助用户挑表头行"""
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的文件类型:{suffix}")

    def grid(df: pd.DataFrame) -> list[list[str]]:
        rows = []
        for row in df.itertuples(index=False, name=None):
            rows.append([normalize_value(v) for v in list(row)[:max_cols]])
        return rows[:max_rows]

    if suffix == ".csv":
        encoding = _detect_encoding(path) or "utf-8"
        df = pd.read_csv(
            path, encoding=encoding, sep=None, engine="python",
            dtype=object, keep_default_na=False, header=None, nrows=max_rows,
        )
        return {"CSV": grid(df)}

    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    tables = pd.read_excel(path, sheet_name=None, engine=engine, dtype=object, header=None, nrows=max_rows)
    return {name: grid(df) for name, df in tables.items()}
