# Auto boker grab 部署文档

本文档用于把当前项目部署到另一台 Windows 电脑。推荐直接使用根目录生成的部署压缩包；如果需要重新打包，也可以运行本文最后的打包命令。

## 1. 部署包内容

部署包包含：

- Python 采集脚本、Web UI、静态文件和查询模板。
- `x9_creator_desktop_system` 后端、Electron 桌面壳、浏览器 UI、迁移脚本。
- 当前 SQLite 数据库：`x9_creator_desktop_system\data\creators.sqlite`。
- Gmail OAuth 文件：`x9_creator_desktop_system\data\gmail_client_secret.json`。
- 本机配置文件：`x9_creator_desktop_system\.env`。
- TikTok 浏览器扩展 zip：`tiktok-creator-lead-browser-extension-1.0.19.zip`。
- 一键安装扩展所需的 relay 文件：`x9_creator_desktop_system\chrome-extension-relay\`。

部署包排除了可重建或无部署价值的内容：`node_modules`、`__pycache__`、`.pytest_cache`、日志目录、`.pyc`、`.log`、`.err`。

注意：部署包里包含 `.env`、SQLite 数据库和 Gmail OAuth 配置。只发给可信电脑或可信人员。

## 2. 目标电脑前置环境

目标电脑建议使用 Windows 10/11，并安装：

- Python 3.11，安装时勾选 `py launcher`。验证命令：

```powershell
py -3.11 --version
```

- Google Chrome，用于加载 TikTok 采集扩展。
- Node.js LTS，仅在需要 Electron 桌面壳时安装。只用浏览器打开后端 UI 可以不装 Node.js。

如果目标电脑要连接远程 X9 后端，请确保能访问 `.env` 中的 `REMOTE_API_URL`。当前项目默认使用局域网地址，如果换了网络，优先检查这里。

## 3. 解压部署包

建议解压到路径简单的位置，例如：

```text
C:\X9\Auto boker grab
```

后续命令都假设项目根目录是 `C:\X9\Auto boker grab`。如果你解压到别的位置，把命令里的路径替换成实际路径即可。

## 4. 安装 Python 依赖

打开 PowerShell：

```powershell
cd "C:\X9\Auto boker grab"
py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install -r requirements.txt
py -3.11 -m pip install -r x9_creator_desktop_system\requirements.txt
```

如果 `pip install` 很慢或失败，先确认目标电脑能访问 Python 包源。

## 5. 初始化数据库

数据库文件已经随包带过去了，但第一次启动前仍建议执行一次迁移。迁移是幂等的，可以重复执行。

```powershell
cd "C:\X9\Auto boker grab"
py -3.11 -m x9_creator_desktop_system.backend.migrations.001_init
```

## 6. 启动后端和浏览器 UI

```powershell
cd "C:\X9\Auto boker grab\x9_creator_desktop_system"
.\start_desktop.bat
```

启动后会打开：

```text
http://localhost:8000/ui/
```

健康检查地址：

```text
http://127.0.0.1:8000/health
```

如果 8000 端口被占用，先关闭占用 8000 的程序，或改用 Electron 启动方式。

## 7. 安装 TikTok 浏览器扩展

第一次部署到新电脑时执行：

```powershell
cd "C:\X9\Auto boker grab\x9_creator_desktop_system"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_extension_strict.ps1
```

然后在 Chrome 中打开：

```text
chrome://extensions
```

操作步骤：

1. 打开右上角 Developer mode。
2. 点击 Load unpacked。
3. 选择 `C:\X9\Auto boker grab\x9_creator_desktop_system\chrome-extension`。
4. 打开 TikTok 并登录。
5. 打开扩展侧边栏，输入关键词后开始采集。
6. 回到 `http://127.0.0.1:8000/ui/` 查看 Collection Monitor 和推荐结果。

## 8. Electron 桌面壳（可选）

只要浏览器 UI 能用，这一步可以跳过。需要桌面应用外壳时执行：

```powershell
cd "C:\X9\Auto boker grab\x9_creator_desktop_system\desktop"
npm install
npm start
```

Electron 会在 `8000-8005` 中自动找一个可用端口启动后端。

## 9. 老版 YouTube/Flask 工具（可选）

根目录还保留了旧工具：

```powershell
cd "C:\X9\Auto boker grab"
py -3.11 webui.py
```

如需 Playwright 浏览器能力，首次使用前执行：

```powershell
py -3.11 -m playwright install chromium
```

## 10. 常见问题

`py -3.11` 找不到：重新安装 Python 3.11，并确保安装了 Python Launcher。

`uvicorn` 找不到：重新执行 `py -3.11 -m pip install -r x9_creator_desktop_system\requirements.txt`。

浏览器扩展无法加载：确认已经运行 `install_extension_strict.ps1`，并选择的是生成后的 `x9_creator_desktop_system\chrome-extension` 文件夹。

UI 里扩展一直离线：确认后端正在运行，Chrome 扩展已启用，扩展权限里允许访问 `http://127.0.0.1:8000/*`。

远程数据不同步：检查 `x9_creator_desktop_system\.env` 里的 `REMOTE_API_URL` 和 `REMOTE_API_KEY`，并确认目标电脑网络能访问该地址。

Gmail 授权失败：确认 `x9_creator_desktop_system\data\gmail_client_secret.json` 存在；如果换了 OAuth 客户端，需要同步更新 Google Cloud Console 中允许的本机回调端口。

## 11. 重新打包

在源电脑项目根目录执行：

```powershell
cd "F:\AI Agent\Auto boker grab"
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_deploy_package.ps1
```

生成的 zip 在：

```text
F:\AI Agent\Auto boker grab\deploy\
```

打包完成后，终端会输出 SHA256，可用于确认传输后的文件没有损坏。
