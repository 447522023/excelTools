<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NCard, NRadioButton, NRadioGroup, NSelect, NSpace } from 'naive-ui'
import type { CompareMode } from '../types'

const props = defineProps<{
  leftColumns: string[]
  rightColumns: string[]
  sharedColumns: string[]
  leftFile: string
  rightFile: string
  mode: CompareMode
  leftKeys: string[]
  rightKeys: string[]
  compareColumns: string[]
}>()

const emit = defineEmits<{
  'update:mode': [v: CompareMode]
  'update:leftKeys': [v: string[]]
  'update:rightKeys': [v: string[]]
  'update:compareColumns': [v: string[]]
  run: []
  back: []
}>()

const leftOptions = computed(() => props.leftColumns.map((c) => ({ label: c, value: c })))
const rightOptions = computed(() => props.rightColumns.map((c) => ({ label: c, value: c })))

const comparableColumns = computed(() =>
  props.sharedColumns.filter((c) => !props.leftKeys.includes(c)),
)
const compareOptions = computed(() => comparableColumns.value.map((c) => ({ label: c, value: c })))

const keysPaired = computed(
  () => props.leftKeys.length > 0 && props.leftKeys.length === props.rightKeys.length,
)
const hasComparable = computed(() => comparableColumns.value.length > 0)
const canRun = computed(() => keysPaired.value && hasComparable.value)

const keyCountHint = computed(() => {
  if (props.leftKeys.length === props.rightKeys.length) return ''
  return `两边关键列数量不一致(表A ${props.leftKeys.length} 个 / 表B ${props.rightKeys.length} 个)`
})
</script>

<template>
  <n-card title="配置对比规则" size="small">
    <template #header-extra>
      <span style="font-size: 12px; color: #7a8699">
        {{ leftFile }} ↔ {{ rightFile }}
      </span>
    </template>

    <n-space vertical size="large">
      <div>
        <div style="font-weight: 600; margin-bottom: 6px">对比模式</div>
        <n-radio-group
          :value="mode"
          name="mode"
          @update:value="emit('update:mode', $event as CompareMode)"
        >
          <n-radio-button value="diff">找不同</n-radio-button>
          <n-radio-button value="same">找相同</n-radio-button>
        </n-radio-group>
        <div style="font-size: 12px; color: #7a8699; margin-top: 6px">
          找不同:输出仅表A有 / 仅表B有 / 两边都有但值不一致的行;找相同:输出两边都存在且内容一致的行
        </div>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px">
        <div>
          <div style="font-weight: 600; margin-bottom: 6px">表 A 关键列(用于匹配行)</div>
          <n-select
            :value="leftKeys"
            multiple
            filterable
            placeholder="选择 1 个或多个,顺序与表B一一对应"
            :options="leftOptions"
            @update:value="emit('update:leftKeys', $event)"
          />
        </div>
        <div>
          <div style="font-weight: 600; margin-bottom: 6px">表 B 关键列</div>
          <n-select
            :value="rightKeys"
            multiple
            filterable
            placeholder="与表A关键列按顺序配对"
            :options="rightOptions"
            @update:value="emit('update:rightKeys', $event)"
          />
        </div>
      </div>
      <div v-if="keyCountHint" style="font-size: 12px; color: #d94030">{{ keyCountHint }}</div>

      <div>
        <div style="font-weight: 600; margin-bottom: 6px">参与比较的列(两表共有列)</div>
        <n-select
          :value="compareColumns"
          multiple
          filterable
          clearable
          placeholder="不选 = 默认比较全部共有列"
          :options="compareOptions"
          @update:value="emit('update:compareColumns', $event)"
        />
        <div v-if="!hasComparable" style="font-size: 12px; color: #d94030; margin-top: 6px">
          没有可比较的共有列:两表除关键列外没有同名列
        </div>
      </div>

      <n-space>
        <n-button @click="emit('back')">上一步</n-button>
        <n-button type="primary" size="large" :disabled="!canRun" @click="emit('run')">
          开始对比
        </n-button>
      </n-space>
    </n-space>
  </n-card>
</template>
