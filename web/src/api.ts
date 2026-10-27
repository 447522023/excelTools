import type {
  CompareRequest,
  CompareResponse,
  DownloadInfo,
  ExportRequest,
  ParseRequest,
  ParsedSheet,
  UploadInfo,
} from './types'

/* ============================================================
 * 双通道:
 *  - 线上(浏览器):fetch 走 /api HTTP 接口
 *  - 离线客户端(pywebview):window.pywebview.api 直接调 Python,零网络
 * 两个通道对外函数签名完全一致,组件无感知。
 * ============================================================ */

declare global {
  interface Window {
    pywebview?: {
      api: {
        upload(filename: string, dataB64: string): Promise<Record<string, unknown>>
        parse_sheet(fileId: string, sheet: string, headerRow: number): Promise<Record<string, unknown>>
        compare(payload: unknown): Promise<Record<string, unknown>>
        export(payload: unknown): Promise<{ saved?: string; cancelled?: boolean; error?: string }>
      }
    }
  }
}

const isDesktop =
  typeof window !== 'undefined' && ('pywebview' in window || window.location.protocol === 'file:')

export { isDesktop }

type DesktopApi = NonNullable<Window['pywebview']>['api']

let desktopReady: Promise<DesktopApi> | null = null

function getDesktopApi(): Promise<DesktopApi> {
  if (!desktopReady) {
    desktopReady = new Promise((resolve, reject) => {
      if (window.pywebview?.api) {
        resolve(window.pywebview.api)
        return
      }
      const timer = setTimeout(() => reject(new Error('桌面环境初始化超时')), 20000)
      window.addEventListener(
        'pywebviewready',
        () => {
          clearTimeout(timer)
          resolve(window.pywebview!.api)
        },
        { once: true },
      )
    })
  }
  return desktopReady
}

function bridgeError(res: Record<string, unknown>): asserts res {
  if (typeof res?.error === 'string' && res.error) throw new Error(res.error)
}

async function fileToB64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let bin = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk))
  }
  return btoa(bin)
}

/* ---------------- HTTP 通道 ---------------- */

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `请求失败(${res.status})`
    try {
      const data = await res.json()
      if (data?.detail) msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

async function httpUpload(file: File): Promise<UploadInfo> {
  const fd = new FormData()
  fd.append('file', file)
  return handle<UploadInfo>(await fetch('/api/upload', { method: 'POST', body: fd }))
}

async function httpParse(req: ParseRequest): Promise<ParsedSheet> {
  return handle<ParsedSheet>(
    await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

async function httpCompare(req: CompareRequest): Promise<CompareResponse> {
  return handle<CompareResponse>(
    await fetch('/api/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  )
}

/* ---------------- 对外统一接口 ---------------- */

/** 可下载的离线版安装包清单(仅线上版;离线客户端无服务端,返回空) */
export async function fetchDownloads(): Promise<DownloadInfo[]> {
  if (isDesktop) return []
  return handle<DownloadInfo[]>(await fetch('/api/downloads'))
}

export async function upload(file: File): Promise<UploadInfo> {
  if (isDesktop) {
    const api = await getDesktopApi()
    const res = await api.upload(file.name, await fileToB64(file))
    bridgeError(res)
    return res as unknown as UploadInfo
  }
  return httpUpload(file)
}

export async function parseSheet(req: ParseRequest): Promise<ParsedSheet> {
  if (isDesktop) {
    const api = await getDesktopApi()
    const res = await api.parse_sheet(req.file_id, req.sheet, req.header_row)
    bridgeError(res)
    return res as unknown as ParsedSheet
  }
  return httpParse(req)
}

export async function compare(req: CompareRequest): Promise<CompareResponse> {
  if (isDesktop) {
    const api = await getDesktopApi()
    const res = await api.compare({ ...req })
    bridgeError(res)
    return res as unknown as CompareResponse
  }
  return httpCompare(req)
}

/**
 * 导出。浏览器环境返回 null(已触发浏览器下载);
 * 桌面环境返回保存路径(原生另存为对话框)。
 */
export async function exportFile(req: ExportRequest): Promise<string | null> {
  if (isDesktop) {
    const api = await getDesktopApi()
    const res = await api.export({ ...req })
    if (res?.error) throw new Error(res.error)
    if (res?.cancelled) return null
    return res?.saved ?? null
  }
  const res = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    let msg = `导出失败(${res.status})`
    try {
      const data = await res.json()
      if (data?.detail) msg = data.detail
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') ?? ''
  const m = /filename\*=UTF-8''([^;]+)/.exec(cd)
  const name = m ? decodeURIComponent(m[1]) : '对比结果.xlsx'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
  return null
}
