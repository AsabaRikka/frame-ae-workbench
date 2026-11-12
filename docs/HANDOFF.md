# 开发接手说明

先读根目录 README 和 ARCHITECTURE.md，再看实际 Git 状态与服务。目录重构将业务实现移到 src/frame_workbench；frontend、resources、scripts、tests 和 docs 分层。ae_workbench 只保留兼容入口及既有本机运行数据。

主要流程：工程素材 → 多候选 → 组合计划 → 按计划选择数量 → 导出。单图选文件，序列选目录。旧三类快捷和手动配置入口已移除，旧数据处理留在 assets/legacy.py。

必须保护原工程与素材、保留用户工作区；AE 有未保存修改时停止，不能并发驱动 AE。用实际文件验证导出，不能以模拟进度报告完成。默认测试使用 scripts/test.py 的临时工作区。

路径集中在 runtime.py。源码 8518 使用 ae_workbench/data-v02，旧 data 和 8517 不迁移；桌面包使用 data-v1。脚本入口支持任意工作目录。旧 launch.py、portable.py、server.py 和 build_release.py 仅兼容转发。

公开仓库为 AsabaRikka/frame-ae-workbench，main 独立于本机旧历史。只同步审核后的当前源码，不推送本机 master 的完整历史；不要使用 push --all 或 --mirror。本机历史资料放在 docs/local（忽略），公开仓库不包含原工程封面、工作区、密钥、工程与素材。

本次结构重构已验证：92 项 Python + 5 项 Node 测试通过；旧桌面入口从任意工作目录启动通过；源码服务与全部页面资源返回正常；一键启动/重启通过；从新 ZIP 解压的 EXE 在 PATH 仅含系统目录时完成内置组件及桌面启动自检，退出码为 0。ZIP CRC 与 161 个文件清单校验一致。用户工作区 SHA-256 保持不变。完整 AE 渲染、付费 AI 调用、移机与 50 份压力测试必须单独验收，不等同于目录与启动测试。
