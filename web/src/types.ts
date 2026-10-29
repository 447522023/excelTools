export interface SheetInfo {
  name: string
  row_count: number
  columns: string[]
  /** 前若干行原始内容(不做表头假设),用于挑选表头所在行 */
  raw_preview: string[][]
}

export interface UploadInfo {
  file_id: string
  filename: string
  sheets: SheetInfo[]
}

export interface ParseRequest {
  file_id: string
  sheet: string
  header_row: number
}

export interface ParsedSheet {
  sheet: string
  header_row: number
  row_count: number
  columns: string[]
  preview: Record<string, string>[]
}

/** 一个可供对比的"表":文件 + 工作表 + 表头行 + 解析出的列 */
export interface SheetSelection {
  file_id: string
  filename: string
  sheet: string
  header_row: number
  columns: string[]
  row_count: number
}

export type CompareMode = 'diff' | 'same' | 'cell'

export interface CompareRequest {
  left_file_id: string
  left_sheet: string
  left_header_row: number
  right_file_id: string
  right_sheet: string
  right_header_row: number
  left_keys: string[]
  right_keys: string[]
  mode: CompareMode
  compare_columns: string[] | null
  page: number
  /** 0 = 不分页,返回全部结果 */
  page_size: number
}

export interface CompareResponse {
  mode: CompareMode
  total: number
  columns: string[]
  rows: Record<string, string>[]
  summary: Record<string, number>
  /** 名字对不上、未参与对比的列:"仅表A的列" / "仅表B的列" */
  unmatched_columns?: Record<string, string[]>
  /** 只在一侧存在的工作表:"仅表A的工作表" / "仅表B的工作表" */
  unmatched_sheets?: Record<string, string[]>
}

export interface ExportRequest extends Omit<CompareRequest, 'page' | 'page_size'> {
  format: 'xlsx' | 'csv'
}

/** 离线版安装包信息(线上版页面"下载离线版"入口) */
export interface DownloadInfo {
  platform: 'windows' | 'macos' | 'linux'
  filename: string
  size: number
  mtime: number
  url: string
  downloads: number
}
