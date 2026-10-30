"""共享业务操作:线上 FastAPI 路由与离线客户端(pywebview 桥接)共用,逻辑单一来源。

所有函数出错时抛 OpError,message 为可直接展示给用户的中文提示。
"""
import io
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from app.schemas import CompareMode, CompareRequest, ExportRequest
from app.services import comparer, excel_io, exporter
from app.storage import FileStore


class OpError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def upload_bytes(store: FileStore, filename: str, data: bytes) -> dict:
    """上传文件内容 → 解析出各工作表(列、行数、原始预览)。单次读取,预览复用同一份网格"""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in excel_io.SUPPORTED_SUFFIXES:
        raise OpError(
            f"不支持的文件类型“{suffix or filename}”,请上传 {'/'.join(sorted(excel_io.SUPPORTED_SUFFIXES))}"
        )
    file_id = store.save(filename, suffix, io.BytesIO(data))
    path = store.path(file_id)
    try:
        described = excel_io.describe_file(path)
    except Exception as e:
        raise OpError(f"文件解析失败:{e}")
    if not described:
        raise OpError("文件中没有可读取的工作表")
    sheets = [
        {
            "name": name,
            "row_count": t["row_count"],
            "columns": t["columns"],
            "raw_preview": t["raw_preview"],
        }
        for name, t in described.items()
    ]
    return {"file_id": file_id, "filename": filename, "sheets": sheets}


def parse_sheet(store: FileStore, file_id: str, sheet: str, header_row: int = 1) -> dict:
    path = store.path(file_id)
    if path is None:
        raise OpError("文件不存在或已过期,请重新上传")
    try:
        df = excel_io.read_table(path, sheet, header_row)
    except Exception as e:
        raise OpError(f"按第 {header_row} 行解析失败:{e}")
    if not list(df.columns):
        raise OpError(f"第 {header_row} 行没有可识别的表头,请调整表头所在行数")
    return {
        "sheet": sheet,
        "header_row": header_row,
        "row_count": len(df),
        "columns": list(df.columns),
        "preview": df.head(5).to_dict(orient="records"),
    }


def _validate(payload: dict, model=CompareRequest):
    try:
        return model.model_validate(payload)
    except ValidationError as e:
        err = e.errors()[0]
        loc = ".".join(str(x) for x in err.get("loc", ()))
        raise OpError(f"参数“{loc}”不合法:{err.get('msg', str(e))}")


def _run(store: FileStore, payload: dict):
    req = _validate(payload)
    path_a = store.path(req.left_file_id)
    path_b = store.path(req.right_file_id)
    if path_a is None:
        raise OpError("表A的文件不存在或已过期,请重新上传")
    if path_b is None:
        raise OpError("表B的文件不存在或已过期,请重新上传")

    if req.mode == CompareMode.CELL:
        # 坐标模式:不做表头假设,网格逐格比较(含公式层)
        try:
            grid_a = excel_io.read_grid(path_a, req.left_sheet)[req.left_sheet]
            grid_b = excel_io.read_grid(path_b, req.right_sheet)[req.right_sheet]
            fa = excel_io.read_formulas(path_a).get(req.left_sheet, {})
            fb = excel_io.read_formulas(path_b).get(req.right_sheet, {})
        except Exception as e:
            raise OpError(f"坐标对比失败:{e}")
        # 坐标范式由 compare_grids 决定;mode 仍表达"输出差异还是输出一致"
        outcome = comparer.compare_grids(grid_a, grid_b, fa, fb, comparer.MODE_DIFF)
        return req, outcome

    if not req.left_keys or not req.right_keys:
        raise OpError("请先选择关键列;表没有关键列时可用「坐标对比」模式")
    formulas_a = formulas_b = None
    row_origins_a = row_origins_b = None
    col_origins_a = col_origins_b = None
    try:
        if req.compare_formulas:
            # 公式层对比:额外取数据行/列在工作表里的原始坐标,用于查公式文本
            df_a, row_origins_a, col_origins_a = excel_io.read_table_with_pos(
                path_a, req.left_sheet, req.left_header_row
            )
            formulas_a = excel_io.read_formulas(path_a).get(req.left_sheet, {})
        else:
            df_a = excel_io.read_table(path_a, req.left_sheet, req.left_header_row)
    except Exception as e:
        raise OpError(f"表A解析失败:{e}")
    try:
        if req.compare_formulas:
            df_b, row_origins_b, col_origins_b = excel_io.read_table_with_pos(
                path_b, req.right_sheet, req.right_header_row
            )
            formulas_b = excel_io.read_formulas(path_b).get(req.right_sheet, {})
        else:
            df_b = excel_io.read_table(path_b, req.right_sheet, req.right_header_row)
    except Exception as e:
        raise OpError(f"表B解析失败:{e}")

    if len(req.left_keys) != len(req.right_keys):
        raise OpError("表A与表B的关键列数量不一致,请按顺序一一对应")
    missing_a = [c for c in req.left_keys if c not in df_a.columns]
    missing_b = [c for c in req.right_keys if c not in df_b.columns]
    if missing_a or missing_b:
        raise OpError(f"关键列不存在:表A缺少 {missing_a},表B缺少 {missing_b}")

    outcome = comparer.compare_tables(
        df_a, df_b, req.left_keys, req.right_keys, req.mode, req.compare_columns,
        compare_formulas=req.compare_formulas,
        formulas_a=formulas_a,
        row_origins_a=row_origins_a,
        col_origins_a=col_origins_a,
        formulas_b=formulas_b,
        row_origins_b=row_origins_b,
        col_origins_b=col_origins_b,
    )
    return req, outcome


def _unmatched_sheets(store: FileStore, file_id_a: str, file_id_b: str) -> dict[str, list[str]]:
    """两文件各有哪些工作表是对方没有的(轻量元数据读取,失败不影响主流程)"""
    try:
        path_a, path_b = store.path(file_id_a), store.path(file_id_b)
        if path_a is None or path_b is None:
            return {}
        names_a = set(excel_io.sheet_names(path_a))
        names_b = set(excel_io.sheet_names(path_b))
        return {
            "仅表A的工作表": sorted(names_a - names_b),
            "仅表B的工作表": sorted(names_b - names_a),
        }
    except Exception:
        return {}


def compare_page(store: FileStore, payload: dict) -> dict:
    req, outcome = _run(store, payload)
    if req.page_size == 0:
        rows = outcome.rows
    else:
        start = (req.page - 1) * req.page_size
        rows = outcome.rows[start : start + req.page_size]
    unmatched_sheets = _unmatched_sheets(store, req.left_file_id, req.right_file_id)
    return {
        "mode": req.mode.value,
        "total": len(outcome.rows),
        "columns": outcome.columns,
        "rows": rows,
        "summary": outcome.summary,
        "unmatched_columns": {k: v for k, v in outcome.unmatched_columns.items() if v},
        "unmatched_sheets": {k: v for k, v in unmatched_sheets.items() if v},
    }


def export_result(store: FileStore, payload: dict) -> tuple[str, bytes]:
    req = _validate({**payload, "format": payload.get("format", "xlsx")}, model=ExportRequest)
    _, outcome = _run(store, payload)
    mode_name = {"diff": "找不同", "same": "找相同", "cell": "坐标对比"}[req.mode.value]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if req.format == "csv":
        return f"对比结果_{mode_name}_{stamp}.csv", exporter.to_csv(outcome)
    return f"对比结果_{mode_name}_{stamp}.xlsx", exporter.to_xlsx(outcome)
