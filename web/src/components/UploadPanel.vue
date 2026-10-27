<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NInputNumber,
  NSelect,
  NTag,
  NUpload,
  NUploadDragger,
  useMessage,
  type UploadCustomRequestOptions,
} from 'naive-ui'
import { parseSheet, upload } from '../api'
import type { ParsedSheet, SheetSelection, UploadInfo } from '../types'

defineProps<{ label: string }>()
const emit = defineEmits<{ 'update:selection': [v: SheetSelection | null] }>()

const message = useMessage()
const uploading = ref(false)
const parsing = ref(false)

const info = ref<UploadInfo | null>(null)
const sheet = ref('')
const headerRow = ref(1)
const parsed = ref<ParsedSheet | null>(null)
let parseTimer: ReturnType<typeof setTimeout> | undefined

const sheetOptions = computed(() =>
  (info.value?.sheets ?? []).map((s) => ({ label: `${s.name}(${s.row_count} 行)`, value: s.name })),
)

const currentSheet = computed(() => info.value?.sheets.find((s) => s.name === sheet.value) ?? null)

watch([sheet, headerRow], () => {
  if (!info.value || !sheet.value) {
    parsed.value = null
    emitSelection()
    return
  }
  clearTimeout(parseTimer)
  parseTimer = setTimeout(runParse, 250)
})

async function runParse() {
  if (!info.value || !sheet.value) return
  parsing.value = true
  try {
    parsed.value = await parseSheet({
      file_id: info.value.file_id,
      sheet: sheet.value,
      header_row: headerRow.value,
    })
  } catch (e) {
    parsed.value = null
    message.error(e instanceof Error ? e.message : '解析失败')
  } finally {
    parsing.value = false
  }
  emitSelection()
}

function emitSelection() {
  if (info.value && parsed.value) {
    emit('update:selection', {
      file_id: info.value.file_id,
      filename: info.value.filename,
      sheet: parsed.value.sheet,
      header_row: parsed.value.header_row,
      columns: parsed.value.columns,
      row_count: parsed.value.row_count,
    })
  } else {
    emit('update:selection', null)
  }
}

async function customRequest({ file, onFinish, onError }: UploadCustomRequestOptions) {
  uploading.value = true
  try {
    const raw = file.file
    if (!raw) throw new Error('文件读取失败')
    const result = await upload(raw)
    info.value = result
    headerRow.value = 1
    parsed.value = null
    sheet.value = result.sheets[0]?.name ?? '' // 触发 watch -> 自动解析
    const totalRows = result.sheets.reduce((n, s) => n + s.row_count, 0)
    message.success(`“${result.filename}”上传成功:${result.sheets.length} 个工作表 / ${totalRows} 行`)
    onFinish()
  } catch (e) {
    message.error(e instanceof Error ? e.message : '上传失败')
    onError()
  } finally {
    uploading.value = false
  }
}

function onSheetChange(v: string) {
  headerRow.value = 1
  sheet.value = v
}

function onHeaderRowChange(v: number | null) {
  headerRow.value = Math.max(1, Math.floor(v ?? 1))
}

function remove() {
  clearTimeout(parseTimer)
  info.value = null
  sheet.value = ''
  headerRow.value = 1
  parsed.value = null
  emitSelection()
}
</script>

<template>
  <n-card :title="label" size="small">
    <template #header-extra>
      <n-button v-if="info" quaternary size="tiny" type="error" @click="remove">移除</n-button>
    </template>

    <n-upload
      v-if="!info"
      :custom-request="customRequest"
      :show-file-list="false"
      accept=".xlsx,.xlsm,.xls,.csv"
      :disabled="uploading"
    >
      <n-upload-dragger>
        <div style="padding: 30px 16px; text-align: center; color: #6b7690">
          <div style="font-size: 15px; font-weight: 600; color: #3c4a66">
            {{ uploading ? '正在解析…' : '点击或拖拽文件到此处' }}
          </div>
          <div style="font-size: 12px; margin-top: 8px">支持 .xlsx / .xlsm / .xls / .csv,可混合上传</div>
        </div>
      </n-upload-dragger>
    </n-upload>

    <template v-else>
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px">
        <n-tag type="success" size="small" :bordered="false">{{ info.filename }}</n-tag>
        <n-select
          :value="sheet"
          :options="sheetOptions"
          size="small"
          style="width: 190px"
          placeholder="选择工作表"
          @update:value="onSheetChange"
        />
        <span style="font-size: 12px; color: #7a8699">表头所在行</span>
        <n-input-number
          :value="headerRow"
          size="small"
          :min="1"
          :disabled="parsing"
          style="width: 100px"
          @update:value="onHeaderRowChange"
        />
      </div>

      <div v-if="currentSheet?.raw_preview?.length" class="raw-preview">
        <table class="raw-table">
          <tbody>
            <tr
              v-for="(row, i) in currentSheet.raw_preview"
              :key="i"
              :class="{ 'raw-table--header-row': i + 1 === headerRow }"
            >
              <td class="raw-table__no">{{ i + 1 }}</td>
              <td v-for="(cell, j) in row" :key="j" :title="cell">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style="font-size: 12px; color: #7a8699; margin: 10px 0 6px">
        <template v-if="parsing">正在按第 {{ headerRow }} 行解析…</template>
        <template v-else-if="parsed">
          按第 {{ headerRow }} 行解析:{{ parsed.columns.length }} 列 / {{ parsed.row_count }} 行数据
        </template>
        <template v-else>表头行无效,请调整上方“表头所在行”</template>
      </div>
      <div class="col-tags">
        <n-tag v-for="c in parsed?.columns ?? []" :key="c" size="small" :bordered="false">
          {{ c }}
        </n-tag>
      </div>
    </template>
  </n-card>
</template>
