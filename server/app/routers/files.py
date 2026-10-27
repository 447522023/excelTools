"""文件上传与解析(线上 HTTP 接口,业务逻辑在 services/ops.py)"""
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas import ParseRequest, ParseResponse, UploadResponse
from app.services import excel_io, ops
from app.storage import FileStore

router = APIRouter(prefix="/api", tags=["files"])
store = FileStore()


@router.post("/upload", response_model=UploadResponse)
def upload(file: UploadFile = File(...)) -> UploadResponse:
    data = file.file.read()
    try:
        result = ops.upload_bytes(store, file.filename or "未命名", data)
    except ops.OpError as e:
        status = 415 if e.message.startswith("不支持的文件类型") else 400
        raise HTTPException(status_code=status, detail=e.message)
    return UploadResponse(**result)


@router.post("/parse", response_model=ParseResponse)
def parse_sheet(req: ParseRequest) -> ParseResponse:
    try:
        result = ops.parse_sheet(store, req.file_id, req.sheet, req.header_row)
    except ops.OpError as e:
        raise HTTPException(status_code=404 if "不存在" in e.message else 400, detail=e.message)
    return ParseResponse(**result)
