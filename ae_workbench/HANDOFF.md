# 开发接手说明 · V1.1.0

入口：desktop.py / portable.py；本地 API：server.py；AE 脚本：bridge.jsx；前端：static。
工程素材 → 多候选 → 组合计划 → 按选定计划导出。旧三类快捷入口已移除。
源码浏览器模式使用 data-v02；便携版或显式 FRAME_WORKBENCH_HOME 使用 data-v1。
保护原工程、素材和已有工作区；AE 有未保存修改时停止自动化，不并发驱动 AE。
公开仓库从已检查的源码快照开始，不包含本机历史资料。不要添加用户工作区、密钥或原素材。
88 项 Python 和 5 项 Node 测试已通过。桌面自检与生命周期已验证；完整 AE 渲染、付费 API、移机和批量压力测试需独立验收。
