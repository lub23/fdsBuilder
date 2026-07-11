# UI 优化与冗余清理执行计划

更新时间：2026-07-09（Asia/Shanghai）

## 背景

本文件用于记录本轮 UI 优化、冗余代码清理、拆分与测试进度。若当前对话 token 不足，可在新对话中读取本文件继续执行。

## 用户确认后的执行范围

### 一、UI 优化

1. **主窗口布局适配**：按建议修改。
   - 优化窗口/分割器适配。
   - 保存/恢复 `QSplitter` 比例。
   - 改善状态栏与校验提示展示。
2. **设施面板**：按用户修订后的范围执行。
   - 不增加设施树搜索框。
   - 不增加根节点操作提示。
   - 删除位置编辑功能。
   - 不支持“重置视角到该建筑”。
   - 保留场景目标列表展示、选择/高亮、删除等必要功能。
3. **仿真控制面板日志**：按建议修改。
   - 修复 `QLabel.append` 潜在崩溃。
   - 输出区改为可滚动只读日志控件。
   - 增加复制日志、清空日志、打开输出目录等实用操作（如实现成本低且不影响现有流程）。
4. **图纸识别功能**：移除。
   - 移除 `BlueprintViewer` / OCR UI 入口和主窗口中相关引用。
   - 不再保留图纸拖放、后台识别等计划。
   - 业务层 OCR 文件可暂不删除，除非确认无外部脚本依赖。
5. **FDS 代码预览**：按建议修改。
   - 增加搜索、复制全部、保存预览等功能。
   - 保留现有预览更新能力。
6. **样式统一**：按建议修改。
   - 抽取常用按钮样式。
   - 尽量用 `objectName`/公共样式减少重复 `setStyleSheet`。

### 二、代码冗余与结构调整

1. **`ui/viewer_3d.py`**：不拆分文件。
   - 修改前先提交当前状态，方便后续回退。
   - 仅删除多余/未使用/遗留代码，简化相关重复逻辑。
   - 修改后必须确保功能不受影响。
2. **`ui/facility_panel.py`**：不拆分文件。
   - 删除冗余代码。
   - 移除位置编辑相关逻辑。
   - 保留现有核心功能。
3. **`ui/dialogs.py`**：可以拆分，按计划进行。
   - 拆分为多个对话框模块。
   - 保持原有导入兼容或更新调用方。
4. **主窗口职责清理**：按建议修改。
   - 抽取程序路径读写。
   - 抽取 FDS 文件名/CHID 生成逻辑。
   - 清理 star imports 和未使用导入。
5. **未使用导入/遗留代码清理**：按建议修改。

## 重要约束

- 不覆盖用户已有未提交修改。
- 修改 `ui/viewer_3d.py` 前先提交当前状态。
- 每完成一批修改后更新本文件状态。
- 每批修改后尽量运行相关测试；最终运行全量测试。
- 对 `viewer_3d.py` 的改动仅限冗余清理/简化，不改变可见功能。

## 当前工作区状态记录

在开始本轮修改前，工作区已有未提交改动：

- `generators/fds_generator.py`
- `models/window_flux_calibration.py`
- `scripts/sweep_rhfg_wall_flux_a0_e0.py`
- `ui/viewer_3d.py`
- `models/window_flux_calibration_data.py`（未跟踪）
- `scripts/run_facility_wall_flux_calibrations.py`（未跟踪）
- `scripts/update_window_flux_calibration_data.py`（未跟踪）

这些改动不是本轮扫描阶段产生的；按用户要求，将在修改 `viewer_3d.py` 前做安全提交快照。

## 执行进度

| 阶段 | 状态 | 说明 |
|---|---|---|
| 0. 写入计划文档 | 已完成 | 创建本文件 |
| 1. 修改前安全提交 | 已完成 | 安全提交 `be9ad63 chore: checkpoint before ui cleanup` |
| 2. 工具抽取与主窗口清理 | 已完成 | 新增 `services/program_paths.py`、`services/fds_naming.py`；主窗口改为显式导入并保存/恢复分割器状态 |
| 3. 仿真日志与 FDS 预览优化 | 已完成 | FDS 日志改为可滚动只读控件；预览面板增加搜索/复制/保存/警告展示 |
| 4. 移除图纸识别 UI | 已完成 | 删除 `ui/blueprint_viewer.py`，移除主窗口 OCR/Blueprint 引用；保留后端 `ocr/blueprint_ocr.py` 以免影响脚本 |
| 5. 设施面板冗余清理 | 已完成 | 删除位置编辑信号和行内编辑逻辑；场景表保留展示/选择/删除 |
| 6. viewer_3d 冗余清理 | 已完成 | 不拆分文件；删除 legacy 渲染/绘制私有函数和未使用导入；保留当前缓存渲染主路径 |
| 7. dialogs.py 拆分 | 已完成 | 新增 `ui/dialog_windows/` 多个模块；`ui/dialogs.py` 保持兼容导出 |
| 8. 测试与收尾 | 已完成 | `compileall`、`pytest`、offscreen UI smoke 均通过 |

## 测试基线

修改前只读扫描阶段已运行：

```text
python -m compileall -q ui models generators tests
python -m pytest -q
450 passed, 1 skipped
```

## 实时日志

- 2026-07-09：根据用户确认范围创建本执行计划。

- 2026-07-09：已完成修改前安全提交 `be9ad63 chore: checkpoint before ui cleanup`。

- 2026-07-09：完成工具抽取、主窗口清理、仿真日志修复、FDS 预览增强、图纸识别 UI 移除、设施面板位置编辑移除、`viewer_3d.py` legacy 私有渲染代码清理、`dialogs.py` 拆分。
- 2026-07-09：验证通过：`python -m compileall -q main.py services ui models generators tests`；`python -m pytest -q` → `453 passed, 1 skipped`；`QT_QPA_PLATFORM=offscreen` 组件 smoke 测试通过。
