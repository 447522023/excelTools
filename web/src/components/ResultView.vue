<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NSpace,
  NTag,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { compare, exportFile } from '../api'
import type { CompareRequest, CompareResponse } from '../types'

const props = defineProps<{ req: CompareRequest }>()
const emit = defineEmits<{ back: []; restart: [] }>()

const message = useMessage()
const data = ref<CompareResponse | null>(null)
const loading = ref(false)
const exporting = ref<'xlsx' | 'csv' | null>(null)

const STATUS_TAG: Record<string, 'warning' | 'info' | 'error' | 'success'> = {
  仅表A: 'warning',
  仅表B: 'info',
  值不一致: 'error',
  一致: 'success',
}

// naive-ui 现版本的 row-key 回调只传 row 一个参数,用整行内容拼稳定 key
function rowKey(row: Record<string, string>): string {
  return Object.values(row).join('\u0001')
}

const summaryChips = computed(() => {
  const s = data.value?.summary ?? {}
  return [
    { label: '表A总行数', num: s['表A总行数'] ?? 0, color: '#3c4a66' },
    { label: '表B总行数', num: s['表B总行数'] ?? 0, color: '#3c4a66' },
    { label: '完全一致', num: s['一致'] ?? 0, color: '#18a058' },
    { label: '值不一致', num: s['值不一致'] ?? 0, color: '#d94030' },
    { label: '仅表A有', num: s['仅表A'] ?? 0, color: '#d97706' },
    { label: '仅表B有', num: s['仅表B'] ?? 0, color: '#2563eb' },
  ]
})

const tableColumns = computed<DataTableColumns<Record<string, string>>>(() =>
  (data.value?.columns ?? []).map((c) => ({
    title: c,
    key: c,
    minWidth: 120,
    ellipsis: { tooltip: true },
    render:
      c === '状态'
        ? (row) =>
            h(
              NTag,
              { type: STATUS_TAG[row[c]] ?? 'default', size: 'small', bordered: false },
              { default: () => row[c] },
            )
        : undefined,
  })),
)

async function load() {
  loading.value = true
  try {
    data.value = await compare({ ...props.req, page: 1, page_size: 0 })
  } catch (e) {
    message.error(e instanceof Error ? e.message : '查询失败')
  } finally {
    loading.value = false
  }
}

async function doExport(format: 'xlsx' | 'csv') {
  exporting.value = format
  try {
    const { page: _p, page_size: _s, ...rest } = props.req
    const savedPath = await exportFile({ ...rest, format })
    message.success(savedPath ? `已导出到:${savedPath}` : '导出成功,已开始下载')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '导出失败')
  } finally {
    exporting.value = null
  }
}

onMounted(load)
</script>

<template>
  <n-card size="small">
    <template #header>
      对比结果
      <n-tag :type="req.mode === 'diff' ? 'error' : 'success'" size="small" :bordered="false" style="margin-left: 8px">
        {{ req.mode === 'diff' ? '找不同' : '找相同' }}
      </n-tag>
    </template>
    <template #header-extra>
      <n-space>
        <n-button size="small" @click="emit('back')">返回修改配置</n-button>
        <n-button size="small" @click="emit('restart')">重新开始</n-button>
        <n-button size="small" type="primary" :loading="exporting === 'xlsx'" @click="doExport('xlsx')">
          导出 Excel
        </n-button>
        <n-button size="small" :loading="exporting === 'csv'" @click="doExport('csv')">导出 CSV</n-button>
      </n-space>
    </template>

    <div class="stat-chips">
      <div v-for="chip in summaryChips" :key="chip.label" class="stat-chip">
        <div class="num" :style="{ color: chip.color }">{{ chip.num }}</div>
        <div class="label">{{ chip.label }}</div>
      </div>
    </div>

    <div style="font-size: 12px; color: #7a8699; margin-bottom: 8px">
      结果共 {{ data?.total ?? 0 }} 行,表格内滚动查看全部
    </div>

    <n-empty
      v-if="data && data.total === 0"
      description="没有符合条件的结果"
      style="padding: 40px 0"
    />
    <n-data-table
      v-else
      :columns="tableColumns"
      :data="data?.rows ?? []"
      :loading="loading"
      :row-key="rowKey"
      :pagination="false"
      :scroll-x="1200"
      size="small"
      :bordered="false"
      striped
      max-height="620"
    />
  </n-card>
</template>
