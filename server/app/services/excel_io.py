"""统一读取 xls / xlsx / xlsm / csv 为"全部规范化字符串"的 DataFrame。

规范化规则:空值 -> "";整数浮点 1.0 -> "1";其余 str() 后去首尾空白。
这样 1 与 "1"、1.0 与 1 在对比时视为相同。

合并表头支持:所选表头行落在合并区域内时,自动识别整条"表头带"(可跨多行):
- 纵向合并(如"编号"占 2 行):取合并单元格的值作为列名;
- 横向合并(如"基本信息"盖住 2 列):值铺到覆盖的每一列,再与下一级的子表头拼接;
- 多行表头按"上级-下级"拼接成唯一列名(如"基本信息-姓名");
- 数据一律从表头带最后一行之下开始,两表表头行数不一致也能各自正确解析。
"""
import math
import re
from pathlib import Path

import pandas as pd
from charset_normalizer import from_path
from openpyxl import load_workbook

SUPPORTED_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv"}

# 纯数字且小数部分全为 0 的字符串,如 "10.0",去掉浮点尾巴变 "10"(保留前导零,如 "00123.0" -> "00123")
_TRAILING_ZERO_FLOAT = re.compile(r"^-?\d+\.0+$")

# pandas 对空表头单元格生成的占位名,如 "Unnamed: 2"
_UNNAMED = re.compile(r"^Unnamed: \d+$")

# 表头带最多覆盖的行数,防止把数据区的大合并误认成表头
_MAX_HEADER_BAND = 10

# 合并区域统一为 0 起半开区间 [r1, r2) x [c1, c2)
_Merge = tuple[int, int, int, int]


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
    for i, c in enumerate(cols):
        name = str(c).strip()
        if not name or _UNNAMED.fullmatch(name):
            # 空表头按列位置命名,两表都有空表头时也能按位置对上
            name = f"未命名{i + 1}"
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
    """探测 CSV 编码。

    utf-8 / BOM 先严格验证;其次取探测结果中可信度大于 0 的那个。
    全部不可信时(常见于只有几个汉字的小文件:GBK 与韩文 cp949 字节高度重叠,
    探测器只能给出 0 置信度的猜测),面向中文场景优先严格试 GBK,
    再不行才退回探测器的最佳猜测。
    """
    raw = path.read_bytes()[:65536]
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        matches = list(from_path(str(path)))
    except Exception:
        matches = []
    confident = next(
        (m.encoding for m in matches if getattr(m, "coherence", 0) > 0), None
    )
    if confident:
        return confident
    for enc in ("gbk", *(m.encoding for m in matches)):
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return None  # 调用方以 utf-8 兜底


def _cell(grid: list[list], r: int, c: int):
    if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
        return grid[r][c]
    return None


def _xlsx_merges(path: Path) -> dict[str, list[_Merge]]:
    try:
        wb = load_workbook(path, read_only=False, data_only=True)
    except Exception:
        return {}
    try:
        return {
            ws.title: [
                (rng.min_row - 1, rng.max_row, rng.min_col - 1, rng.max_col)
                for rng in ws.merged_cells.ranges
            ]
            for ws in wb.worksheets
        }
    finally:
        wb.close()


def _xls_merges(path: Path) -> dict[str, list[_Merge]]:
    try:
        import xlrd

        book = xlrd.open_workbook(str(path), formatting_info=True)
    except Exception:
        # 个别老格式读不到格式信息时,按"无合并单元格"处理
        return {}
    # xlrd 的 merged_cells 本身就是 0 起半开区间
    return {sh.name: [tuple(m) for m in sh.merged_cells] for sh in book.sheets()}


def _merge_map(path: Path) -> dict[str, list[_Merge]]:
    if path.suffix.lower() == ".xls":
        return _xls_merges(path)
    return _xlsx_merges(path)


def _grid_rows(df: pd.DataFrame) -> list[list]:
    return [list(row) for row in df.itertuples(index=False, name=None)]


def _header_band(grid: list[list], merges: list[_Merge], hr: int) -> tuple[int, int]:
    """表头带 [top, bottom](0 起闭区间):从所选行 hr 出发,沿"跨过带边界且有值"的
    合并单元格向上/向下扩展。数据区/标题区的合并不会跨界,天然不受影响。
    """
    top, bottom = hr, hr
    while True:
        ntop, nbottom = top, bottom
        for r1, r2, c1, _c2 in merges:
            if not normalize_value(_cell(grid, r1, c1)):
                continue  # 空的合并区域(如纯格式合并)不参与表头带识别
            if r1 < top < r2 and bottom - r1 + 1 <= _MAX_HEADER_BAND:
                ntop = min(ntop, r1)  # 合并从带上方跨进来 -> 表头带向上扩
            if r1 <= bottom < r2 and r2 - top <= _MAX_HEADER_BAND:
                nbottom = max(nbottom, r2 - 1)  # 合并从带内跨到下方 -> 表头带向下扩
        if (ntop, nbottom) == (top, bottom):
            return top, bottom
        top, bottom = ntop, nbottom


def _anchor_values(
    grid: list[list], merges: list[_Merge], top: int, bottom: int, ncols: int
) -> dict[tuple[int, int], str]:
    """表头带内每个格子的"合并锚点值":格子属于某合并区域时取该区域左上角的值"""
    anchor: dict[tuple[int, int], str] = {}
    for r1, r2, c1, c2 in merges:
        value = normalize_value(_cell(grid, r1, c1))
        if not value:
            continue
        for r in range(max(r1, top), min(r2, bottom + 1)):
            for c in range(max(c1, 0), min(c2, ncols)):
                anchor[(r, c)] = value
    return anchor


def _frame_from_grid(grid: list[list], merges: list[_Merge], header_row: int) -> pd.DataFrame:
    """原始网格 + 合并信息 + 表头行(1 起)-> DataFrame(列名为拼接后的表头)"""
    if header_row < 1 or header_row > len(grid):
        raise ValueError(f"表头行 {header_row} 超出表格范围(共 {len(grid)} 行)")
    hr = header_row - 1
    ncols = max((len(r) for r in grid), default=0)
    top, bottom = _header_band(grid, merges, hr)
    anchor = _anchor_values(grid, merges, top, bottom, ncols)

    names: list[str] = []
    fallback_cols: set[int] = set()  # 表头完全为空的列,若数据也全空则整列丢弃
    for c in range(ncols):
        parts: list[str] = []
        for r in range(top, bottom + 1):
            v = anchor.get((r, c)) or normalize_value(_cell(grid, r, c))
            if v and v not in parts:
                parts.append(v)
        if parts:
            names.append("-".join(parts))
        else:
            names.append(f"未命名{c + 1}")
            fallback_cols.add(c)

    # 数据从表头带下方开始;剔除整行全空的行(合并表头下方常有多余空行)
    data = [
        row for row in grid[bottom + 1 :] if any(normalize_value(v) for v in row)
    ]
    df = pd.DataFrame(data, columns=names)
    keep = [
        name
        for i, name in enumerate(names)
        if i not in fallback_cols or not df[name].eq("").all()
    ]
    return _normalize_df(df[keep])


def _read_excel_sheets(
    path: Path, sheet: str | None, header_row: int
) -> dict[str, pd.DataFrame]:
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    grids = pd.read_excel(path, sheet_name=sheet, engine=engine, dtype=object, header=None)
    if sheet is not None:
        grids = {sheet: grids}
    merge_map = _merge_map(path)
    return {
        name: _frame_from_grid(_grid_rows(df), merge_map.get(name, []), header_row)
        for name, df in grids.items()
    }


def _read_csv(path: Path, header_row: int) -> pd.DataFrame:
    encoding = _detect_encoding(path) or "utf-8"
    # sep=None + python 引擎自动嗅探分隔符(逗号/制表符等)
    df = pd.read_csv(
        path, encoding=encoding, sep=None, engine="python",
        dtype=object, keep_default_na=False, header=header_row - 1,
    )
    return _normalize_df(df)


def read_tables(path: Path, header_row: int = 1) -> dict[str, pd.DataFrame]:
    """读取整个文件,返回 {sheet名: DataFrame}。csv 视为单个名为 CSV 的表。

    header_row:表头所在行数(1 起);该行所在的合并表头带之上的内容会被忽略。
    """
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的文件类型:{suffix},仅支持 {', '.join(sorted(SUPPORTED_SUFFIXES))}")
    if suffix == ".csv":
        return {"CSV": _read_csv(path, header_row)}
    return _read_excel_sheets(path, None, max(1, header_row))


def read_table(path: Path, sheet: str, header_row: int = 1) -> pd.DataFrame:
    """只读取指定工作表(表头行可指定),避免其他工作表的解析问题影响本次请求"""
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的文件类型:{suffix},仅支持 {', '.join(sorted(SUPPORTED_SUFFIXES))}")
    if suffix == ".csv":
        if sheet != "CSV":
            raise ValueError(f"CSV 文件只有一个名为 CSV 的表,没有“{sheet}”")
        return _read_csv(path, max(1, header_row))
    return _read_excel_sheets(path, sheet, max(1, header_row))[sheet]


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
        df = _read_csv_raw_preview(path, max_rows)
        return {"CSV": grid(df)}

    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    tables = pd.read_excel(path, sheet_name=None, engine=engine, dtype=object, header=None, nrows=max_rows)
    return {name: grid(df) for name, df in tables.items()}


def _read_csv_raw_preview(path: Path, max_rows: int) -> pd.DataFrame:
    encoding = _detect_encoding(path) or "utf-8"
    return pd.read_csv(
        path, encoding=encoding, sep=None, engine="python",
        dtype=object, keep_default_na=False, header=None, nrows=max_rows,
    )
