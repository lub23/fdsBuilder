# 设施火灾热辐射建模与损伤预测系统介绍演示文稿

## 交付物

- `output/设施火灾热辐射建模与损伤预测系统介绍_20260909.pptx`：18 页可编辑中文演示文稿。
- `output/设施火灾热辐射建模与损伤预测系统介绍_20260909.pdf`：用于快速审阅的 PDF 版本。
- `assets/system_architecture.png`：系统总体架构图（独立 PNG）。
- `assets/quick_modeling_flow.png`：快速建模流程图（独立 PNG）。
- `assets/equivalent_model_logic.png`：可计算等效模型逻辑图（独立 PNG）。
- `assets/surrogate_fds_dual_track.png`：代理模型 / FDS 双轨决策流程图（独立 PNG）。
- `assets/program_main_ui.png`：程序主界面截图。
- `assets/program_3d_view.png`：由当前航空航天中型等效模型数据生成的离屏 3D 场景图。
- `assets/program_prediction_dialog.png`：真实代理模型工况预测结果界面截图。

## 截图说明

当前 Linux 容器没有 X Server。主界面使用 Qt offscreen 平台真实渲染；中央 3D 区域嵌入由同一 `BuildingGroup` 数据通过离屏渲染得到的画面。预测结果截图加载当前生产模型，并使用 `aerospace_medium / q=15000 kW/m² / a=270° / e=30° / d=2.1 s` 权威已观测工况，界面显示 Dk=0.1457 和中等破坏。

## 重新生成

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python presentation/generate_assets.py
.venv/bin/python presentation/generate_ppt.py
```

如需重新导出 PDF：

```bash
libreoffice --headless --convert-to pdf \
  --outdir presentation/output \
  presentation/output/设施火灾热辐射建模与损伤预测系统介绍_20260909.pptx
```

演示文稿数据口径采用 2026-07-15 生产快照：5479 条合格工况、36 个设施训练身份、58 维输入、75 棵回归树 + 75 棵分类树。
