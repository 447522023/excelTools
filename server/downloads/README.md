# downloads 目录说明

该目录存放离线版安装包(页面右上角「下载离线版」入口读取本目录):

- 由 `client/build_offline.py` 在各平台构建后自动放入,命名约定
  `excel-compare-<版本>-<平台>-<架构>.exe|.tar.gz`(附同名 `.sha256` 校验文件)
- 也可用 GitHub Actions 的 `build-offline` 工作流构建后,把 artifact 手动放进本目录
- 下载量统计写在 `.stats.json`,属运行时文件,无需纳入版本库
- 目录内容不进 git;没有安装包时页面各平台显示「敬请期待」,功能不受影响
