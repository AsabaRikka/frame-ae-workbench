# 帧场 · AE 工作台

Windows 桌面工具，用于扫描 Adobe After Effects 工程、预览原素材、添加替换候选、生成不重复组合计划，批量输出可编辑 AEP 和视频。

## 功能

- 检索源素材、预合成及文字/形状图层，名称仅辅助分类。
- 单图选择文件、序列帧选择文件夹，支持动画预览和多个替换候选。
- 生成、预览及调整组合计划，按选定计划和数量导出。
- 默认适配原尺寸；角色等比缩放，序列统一变换，背景等比铺满。
- MP4 分辨率、帧率、画质/码率、音频可配置。
- 导出队列与 AI 生成记录支持分页、搜索和折叠。
- 火山方舟生图/生视频，API 配置和密钥由使用者填写。
- 独立桌面窗口，重复启动复用窗口，有任务时阻止退出。

## 运行

Windows 10/11 x64、Python、Pillow，以及 PATH 中的 FFmpeg/FFprobe。AE 自动化主要在 AE 2022 验证，工程插件、字体和素材需另行准备。

```powershell
python -m pip install -r ae_workbench/requirements-build.txt
python ae_workbench/portable.py
```

桌面模式需要 Microsoft WebView2 和 .NET Framework 4.8。根目录 start.cmd / restart.cmd 保留浏览器开发模式，使用 8518 端口、data-v02；桌面便携版使用 data-v1。

## 使用

导入工程文件夹并扫描 → 为素材添加候选 → 生成组合计划 → 预览、调整并选择数量 → 导出。

原工程及素材不覆盖。输出 AEP 可能依赖原素材及 adapted 文件夹，移机前应使用 AE 收集文件。整组替换会替换内部动画，不允许同时替换父组合及内部素材。组合预览展示素材搭配，不是实时 AE 合成画面。

## 测试

```powershell
python -m unittest discover -s ae_workbench -p test_*.py
node --test ae_workbench/test_queues.cjs ae_workbench/test_preview_bridge.cjs
```

发布时 88 项 Python 和 5 项 Node 测试通过。桌面启动、重复启动、退出生命周期已验证；不代表所有 AE 工程、插件或 50 份视频压力测试均已通过。

## 构建

安装 requirements-build.txt 中的依赖，准备 FFmpeg/FFprobe（构建脚本需要发行包 LICENSE 和 README）。将微软官方 WebView2 x64 离线安装器放到 build/desktop-support/MicrosoftEdgeWebView2RuntimeInstallerX64.exe，核验微软数字签名后运行：

```powershell
python ae_workbench/build_release.py
```

[微软 WebView2 下载页](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

仓库仅含源码、图标、文档及测试，不含用户 AEP、原工程预览图、素材、密钥、工作区、导出记录或安装包。第三方组件遵循各自许可。
