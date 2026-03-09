# FDS建筑模型生成器 - 完整项目交接文档

## 一、项目概述
桌面GUI应用，用于可视化配置建筑参数（**多层建筑**、墙体、开口、楼板开洞、可燃物、外部辐射热源），3D预览，导出FDS（Fire Dynamics Simulator）输入文件。
**核心目的**：通过外部强辐射热源（模拟大型强辐射源），经辐射引燃建筑内部可燃物。
**技术栈**：Python + PySide6 + PyVista(3D) + 大模型VLM(图纸OCR)
**坐标系约定**：
- 建筑模型内部：左下角为原点，X=长度(东西)，Y=宽度(南北)，Z=高度
- FDS/3D显示：建筑中心为原点，所有坐标做 `x - L/2, y - W/2` 偏移
- 3D视角：上北下南左西右东，Z朝上
## 二、文件结构

```
fds_builder/
├── main.py                          # 入口，启动MainWindow
├── models/
│   ├── building.py                  # BuildingModel（多层）、Story、FloorSlab、WallData、OpeningData
│   ├── materials.py                 # MATERIAL_LIBRARY 材料库字典
│   └── combustibles.py              # Combustible、CombustibleManager、COMBUSTIBLE_PRESETS
├── generators/
│   └── fds_generator.py             # FDSGenerator：模型→FDS文本
├── ui/
│   ├── mainwindow.py                # MainWindow：三栏布局、菜单、信号连接
│   ├── param_panel.py               # ParameterPanel：左侧参数面板
│   ├── viewer_3d.py                 # Viewer3D：PyVista 3D渲染
│   ├── fds_preview.py               # FDSPreviewPanel：右侧FDS代码预览
│   ├── blueprint_viewer.py          # 图纸上传/OCR预览
│   ├── styles.py                    # Catppuccin深色主题
│   └── dialogs.py                   # 各种编辑对话框
├── ocr/
│   └── blueprint_ocr.py             # 大模型VLM图纸识别
└── utils/
    └── helpers.py
```

## 三、核心数据结构
### 3.1 BuildingModel（`models/building.py`）

```python
class BuildingModel:
    chid: str = "building"
    length: float          # X方向（东西）
    width: float           # Y方向（南北）
    wall_thickness: float
    
    stories: List[Story]   # 多层列表，核心结构
    roof: dict             # {"thickness": 0.2, "material": "CONCRETE"}
    
    materials: dict        # {"walls": "CONCRETE", "floor": "CONCRETE", "roof": "CONCRETE"}
    heat_source: dict      # {"enabled", "location", "distance", "radiation_flux", "use_ramp", "ramp_points"}
    simulation_time: float
    domain: dict           # {"padding": 5.0, "mesh_cells": [80, 60, 40]}
    output: dict           # {"slices": True, "devices": True}
```

**关键方法**：
- `update_z_offsets()`：计算每层z_bottom
- `update_external_walls()`：为每层生成4面外墙
- `add_story() / remove_story()`：层管理
- `to_dict() / from_dict()`：序列化，兼容旧单层格式（无stories字段时自动转单层）
- `total_height` 属性：所有层高之和
- 兼容属性：`walls / openings / combustible_mgr / height` 代理到stories[0]或total_height
### 3.2 Story
```python
@dataclass
class Story:
    name: str = "1F"
    height: float = 3.0           # 层高
    walls: List[Dict]             # 墙体列表（含外墙+内墙）
    openings: List[Dict]          # 开口列表
    combustibles: CombustibleManager
    floor_slab: FloorSlab         # 楼板（含开洞）
    
    # 运行时计算
    z_bottom: float               # 由update_z_offsets注入
    z_top: float                  # = z_bottom + height
```
### 3.3 墙体数据（Dict格式）
```python
wall = {
    "name": "南墙",
    "x1": 0, "y1": 0,       # 起点（模型坐标，左下角原点）
    "x2": 20, "y2": 0,      # 终点
    "thickness": 0.25,
    "height": 3.0,           # 通常=层高
    "is_external": True,     # 外墙不可删除
}
```
**墙体角落处理规则**：
- 水平墙（南北）：两端各延伸 thick/2（包住角落）
- 垂直墙（东西）：两端各缩进 thick/2（夹在水平墙之间）
- 地板/屋顶：与外墙外边缘齐平（±L/2±t/2）
### 3.4 开口数据（Dict格式）
```
opening = {
    "wall_index": 0,         # 所属墙在story.walls中的索引
    "type": "door",          # door / window
    "position": 0.5,         # 沿墙的相对位置 0~1
    "width": 1.2,
    "height": 2.1,
    "z_bottom": 0.0,         # 相对本层地板
}
```
### 3.5 FloorSlab
```
@dataclass
class FloorSlab:
    thickness: float = 0.2
    material: str = "CONCRETE"
    openings: List[Dict]     # 楼板开洞（层间连通）
    # 每个: {"x": 5, "y": 3, "length": 2, "width": 2, "name": "楼梯间"}
```
### 3.6 可燃物系统（`models/combustibles.py`）
```
@dataclass
class Combustible:
    id: str                  # 自动生成 CB_xxxxxx
    preset_key: str          # WOOD_TABLE, FABRIC_SOFA 等
    name: str
    x, y, z: float           # 位置（模型坐标，左下角原点）
    length, width, height: float
    hrrpua: float            # kW/m²
    ignition_temp: float
    color: str
    matl: dict               # 热物性参数

class CombustibleManager:
    items: List[Combustible]
    # 批量生成
    generate(preset_key, count, method, room_length, room_width, ...)
    # 6种分布方式
    DistributionMethod: UNIFORM_GRID, RANDOM, ALONG_WALLS, CLUSTERED, DIAGONAL, RING
```

**COMBUSTIBLE_PRESETS** 内置8种：WOOD_TABLE, WOOD_CHAIR, FABRIC_SOFA, BOOKSHELF, PLASTIC_BIN, CARDBOARD_BOX, MATTRESS, CURTAIN
**可燃物坐标**：存储时用模型坐标（左下角原点），3D显示和FDS生成时做 `-L/2, -W/2` 偏移。
**沿墙分布算法**：物体紧贴建筑内墙面，考虑wall_thickness，最终裁剪确保不超出interior空间。
### 3.7 材料库（`models/materials.py`）
```
MATERIAL_LIBRARY = {
    "CONCRETE": {"DENSITY": 2200, "CONDUCTIVITY": 1.4, "SPECIFIC_HEAT": 0.84, "COLOR": "#808080"},
    "STEEL": {...},
    "BRICK": {...},
    "WOOD": {...},
    # ...
}
```
## 四、UI层
### 4.1 MainWindow（`ui/main_window.py`）
三栏Splitter布局：
- 左：ParameterPanel（滚动面板）
- 中：3D预览（顶部工具栏含楼层复选框 + Viewer3D）
- 右：FDSPreviewPanel
**菜单**：新建、打开JSON配置、保存配置、导出FDS文件
**关键方法**：
- `update_preview()`：调用 `param_panel.get_model()` → `viewer_3d.update_model()` → `FDSGenerator.generate()` → `fds_preview.update_code()`
- `open_config()`：JSON → `BuildingModel.from_dict()` → `param_panel.set_model()` → `_rebuild_story_checks()` → `update_preview()`
- `_rebuild_story_checks()`：根据model.stories重建楼层复选框
- `_toggle_story(index, visible)`：控制 `viewer_3d.visible_stories` 集合
**关键信号连接**：
- `param_panel.parameters_changed → _on_param_changed`：同步刷新3D+FDS
- `param_panel.stories_changed → _rebuild_story_checks`：重建楼层复选框
- `blueprint_panel.dimensions_extracted → _apply_ocr_result`：应用OCR结果
**工具栏**：刷新3D按钮（左）、重置视角按钮、楼层复选框、屋顶复选框
### 4.2 ParameterPanel（`ui/param_panel.py`）
使用 `CollapsibleGroup`（可折叠QGroupBox）组织：
1. **📐 几何/材料**：2行GridLayout，长宽墙厚+3个材料下拉
2. **🧱 墙体**：工具栏(生成/编辑/删除) + QTableWidget，列=[类型,名称,起点,终点,厚度]
3. **🚪 开口(门/窗/楼梯口)**：同上，列=[类型,所属,位置/XY,宽×高,底高]，楼梯口选择时"所属墙"禁用显示灰色
4. **🪵 可燃物**：管理按钮 + 只读预览表格 + 计数标签
5. **☀️ 外部热源**：启用复选框 + 可隐藏选项区（方位/距离/热通量/时间曲线）
6. **⚙️ 模拟/输出**：时间/边距/网格/切片/测量点
**关键机制**：
- `_syncing` 标志位防止 `setValue` 触发 `valueChanged` 信号回写模型
- `sync_ui_from_model()`：设 `_syncing=True`，批量setValue，finally恢复
- `sync_model_from_ui()`：读取所有控件值写入model
- `_current_story_index`：当前编辑的层
- `_current_story()`：返回当前层Story对象
- 所有墙体/开口/可燃物操作都基于当前层
- `_table_item(text)`：创建带tooltip的只读QTableWidgetItem
- `_make_table(columns, col_widths)`：统一表格样式（深色交替行、固定列宽）
**信号**：`parameters_changed`、`wall_selected(int)`、`opening_selected(int)`
### 4.3 Viewer3D（`ui/viewer_3d.py`）
PyVista + pyvistaqt.QtInteractor
**update_model(model)** 流程：
1. `plotter.clear()`
2. 遍历 `model.stories`，跳过 `visible_stories` 中不包含的层
3. 每层画：楼板（用深色半透明填充+红边框表示） → 墙体 → 开口 → 可燃物
4. 画屋顶（最顶层上方一次）， 画热源、原点标记
5. 刷新保持视角：非首次渲染只调用`reset_camera_clipping_range()`
- `visible_stories: Set[int]`：可见的层索引
- `show_roof: bool`：是否显示屋顶
- `_first_render: bool`：首次渲染标志，用于保持后续刷新不改视角
**_add_opening** 签名：`(opening, story, L, W, t, z0)` — 用story.walls取墙，z_bottom加z0偏移
**wall_actors/opening_actors**：存为 `(story_index, actor)` 元组，支持高亮
**draw_origin_marker**：建筑左下角画RGB轴线+白球
**setup_camera**：从南偏上方看，camera_position = `(0, -d, d*0.6)` 看向 `(0, 0, cz)`

### 4.4 Dialogs（`ui/dialogs.py`）
- `OpeningDialog`：单个开口编辑
- `WallDialog`：单个墙体编辑
- `FloorSlabHoleDialog`：楼板开洞编辑
- `BatchOpeningDialog`：批量开口（支持门/窗/楼梯口三种类型）
- `BatchWallDialog`：批量内墙
- `CombustibleDialog`：可燃物管理
- `RampEditorDialog`：热源时间曲线编辑
## 五、FDS生成（`generators/fds_generator.py`）
### 生成顺序
```
&HEAD CHID=...
&TIME T_END=...
&REAC FUEL='CELLULOSE' ...         ← 有可燃物时必须
&MESH ...
&MATL (墙体/地板/屋顶材料)
&SURF (WALL/FLOOR/ROOF + 每层FLOOR_xxF)

每层循环:
  楼板 &OBST + &HOLE(楼板开洞)
  墙体 generate_wall()（含开口切分）
  可燃物 &OBST (用SURF_IDS，底面INERT)

屋顶 &OBST

可燃物:
  &MATL (纯热物性，不含燃烧参数)
  &SURF (含HRRPUA，不含IGNITION_TEMPERATURE)
  &OBST (坐标做-L/2,-W/2偏移)

外部热源:
  &SURF EXTERNAL_FLUX=...
  &OBST (面源)
  &RAMP (可选时间曲线)

&SLCF / &BNDF / &DEVC (输出)
&TAIL
```
### 热辐射引燃原理（目前暂时没有完美实现）
1. 外部热源用 `TMP_FRONT` 设置表面高温或辐射强度
2. 热量通过墙体开口（门窗）辐射和传导传入建筑内部
3. 可燃物表面温度升至 `IGNITION_TEMPERATURE`（250℃）时着火
4. 着火后按 `HRRPUA` 释放热量
### generate_wall 核心逻辑
处理开口切分：
1. 收集所有高度分割点 `z_splits = [0, wall_h, z_bottom, z_top of each opening]`
2. 对每个高度段，沿墙方向切分为"墙段"和"开口段"
3. 只对非开口段生成 `&OBST`
4. 水平墙两端 ±thick/2，垂直墙两端 ∓thick/2（角落处理）
### 坐标偏移
所有FDS坐标 = 模型坐标 - (L/2, W/2)，z保持不变（多层时z=z_bottom+局部z）
## 六、OCR识别（`ocr/blueprint_ocr.py`）
### 功能
用大模型VLM识别建筑平面图，提取墙体/开口/楼板开洞，输出BuildingModel.from_dict兼容格式。
```
class BlueprintRecognizer:
    def __init__(self, api_key, model="google/gemini-2.5-flash-preview")
    def recognize(file_path) -> dict  # 返回BuildingModel兼容的dict
    def get_summary() -> str
```
### PROMPT要点
- 支持多层图纸识别
- 输出stories数组，每层含walls/openings/floor_slab.openings
- 外墙由模型自动生成，OCR只返回内墙
- wall_index需要重映射（外墙排前4位）
### _to_model_dict
- 遍历stories数组
- 分离内外墙（外墙丢弃，由模型自动生成）
- 重映射opening的wall_index
- 解析floor_slab.openings（楼梯口）
## 七、JSON配置格式
```json
{
  "chid": "building",
  "length": 29.2,
  "width": 56.5,
  "wall_thickness": 0.24,
  "stories": [
    {
      "name": "1F",
      "height": 4.0,
      "walls": [],
      "openings": [{"wall_index":0,"type":"door","position":0.5,"width":1.2,"height":2.1,"z_bottom":0}],
      "combustibles": [],
      "floor_slab": {"thickness":0.2,"material":"CONCRETE","openings":[]}
    },
    {
      "name": "2F",
      "height": 3.5,
      "walls": [],
      "openings": [],
      "combustibles": [],
      "floor_slab": {"thickness":0.2,"material":"CONCRETE",
                     "openings":[{"x":8,"y":6,"length":3,"width":3,"name":"楼梯间"}]}
    }
  ],
  "roof": {"thickness":0.2,"material":"CONCRETE"},
  "materials": {"walls":"CONCRETE","floor":"CONCRETE","roof":"CONCRETE"},
  "heat_source": {"enabled":true,"location":"north","distance":3.0,"temperature":800.0,"use_ramp":true,"ramp_points":[[0,0],[60,1],[300,1]]},
  "simulation_time": 300,
  "domain": {"padding":5.0,"mesh_cells":[80,60,40]},
  "output": {"slices":true,"devices":true}
}
```
## 八、已解决的关键问题

| 问题               | 解决方案                                  |
| ---------------- | ------------------------------------- |
| FDS REAC报错       | 使用内置燃料名`METHANE`                      |
| FDS QUANTITY名称错误 | 用`TEMPERATURE`/`HRRPUV`等内置量           |
| 热源类型             | `TMP_FRONT`+`RAMP_T` 模拟高温表面           |
| 可燃物引燃            | `IGNITION_TEMPERATURE=250` + `HRRPUA` |
| 楼板开洞显示           | 深色填充+红边框                              |
| OCR不支持多层         | PROMPT改为stories数组格式                   |
## 九、当前待完善
1. 内墙在多层间的独立配置：目前每层独立，复制层时需墙体布局，包括门窗
2. 可燃物分布算法：沿墙分布时需考虑wall_thickness，有冲突时需要去掉有冲突的可燃物，并提示用户。
3. 可计算等效模型：加入一个功能模块，需要用户读取相关数据（设计一个适当合理的方式，用户需要提前配置好相关的数据，比如指定区域工业设施，包含不同类别，航空航天设施、机场机库、机械加工设施，冶金设施，每种类别下设不同目标，比如航空航天设施又包含大型火箭制造厂（又包含子目标比如总装车间、部装车间、加工厂房等），其他类似，每个子目标会有比如长宽高、门窗数量等基本信息，可燃物后续会添加，但一开始可以先考虑建筑模型，用户在软件中可以选择不同类别、目标下的子目标，然后可以直接根据参数生成一个简化的可计算等效模型。
4. FDS集成，后续考虑在软件中可以直接调用系统安装好的FDS程序跑模拟，然后在3d预览区也同步调用smokeview，当然需要用户提前配置好程序的位置。