# 帧场 · AE 工作台

Windows 桌面工具：扫描 After Effects 工程，预览原素材，添加多个替换候选，生成不重复组合计划，批量输出可编辑 AEP 和视频。

## 目录

```text
src/frame_workbench/     Python 程序
├── desktop/            桌面窗口、单实例和退出管理
├── web/                本地 HTTP 接口与任务协调
├── assets/             工程素材目录、候选导入与旧版配置兼容
├── planning/           组合生成和替换方案计算
├── media/              动画预览、尺寸适配与视频编码参数
├── ai/                 火山方舟生成任务
├── filesystem/         文件浏览和系统选择窗口
├── runtime.py          工作区路径、AE 发现与跨进程互斥
└── cli.py              源码服务的启动与重启
frontend/               页面 index.html、js/、css/
resources/              AE 脚本和程序图标
scripts/                启动、测试、打包命令
tests/                  unit/、frontend/、integration/
docs/                   架构、接手说明和使用文档
ae_workbench/           旧入口兼容与既有本机数据，不再放业务实现
build/                  构建和验证临时产物，不提交
releases/               发布 ZIP，不提交到源码仓库
```

模块职责与依赖见 [架构说明](docs/ARCHITECTURE.md)，接手开发先读 [HANDOFF](docs/HANDOFF.md)。

## 开始使用

需要 Windows 10/11 x64、Python、FFmpeg/FFprobe，以及本机可运行的 AE（主要验证 AE 2022）。桌面窗口还需 Microsoft WebView2 和 .NET Framework 4.8。工程依赖的插件、字体和素材自行准备。

```powershell
python -m pip install -r requirements.txt
python scripts/desktop.py
```

源码网页调试仍可双击 `start.cmd` / `restart.cmd`。原有中文启动入口和 `ae_workbench/portable.py` 等旧入口继续可用。

使用流程：导入工程 → 为素材添加候选 → 生成组合计划 → 预览、调整并选择数量 → 导出。
单张图片选文件，序列帧选文件夹。视频规格和 AI 生成参数在工作台设置。原工程与素材不覆盖。

## 开发与验证

```powershell
python scripts/test.py
```

此命令在临时工作区运行 Python 与 Node 测试，不读取用户工作区。`tests/integration/` 中脚本会实际驱动 AE，必须另行运行；先保存 AE 中的改动，且不要与其他扫描/渲染并发。

## 打包

```powershell
python -m pip install -r requirements-build.txt
python scripts/build_release.py
```

准备 FFmpeg/FFprobe 发行包（含 LICENSE/README），将微软官方 WebView2 x64 离线安装器放到 `build/desktop-support/MicrosoftEdgeWebView2RuntimeInstallerX64.exe`，核验数字签名后构建。详细移机要求见 [桌面使用说明](docs/user/desktop.txt)。

## 数据与边界

本次目录调整保留 `ae_workbench/data-v02`、旧 `data` 和 `outputs` 的位置；便携 EXE 继续在自身目录使用 `data-v1` 与 `outputs`。也可通过 `FRAME_WORKBENCH_HOME` 或桌面启动参数 `--data-dir` 使用独立工作区。

组合预览是素材搭配预览，不是实时 AE 成片。整组替换会替换内部动画，不可同时替换父组合与内部素材。输出 AEP 可能依赖原素材与 adapted 文件夹，移机时需要收集文件。

公开源码不含工程、素材、API 密钥、运行数据、本机历史交接或原工程预览图。后端任务协调仍有集中状态，具体边界和后续拆分方向见架构文档。
