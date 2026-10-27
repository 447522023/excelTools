# 表格对比工具 — Linux 宝塔面板部署文档

## 部署架构

```
浏览器 ──► Nginx(宝塔,80/443)──► uvicorn(127.0.0.1:8000,FastAPI)
                                          ├── /api/*   接口
                                          └── /*       前端静态页(web/dist)
```

后端单端口同时提供 API 与页面,无需单独建静态站点,Nginx 全量反向代理即可。

- 本文默认项目路径为 `/www/wwwroot/excel_tools`,不同路径请自行替换。
- 本文默认域名 `excel.example.com`,没有域名可直接用服务器 IP。

---

## 一、前置条件

| 项目 | 要求 |
| --- | --- |
| 系统 | CentOS 7+ / Ubuntu 18+ / Debian 10+ |
| 宝塔面板 | 7.x / 8.x 均可(未安装见下方命令) |
| Nginx | 宝塔软件商店安装任意稳定版(1.2x) |
| Python | 3.10+(推荐 3.12,可由宝塔 Python 项目管理器安装) |
| Node.js | 18+,**仅当选择"在服务器上构建前端"时需要** |
| 内存 | 建议 2G+(几十万行的大表格对比吃内存,1G 小机请加 swap) |

宝塔面板安装命令(已安装可跳过):

```bash
# Ubuntu / Debian
wget -O install.sh https://download.bt.cn/install/install-ubuntu_6.0.sh && bash install.sh ed8484bec

# CentOS
yum install -y wget && wget -O install.sh https://download.bt.cn/install/install_6.0.sh && sh install.sh ed8484bec
```

---

## 二、上传项目

推荐**本地先构建好前端**,再连同后端一起上传,服务器免装 Node:

```bash
# 本地(Windows)执行:
cd web
npm install
npm run build        # 产出 web/dist/
```

需要上传的服务器内容:

```
excel_tools/
├── server/           # 必须上传(不含 .pytest_cache、tests 可不上传)
│   └── downloads/    # 离线客户端安装包(页面"下载离线版"入口读取;没有可后补)
└── web/
    └── dist/         # 必须上传(本地构建产物)
```

> 后续更新离线安装包时,只需把新包(含 .sha256)放进服务器 `server/downloads/` 并删除旧包,页面入口自动刷新,无需重启后端。

上传方式任选其一:

1. 本地把上述目录打成 zip,用宝塔「文件」页上传到 `/www/wwwroot/` 并解压、重命名为 `excel_tools`;
2. 或服务器上 `git clone` 后,单独上传本地构建的 `web/dist`。

> `web/dist` 的位置很关键:后端按 `server/../web/dist` 的相对关系自动查找前端资源,请保持上面的目录结构;放别处也没关系,后面用环境变量 `EXCEL_TOOLS_STATIC_DIR` 指定即可。

---

## 三、安装后端依赖

宝塔「终端」(或 SSH)执行:

```bash
cd /www/wwwroot/excel_tools
python3 -m venv venv
./venv/bin/pip install -r server/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> - 依赖只有 7 个包(fastapi、uvicorn、pandas、openpyxl、xlrd 等),pandas 有官方 wheel,正常情况直接装上。
> - CentOS 7 等老系统若装新版 pandas 报 glibc 错误,改用宝塔「Python 项目管理器」里安装的 Python 3.12 来建 venv。
> - 若后续用宝塔 Python 项目管理器并勾选"安装依赖",本步可跳过。

---

## 四、手动试跑验证

先手动跑一次,确认服务本身没问题:

```bash
cd /www/wwwroot/excel_tools/server
../venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即成功。另开一个终端验证:

```bash
curl -I http://127.0.0.1:8000/          # 应返回 200(text/html)
curl -I http://127.0.0.1:8000/docs      # API 文档页,应返回 200
```

> 注意:必须在 `server/` 目录下启动(上面的 `cd` 不能省),后端按相对路径查找 `web/dist`。
> 验证通过后 Ctrl+C 停掉,进入下一步做常驻运行。

---

## 五、常驻运行(两种方式二选一)

### 方式 A:宝塔 Python 项目管理器(推荐)

1. 宝塔「软件商店」安装 **Python项目管理器**(宝塔 8.x 也可从「网站 → Python项目」进入);在其「版本管理」中安装 Python 3.12(若第三步已用系统 Python 装好依赖,也可直接用系统版本)。
2. 添加 Python 项目,各字段按所用版本界面对应填写:

| 界面字段 | 填写值 |
| --- | --- |
| 项目名称 | `excel_tools` |
| 路径 / 项目目录 | `/www/wwwroot/excel_tools/server` |
| Python 版本 | 3.12(或系统已装依赖的版本) |
| 框架 / 启动方式 | 选 `uvicorn` 或"命令启动" |
| 启动命令 / 模块参数 | `app.main:app --host 127.0.0.1 --port 8000` |
| 端口 | `8000` |
| 是否安装依赖 | 勾选(自动执行 `pip install -r requirements.txt`) |
| 环境变量(如有此项) | `EXCEL_TOOLS_STATIC_DIR=/www/wwwroot/excel_tools/web/dist`(目录结构标准时可不填) |

3. 启动项目,状态显示"运行中"即完成。日志可在项目管理器里直接查看。

### 方式 B:systemd(不依赖宝塔插件)

```bash
cat > /etc/systemd/system/excel-tools.service <<'EOF'
[Unit]
Description=excel-tools FastAPI service
After=network.target

[Service]
Type=simple
WorkingDirectory=/www/wwwroot/excel_tools/server
ExecStart=/www/wwwroot/excel_tools/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now excel-tools
systemctl status excel-tools      # 应为 active (running)
```

日志查看:`journalctl -u excel-tools -f`。

> 无论哪种方式,都让服务监听 `127.0.0.1:8000`,由 Nginx 对外,8000 端口不直接暴露公网。

---

## 六、宝塔建站 + 反向代理

1. 宝塔「网站 → 添加站点」:
   - 域名:`excel.example.com`(无域名填服务器 IP)
   - PHP 版本:纯静态
   - 数据库:不创建
2. 站点「设置 → 反向代理 → 添加反向代理」:
   - 代理名称:`api`
   - 目标 URL:`http://127.0.0.1:8000`
   - 发送域名:`$host`
3. **调大上传限制(重要)**:本工具要上传 xlsx/csv,宝塔/Nginx 默认上传上限通常只有 50m 甚至 1m,超出会报 413。进入站点「设置 → 配置文件」,在 `server {}` 内加入/确认以下配置后保存:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    client_max_body_size 200m;      # 允许上传的最大文件,按需调整
    proxy_request_buffering off;    # 大文件上传直接流式转发,减少等待
    proxy_read_timeout 300s;        # 大表格对比/导出耗时长,放宽超时
    proxy_send_timeout 300s;
}
```

> 如果第 2 步已用反向代理生成过配置,`location /` 会重复冲突:二选一即可 —— 要么用宝塔反代功能(默认配置一般够用,只需再补 `client_max_body_size`),要么删掉反代生成的 `location /`,直接粘贴上面整段。

4. 防火墙:宝塔「安全」及云厂商安全组只放行 `80/443`(及面板端口);确认 8000 未对公网放行。

---

## 七、HTTPS(可选但推荐)

站点「设置 → SSL → Let's Encrypt」申请证书(需已解析域名),开启「强制 HTTPS」。

---

## 八、部署验证清单

- [ ] 浏览器打开 `https://excel.example.com/`,出现"表格对比工具"页面
- [ ] 打开 `https://excel.example.com/docs`,出现 Swagger 接口文档
- [ ] 上传两个小表格 → 选工作表与关键列 → 找不同 → 导出 xlsx/csv 全流程通过
- [ ] 上传一个 50m 以上大文件不报 413(验证上传限制生效)

## 九、更新发布

```bash
# 1. 替换代码:上传新的 server/ 与 web/dist(建议先备份旧目录)
# 2. 有新依赖时:
cd /www/wwwroot/excel_tools && ./venv/bin/pip install -r server/requirements.txt
# 3. 重启服务:
systemctl restart excel-tools          # 方式 B
# 或宝塔 Python 项目管理器里点「重启」  # 方式 A
```

Nginx 配置未变时无需 reload;改过站点配置则 `nginx -t && nginx -s reload`。

---

## 十、常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 访问 502 | 后端没起来。看服务日志(方式 A 在项目管理器里看;方式 B `journalctl -u excel-tools -n 100`),常见为依赖未装全或不在 `server/` 目录启动 |
| 上传报 413 | Nginx 上传限制太小,调大第六步的 `client_max_body_size` |
| `/docs` 能打开但首页 404 / 白屏 | 后端没找到 `web/dist`。确认 `web/dist/index.html` 存在且目录结构与第二节一致;或在服务环境变量中设置 `EXCEL_TOOLS_STATIC_DIR=/www/wwwroot/excel_tools/web/dist` 后重启 |
| pip 安装 pandas 报错 | 老系统 glibc 过低,改用宝塔 Python 项目管理器安装的 Python 3.12;并确认使用国内镜像源 |
| 对比超大文件超时/内存不足 | 放宽 `proxy_read_timeout`;加 swap 或拆分文件(当前版本未做流式分块) |
| 服务器重启后服务没起来 | 方式 B 已设 `enable` 不会出现;方式 A 在项目管理器中确认项目为"开机自启" |

## 十一、运维备忘

- 上传的临时文件存于 `/tmp/excel_tools_uploads`,对比完成即无用;系统清理 `/tmp` 或重启导致目录清空属正常现象,不影响功能。磁盘紧张时可直接删该目录。
- 日志位置:方式 A 在 Python 项目管理器;方式 B 用 `journalctl -u excel-tools`。
- 备份建议:整站只需备份 `/www/wwwroot/excel_tools`(代码 + venv 可重建,核心是 `server/` 与 `web/dist`),无数据库。
