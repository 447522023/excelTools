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
    """上传文件内容 → 解析出各工作表(列、行数、原始预览)"""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in excel_io.SUPPORTED_SUFFIXES:
        raise OpError(
            f"不支持的文件类型“{suffix or filename}”,请上传 {'/'.join(sorted(excel_io.SUPPORTED_SUFFIXES))}"
        )
    file_id = store.save(filename, suffix, io.BytesIO(data))
    path = store.path(file_id)
    try:
        tables = excel_io.read_tables(path)
        previews = excel_io.raw_preview(path)
    except Exception as e:
        raise OpError(f"文件解析失败:{e}")

    sheets = [
        {
            "name": name,
            "row_count": len(df),
            "columns": list(df.columns),
            "raw_preview": previews.get(name, []),
        }
        for name, df in tables.items()
    ]
    if not sheets:
        raise OpError("文件中没有可读取的工作表")
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


def _load_df(store: FileStore, file_id: str, sheet: str, header_row: int, side: str):
    path = store.path(file_id)
    if path is None:
        raise OpError(f"表{side}的文件不存在或已过期,请重新上传")
    try:
        return excel_io.read_table(path, sheet, header_row)
    except Exception as e:
        raise OpError(f"表{side}解析失败:{e}")


def _run(store: FileStore, payload: dict):
    req = _validate(payload)
    df_a = _load_df(store, req.left_file_id, req.left_sheet, req.left_header_row, "A")
    df_b = _load_df(store, req.right_file_id, req.right_sheet, req.right_header_row, "B")

    if len(req.left_keys) != len(req.right_keys):
        raise OpError("表A与表B的关键列数量不一致,请按顺序一一对应")
    missing_a = [c for c in req.left_keys if c not in df_a.columns]
    missing_b = [c for c in req.right_keys if c not in df_b.columns]
    if missing_a or missing_b:
        raise OpError(f"关键列不存在:表A缺少 {missing_a},表B缺少 {missing_b}")

    outcome = comparer.compare_tables(
        df_a, df_b, req.left_keys, req.right_keys, req.mode, req.compare_columns
    )
    return req, outcome


def compare_page(store: FileStore, payload: dict) -> dict:
    req, outcome = _run(store, payload)
    if req.page_size == 0:
        rows = outcome.rows
    else:
        start = (req.page - 1) * req.page_size
        rows = outcome.rows[start : start + req.page_size]
    return {
        "mode": req.mode.value,
        "total": len(outcome.rows),
        "columns": outcome.columns,
        "rows": rows,
        "summary": outcome.summary,
        "unmatched_columns": {k: v for k, v in outcome.unmatched_columns.items() if v},
    }


def export_result(store: FileStore, payload: dict) -> tuple[str, bytes]:
    req = _validate({**payload, "format": payload.get("format", "xlsx")}, model=ExportRequest)
    _, outcome = _run(store, payload)
    mode_name = "找不同" if req.mode == CompareMode.DIFF else "找相同"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if req.format == "csv":
        return f"对比结果_{mode_name}_{stamp}.csv", exporter.to_csv(outcome)
    return f"对比结果_{mode_name}_{stamp}.xlsx", exporter.to_xlsx(outcome)
