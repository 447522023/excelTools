<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NPopover, NSpin } from 'naive-ui'
import { fetchDownloads } from '../api'
import type { DownloadInfo } from '../types'

const PLATFORM_META: Record<string, { label: string; icon: string }> = {
  windows: { label: 'Windows', icon: '🪟' },
  macos: { label: 'macOS', icon: '🍎' },
  linux: { label: 'Linux', icon: '🐧' },
}

const loading = ref(false)
const loaded = ref(false)
const items = ref<DownloadInfo[]>([])
const error = ref('')

async function load(show = true) {
  if (!show || loading.value || loaded.value) return
  loading.value = true
  error.value = ''
  try {
    items.value = await fetchDownloads()
    loaded.value = true
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function find(platform: string): DownloadInfo | undefined {
  return items.value.find((i) => i.platform === platform)
}

function fmtSize(n: number): string {
  if (n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(1) + ' GB'
  if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + ' MB'
  if (n >= 1024) return Math.round(n / 1024) + ' KB'
  return n + ' B'
}

function fmtDate(ts: number): string {
  const d = new Date(ts * 1000)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}
</script>

<template>
  <n-popover trigger="click" placement="bottom-end" :width="336" @update:show="load">
    <template #trigger>
      <n-button size="small" round color="rgba(255,255,255,0.18)" text-color="#fff">
        ⬇ 下载离线版
      </n-button>
    </template>
    <n-spin :show="loading">
      <div class="dl-pop">
        <p class="dl-pop__title">离线桌面版(免装 Python,断网可用,数据不出本机)</p>
        <div v-for="(meta, plat) in PLATFORM_META" :key="plat" class="dl-row">
          <span class="dl-row__icon">{{ meta.icon }}</span>
          <div class="dl-row__body">
            <div class="dl-row__name">{{ meta.label }}</div>
            <div v-if="find(plat)" class="dl-row__meta">
              {{ fmtSize(find(plat)!.size) }} · {{ fmtDate(find(plat)!.mtime) }} · 已下载
              {{ find(plat)!.downloads }} 次
            </div>
            <div v-else-if="loaded" class="dl-row__meta dl-row__meta--none">敬请期待</div>
          </div>
          <a
            v-if="find(plat)"
            class="dl-row__btn"
            :href="find(plat)!.url"
            :download="find(plat)!.filename"
          >
            下载
          </a>
        </div>
        <p v-if="error" class="dl-pop__err">{{ error }}</p>
        <p class="dl-pop__tip">首次启动若被系统拦截:macOS 右键 → 打开;Linux 解压后 chmod +x 再运行</p>
      </div>
    </n-spin>
  </n-popover>
</template>
