"""API 请求/响应模型"""
from enum import Enum

from pydantic import BaseModel, Field


class CompareMode(str, Enum):
    DIFF = "diff"  # 找不同
    SAME = "same"  # 找相同


class SheetInfo(BaseModel):
    name: str
    row_count: int
    columns: list[str]
    # 前若干行原始内容(不做表头假设),帮助用户选择表头所在行
    raw_preview: list[list[str]] = Field(default_factory=list)


class ParseRequest(BaseModel):
    file_id: str
    sheet: str
    header_row: int = Field(default=1, ge=1)


class ParseResponse(BaseModel):
    sheet: str
    header_row: int
    row_count: int
    columns: list[str]
    preview: list[dict[str, str]]


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    sheets: list[SheetInfo]


class CompareRequest(BaseModel):
    left_file_id: str
    left_sheet: str
    right_file_id: str
    right_sheet: str
    # 表头所在行数(1 起,该行之上的内容会被忽略)
    left_header_row: int = Field(default=1, ge=1)
    right_header_row: int = Field(default=1, ge=1)
    # 关键列:左右各自选择,按顺序一一对应,数量必须一致
    left_keys: list[str] = Field(min_length=1)
    right_keys: list[str] = Field(min_length=1)
    mode: CompareMode = CompareMode.DIFF
    # 参与值比较的列(用左侧列名,须为两表共有列);为 None 时默认"全部共有列(不含关键列)"
    compare_columns: list[str] | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=0, le=100000)  # 0 = 不分页,返回全部


class CompareResponse(BaseModel):
    mode: CompareMode
    total: int
    columns: list[str]
    rows: list[dict[str, str]]
    summary: dict[str, int]
    # 名字对不上、只在一侧存在的列(未参与对比):"仅表A的列" / "仅表B的列"
    unmatched_columns: dict[str, list[str]] = Field(default_factory=dict)


class ExportRequest(CompareRequest):
    format: str = Field(default="xlsx", pattern="^(xlsx|csv)$")


class DownloadInfo(BaseModel):
    # 离线版安装包信息,platform: windows / macos / linux
    platform: str
    filename: str
    size: int
    mtime: int  # 秒级时间戳
    url: str  # 相对站内下载地址(/downloads/<filename>)
    downloads: int  # 该平台累计下载次数
