import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

// 离线客户端专用构建:全部 JS/CSS 内联进单个 index.html,
// 由 pywebview 以 file:// 直接加载,页面通过 window.pywebview.api 调用 Python,零网络
export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  build: {
    outDir: 'dist-offline',
  },
})
