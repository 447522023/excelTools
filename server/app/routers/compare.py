"""对比与导出(线上 HTTP 接口,业务逻辑在 services/ops.py)"""
import io

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.routers.files import store
from app.schemas import CompareRequest, CompareResponse, ExportRequest
from app.services import exporter, ops

router = APIRouter(prefix="/api", tags=["compare"])


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest) -> CompareResponse:
    try:
        result = ops.compare_page(store, req.model_dump())
    except ops.OpError as e:
        raise HTTPException(status_code=404 if "不存在" in e.message else 400, detail=e.message)
    return CompareResponse(**result)


@router.post("/export")
def export(req: ExportRequest) -> Response:
    try:
        filename, data = ops.export_result(store, req.model_dump())
    except ops.OpError as e:
        raise HTTPException(status_code=404 if "不存在" in e.message else 400, detail=e.message)

    if filename.endswith(".csv"):
        media_type = "text/csv"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": exporter.content_disposition(filename)},
    )
