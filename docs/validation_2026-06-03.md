# X9 整理性修复验收记录 - 2026-06-03

## 范围

本次执行范围是整理性修复：只更新文档、系统边界说明、构建部署说明和验收清单。

未修改业务逻辑、API、数据库 schema、前端路由、页面布局、颜色、交互或可见文案。当前工作区已有的 email-auto 相关未提交改动保持原样,并作为当前系统状态参与验收。

## 自动化检查

| 检查项 | 结果 | 说明 |
|---|---|---|
| `py -3.11 -m pytest desktop\backend\tests -q` | FAIL | 125 passed, 1 failed。失败项见下方。 |
| `web` TypeScript + Vite build | PASS | 当前 PATH 没有 `npm`,使用 `web\node_modules\.bin\tsc.cmd -b` + `vite.cmd build` 等价执行。 |
| `web-user` TypeScript + Vite build | PASS | 当前 PATH 没有 `npm`,使用 `web-user\node_modules\.bin\tsc.cmd -b` + `vite.cmd build` 等价执行。 |

失败项：

- `desktop/backend/tests/test_outreach.py::test_outreach_lock_blocks_other_user_and_expires`
- 断言位置：`test_outreach.py:473`
- 现象：用户 A 锁定 creator 后,用户 B 的 creator 列表仍返回该 creator。
- 分类：需下一轮功能修复的问题；不是本次文档整理导致。
- 本轮处理：按“只做整理”范围记录,不改业务代码。

## 本地服务 smoke

| 检查项 | 结果 | 说明 |
|---|---|---|
| PostgreSQL | PASS | `x9-postgres` running and healthy, `127.0.0.1:15432->5432`。 |
| Desktop health | PASS | `http://localhost:8000/health` -> 200。 |
| Desktop login page | PASS | `http://localhost:8000/login` -> 200。 |
| Admin root | PASS | `http://localhost:8000/` -> 303,无登录态时重定向到登录流程。 |
| Portal root | PASS | `http://localhost:8000/portal/` -> 303,无登录态时重定向到登录流程。 |
| Auth status | PASS | `http://localhost:8000/api/local/auth/me` -> 200,`logged_in=false`。 |
| Protected dashboard | PASS | `http://localhost:8000/api/local/dashboard/unified` -> 401,无登录态下受保护。 |
| Core root | FAIL | `http://localhost:18765` -> 000。`start_all.ps1 -StartCore -NoBrowser` 提示 core 未在 60 秒内 ready。 |
| Core import | PASS | `py -3.11 -c "import app.main"` 在 `core/` 下通过。 |

Core 说明：本轮未修改 Core 代码。Core 不能 ready 属于当前环境/服务启动问题,需下一轮单独排查启动命令、虚拟环境、端口和运行日志。

## 线上公开 smoke

未提供线上测试账号,因此登录后的角色页面和受保护 API 只验证到公开/未登录行为。

| 检查项 | 结果 | 说明 |
|---|---|---|
| `https://usx9.us/health` | PASS | 200,返回 `service=x9_creator_desktop_system`。 |
| `https://usx9.us/login` | PASS | 200。 |
| `https://usx9.us/api/local/auth/me` | PASS | 200,`logged_in=false`。 |
| `https://usx9.us/api/local/extension/download` | PASS | 200。下载 zip 可解压,存在 `manifest.json`,共 15 个文件。 |
| `https://usx9.us/api/local/foreign-trade/dashboard` | PASS | 401,无登录态下受保护。 |
| `https://usx9.us/api/local/recommendations` | PASS | 401,无登录态下受保护。 |
| `https://usx9.us/api/local/outreach/tracking` | PASS | 401,无登录态下受保护。 |

## 受限项

- 未提供线上测试账号,未覆盖登录后的 `/a/*`、`/c/*`、`/d/*`、`/portal/*` 角色页面。
- 未发送真实邮件。
- 未执行真实批量采集。
- 未写入线上业务数据。
- 当前 shell 无 `npm` 命令；前端 build 已通过本地 `node_modules/.bin` 里的 `tsc` 和 `vite` 验证。

## 下一步建议

1. 单独修复 outreach lock 可见性问题,使锁定 creator 对其他用户隐藏并让失败测试通过。
2. 单独排查 Core `:18765` 启动 readiness,补充可读日志或健康检查。
3. 提供覆盖超管、公司管理员、部门管理员、部门用户的测试账号后,补跑线上登录态 smoke。
