<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NStep, NSteps, useMessage } from 'naive-ui'
import type { CompareMode, CompareRequest, SheetSelection } from '../types'
import { isDesktop } from '../api'
import CompareConfig from './CompareConfig.vue'
import DownloadEntry from './DownloadEntry.vue'
import ResultView from './ResultView.vue'
import UploadPanel from './UploadPanel.vue'

const message = useMessage()

const step = ref(1)
// 面板重建钥匙:仅在"重新开始"时变化,强制清空上传状态;
// 平时往返各步骤用 v-show 保持挂载,已上传的表与所选工作表/表头行不丢失
const panelKey = ref(0)

// 第一步:两个文件(每个面板自己管理工作表/表头行,对外只暴露一个可对比的"表")
const leftSel = ref<SheetSelection | null>(null)
const rightSel = ref<SheetSelection | null>(null)

const bothUploaded = computed(() => !!leftSel.value && !!rightSel.value)

// 第二步:对比配置
const mode = ref<CompareMode>('diff')
const leftKeys = ref<string[]>([])
const rightKeys = ref<string[]>([])
const compareCols = ref<string[]>([]) // 空 = 默认全部共有列
const compareFormulas = ref(false) // 对比公式(公式文本不同也算差异)

const sharedColumns = computed(() => {
  const a = leftSel.value?.columns ?? []
  const b = new Set(rightSel.value?.columns ?? [])
  return a.filter((c) => b.has(c))
})

// 第三步:结果
const req = ref<CompareRequest | null>(null)

function toStep2() {
  if (!bothUploaded.value) {
    message.warning('请先上传两个文件并确认表头行')
    return
  }
  leftKeys.value = []
  rightKeys.value = []
  compareCols.value = []
  step.value = 2
}

function runCompare() {
  const a = leftSel.value!
  const b = rightSel.value!
  req.value = {
    left_file_id: a.file_id,
    left_sheet: a.sheet,
    left_header_row: a.header_row,
    right_file_id: b.file_id,
    right_sheet: b.sheet,
    right_header_row: b.header_row,
    left_keys: leftKeys.value,
    right_keys: rightKeys.value,
    mode: mode.value,
    compare_columns: compareCols.value.length ? compareCols.value : null,
    compare_formulas: mode.value !== 'cell' ? compareFormulas.value : false,
    page: 1,
    page_size: 0,
  }
  step.value = 3
}

function reset() {
  leftSel.value = null
  rightSel.value = null
  mode.value = 'diff'
  leftKeys.value = []
  rightKeys.value = []
  compareCols.value = []
  compareFormulas.value = false
  req.value = null
  step.value = 1
  panelKey.value += 1
}
</script>

<template>
  <div>
    <header class="page-header">
      <div>
        <h1>表格对比工具</h1>
        <p>上传两个表格(xlsx / xls / xlsm / csv),按关键列对比,找不同、找相同,一键导出结果</p>
      </div>
      <DownloadEntry v-if="!isDesktop" />
    </header>

    <main class="page-content">
      <n-steps :current="step" size="small" style="margin-bottom: 26px">
        <n-step title="上传表格" />
        <n-step title="配置对比" />
        <n-step title="查看结果" />
      </n-steps>

      <div v-show="step === 1">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 18px">
          <UploadPanel :key="`L-${panelKey}`" v-model:selection="leftSel" label="表 A" />
          <UploadPanel :key="`R-${panelKey}`" v-model:selection="rightSel" label="表 B" />
        </div>
        <div style="margin-top: 22px; display: flex; gap: 12px">
          <n-button type="primary" size="large" :disabled="!bothUploaded" @click="toStep2">
            下一步:配置对比
          </n-button>
        </div>
      </div>

      <template v-if="step === 2">
        <CompareConfig
          v-model:mode="mode"
          v-model:left-keys="leftKeys"
          v-model:right-keys="rightKeys"
          v-model:compare-columns="compareCols"
          v-model:compare-formulas="compareFormulas"
          :left-columns="leftSel?.columns ?? []"
          :right-columns="rightSel?.columns ?? []"
          :shared-columns="sharedColumns"
          :left-file="leftSel?.filename ?? ''"
          :right-file="rightSel?.filename ?? ''"
          @run="runCompare"
          @back="step = 1"
        />
      </template>

      <template v-if="step === 3 && req">
        <ResultView :req="req" @back="step = 2" @restart="reset" />
      </template>
    </main>
  </div>
</template>
