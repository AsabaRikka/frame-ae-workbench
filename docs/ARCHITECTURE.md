# 结构与模块边界

## 程序如何启动

桌面入口 `scripts/desktop.py` 加载 `desktop/launcher.py`。启动器确认工作区和单实例锁，创建本地服务，由 `desktop/window.py` 显示 WebView2 窗口。页面从 `frontend/` 加载，通过本机 HTTP 调用 `web/server.py`。

网页开发入口 `scripts/launch.py` 使用 `cli.py`，通过 `scripts/serve.py` 启动同一个 HTTP 服务。`start.cmd`、`restart.cmd` 及旧目录入口仅转发，不各自实现一套启动逻辑。

## 职责与依赖

| 模块 | 负责 | 不应该负责 |
|---|---|---|
| desktop | 窗口、单实例、退出保护、系统窗口关联 | 组合算法、视频编码规则 |
| web/server.py | HTTP、工作区状态、请求验证、扫描与导出任务协调 | 扫描候选文件细节、随机组合计算 |
| assets/library.py | 单文件导入、序列分组、候选元数据 | HTTP 和当前工程全局状态 |
| assets/catalog.py | 全工程素材清单、父子组合冲突检查、预览整理 | 桌面窗口生命周期 |
| assets/legacy.py | 旧三类配置的数据兼容 | 新增用户入口 |
| planning/combinations.py | 不重复组合、确定替换方案 | 读取 web/server 的全局 STATE |
| media | 序列与动画预览、尺寸适配、编码参数 | 窗口和 API 密钥 |
| ai/generation.py | 方舟请求、密钥保护、生成任务与结果 | AE 图层替换 |
| filesystem | 文件系统浏览、原生目录对话框 | 业务组合规则 |
| runtime.py | 稳定路径、AE 发现、进程启动、AE 全局互斥 | 页面展示 |
| resources/ae/bridge.jsx | 在 AE 中扫描、替换、保存和渲染 | 操作浏览器或 AI API |

业务模块通过参数接收数据，不反向导入 `web.server`。server 为旧调用保留少量函数入口，实际计算委托给业务模块。前端 JS 按 catalog、combinations、queues、media、environment 等功能划分；CSS 与 JS 分目录，未引入新的前端构建工具。

## 路径约定

- `runtime.PROJECT_ROOT`：源码仓库根目录。
- `runtime.RESOURCE_ROOT`：源码根目录；冻结后为 PyInstaller 解包资源目录。
- `runtime.FRONTEND / BRIDGE / ICON`：唯一的静态资源定位入口。
- `runtime.APP_HOME / WORK_HOME`：数据位置，与代码位置分离。
- 原 `ae_workbench/data-v02` 和输出路径保持不变。不要通过移动数据目录来完成代码重构。
- PyInstaller 收集 `frontend`、`resources/ae`、`resources/icons` 和运行组件，不能把本机数据或 `docs/local` 打入包。

## 修改入口

新增候选识别修改 assets；修改组合算法修改 planning；调整尺寸或视频规格修改 media；更换 AI 供应商修改 ai；页面交互修改 frontend；AE 脚本行为修改 resources/ae。相应验证放到 tests/unit 或 tests/frontend。需要真实 AE 的验证放到 tests/integration，不纳入默认测试。

`scripts/test.py` 为测试和子进程注入 src 路径及临时工作区。源码无需依赖当前工作目录，程序入口统一通过 scripts 执行。桌面包使用独立资源布局，不依赖外部 src 目录。

## 仍然存在的技术债

`web/server.py` 仍承担工程持久化、请求分发和 AE 导出任务协调，尚未完全拆成 repository、queue、routes 等组件。本次先建立包边界并分离候选读取及组合计算，保持现有任务锁和导出行为；后续拆任务服务时须验证重试、退出、跨工程状态与输出校验，不能只移动函数。

前端仍使用已有的全局状态与脚本加载顺序。没有把这次目录整理描述成完整架构重写，也没有引入微服务或新的 UI 框架。
