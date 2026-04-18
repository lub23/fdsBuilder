# UI / 3D 刷新 / 热源重构设计（2026-04-19）

## 背景与目标

针对 7 条用户反馈修复 UI 与 3D 预览的若干问题，并优化建筑生成/刷新性能。实测 JSON 加载（~2ms）、模型构造（<1ms）、FDS 生成（~3ms）均非瓶颈；真正的性能问题集中在 3D 渲染（pyvista 每次 `clear()` + 重建数十到数百个 `pv.Box` actor）以及逻辑上的**双重刷新**（`update_preview()` 和 `refresh_3d()` 都会调 `viewer_3d.update_model()`）。

本设计将 3D 渲染从"全量整体刷新"重构为"按组分段刷新 + mesh bundle 内存缓存"，同时修复一批具体 bug 并简化面板布局。

## 一、3D 增量刷新架构

### 1.1 actor 分组

`Viewer3D` 新增按类别的 actor 组管理：

```python
self._actor_groups: dict[str, list] = {
    "buildings": [],     # 墙/防火墙/开口/屋顶（几何固定，随建筑缓存）
    "combustibles": [],  # 可燃物 + 专用组件
    "heat_source": [],   # MESH 面上的热源着色板
    "slices": [],        # 切片平面
    "devices": [],       # 测量点球体
    "origin": [],        # 原点坐标轴
}
```

每个组的清空用 `self.plotter.remove_actor(a)` 逐个移除，而非 `plotter.clear()`。

### 1.2 公开更新接口

`Viewer3D` 暴露 4 个入口：

| 方法 | 行为 |
|---|---|
| `update_model(bg)` | 全量：调用下面三个，并重置相机（若 `_first_render`） |
| `update_buildings(bg)` | 仅刷 `buildings` + `combustibles`（走缓存） |
| `update_heat_source(bg)` | 仅刷 `heat_source` 组 |
| `update_slices_devices(bg)` | 仅刷 `slices` + `devices` 组 |

### 1.3 信号路由

`SimulationControlPanel.parameters_changed` 改为 `Signal(str)`，值为事件种类：

| kind | 触发源 | mainwindow 路由到 |
|---|---|---|
| `"heat_geom"` | azimuth / elevation 提交 | `update_heat_source` + `update_preview` |
| `"heat_flux"` | net_heat_flux / duration | 仅 `update_preview`（FDS 文本） |
| `"sim"` | simulation_time / grid_size | 仅 `update_preview` |
| `"slice_device"` | 切片/测量点开关 / 自定义行变化 | `update_slices_devices` + `update_preview` |

注：`grid_size` 影响 MESH 大小，理论上会改变热源面位置；但此变化视觉上极小，且调整网格是低频操作，先只走 FDS 更新，不刷 3D。

### 1.4 消除双重刷新

- `mainwindow.update_preview()` **移除** `self.viewer_3d.update_model(model)` 调用——仅负责生成 FDS 文本 + 更新状态栏。
- `mainwindow._on_sim_param_changed(kind)` 根据 `kind` 分派到对应的 3D 更新方法。
- 现有所有"`update_preview()` + `refresh_3d()`"连续调用站点（`new_project` / `open_config` / `_apply_ocr_result` / `_on_facility_selected` / `_on_building_added` / `_on_scene_building_removed` / `_on_scene_building_offset_changed`）改为只调 `refresh_3d(first_render=?)` + `update_preview()`，语义清晰且仅一次渲染。

## 二、热源重构

### 2.1 参数模型精简

`BuildingGroup.heat_source` 默认结构改为：

```python
{
    "azimuth": 0,         # 0-360°, 步长 5°
    "elevation": 0,       # {0, 30, 45, 60}
    "net_heat_flux": 20,  # kW/m² （从 W/m² 改为 kW/m²）
    "duration": 1.36,     # s
}
```

**移除字段**：`enabled`、`distance`、`width_ratio`、`height_ratio`、`location`、`use_ramp`。`BuildingGroup.from_dict` 对旧字段做一次性迁移：若存在 `net_heat_flux` 且数值 > 1000，视为 W/m² 旧值并 /1000 转到 kW/m²。

热源始终启用（不再有开关），取消了能见面板，内容直接显示。

### 2.2 通量分解：`heat_source_face_fluxes`

新增模块函数 `models/heat_source.py::face_fluxes(azimuth, elevation, Q_kwm2) -> dict[str, float]`：

```python
def face_fluxes(azimuth: float, elevation: float, Q: float) -> dict[str, float]:
    a = azimuth % 360
    quadrant = int(a // 90)          # 0..3
    rem = math.radians(a % 90)
    e = math.radians(elevation)
    cos_e, sin_e = math.cos(e), math.sin(e)

    # 象限 → (primary_face, secondary_face) 顺时针
    faces = [("YMAX", "XMAX"), ("XMAX", "YMIN"),
             ("YMIN", "XMIN"), ("XMIN", "YMAX")][quadrant]

    result = {}
    p = Q * cos_e * math.cos(rem)    # primary
    s = Q * cos_e * math.sin(rem)    # secondary
    if p > 1e-9:
        result[faces[0]] = p
    if s > 1e-9:
        result[faces[1]] = s
    if sin_e > 1e-9:
        result["ZMAX"] = Q * sin_e
    return result
```

单位测试覆盖 azimuth ∈ {0, 45, 90, 135, 180, 270, 360} × elevation ∈ {0, 30, 45, 60}；验证 primary+secondary 在 azimuth=0/90/180/270 时退化为单面；elevation=0 时无 ZMAX 分量。

### 2.3 3D 渲染：MESH 面着色

在 `_compute_mesh()` 返回的 domain `(x0, x1, y0, y1, z0, z1)` 上，为每个有分量的面画一个 `pv.Plane`：

- 面中心、法向量、`i_size`/`j_size` 根据面名推导
- 颜色从黄（低通量）到红（高通量）线性插值，归一化到该次显示中的 `max(flux)` 或一个固定上限（20 kW/m²）
- `opacity=0.35`，不遮挡建筑
- actor 归入 `_actor_groups["heat_source"]`

### 2.4 FDS 生成器更新

`_generate_heat_source()` 改为：

```python
fluxes = face_fluxes(azimuth, elevation, Q_kwm2)
for face_name, flux_kw in fluxes.items():
    # 将 MESH XB 对应面的 XB 坐标夹紧到该面（其他轴相等）
    xb = make_face_xb(domain, face_name)
    # FDS 的 NET_HEAT_FLUX 单位也用 kW/m²（FDS 原生单位是 kW/m²，先前 UI W/m² 是 bug）
    lines.append(f"&VENT XB=..., SURF_ID='HEAT_SOURCE_{face_name}', "
                 f"NET_HEAT_FLUX={flux_kw:.2f}, COLOR='ORANGE' /")
```

移除旧的 `face_map = {0: "YMAX", 90: "XMIN", ...}` 单面逻辑和 `distance`/`width_ratio`/`height_ratio` 相关几何计算（含 `_compute_mesh` 里对 domain 的扩展——改为按实际 MESH bbox，不再因热源 distance 扩展）。

CHID 后缀保留 `q{flux}_a{az}_e{el}_d{dur}_t{sim}`，但 `flux` 改为 kW/m² 整数。

### 2.5 UI 重构

`SimulationControlPanel._build_heat_section` 新布局（2 行 × 4 列）：

```
方位角: [━━━●━━━━ 5° 步进 slider] [度数 + 方位标签]  俯仰角: [0/30/45/60 snap]
热通量: [SpinBox kW/m²]                                持续:   [SpinBox s]
```

移除 `heat_enabled_check`、`heat_distance_spin`、`heat_width_ratio_spin`、`heat_height_ratio_spin`、`heat_options` 可见性切换。

### 2.6 双侧滑块的 azimuth UX

azimuth 在 0/90/180/270 正值时对应单面；其它角度双面分布。滑块上的刻度保持 45° tick interval，label 额外显示当前分配：

```
120° (XMAX 87%, YMIN 50%)
```

（显示百分比是"占 Q 的比例"，用户可一眼看到分配；仅 label 文字，不影响逻辑。）

## 三、其他修复

### 3.1 默认值（Bug 3）

- `BuildingGroup.simulation_time` dataclass 默认值：60 → **600**
- `BuildingGroup.domain` dataclass 默认值：`{"padding": 5.0, "mesh_cells": [80, 60, 40]}` → `{"padding": 5.0, "grid_size": 1.0}`（沿用 `_compute_mesh` 已经用的 `grid_size` 字段）
- `SimulationControlPanel.sim_time_spin` 初始值：60 → 600
- `SimulationControlPanel.grid_size_spin` 初始值：0.5 → 1.0

### 3.2 FDS 仿真执行按钮布局（Bug 4）

`_build_simulation_run_section` 重写：

```
🔥 FDS 仿真执行
[▶️ 运行] [⏹️ 停止] [🔍 查看] [⚡ 预测]    ← 等宽 QHBoxLayout，每按钮 height=30
状态: 就绪                                    ← 单行 progress_label
(output 最后 2 行，灰色小字)                  ← output_text（maxHeight 40）
```

按钮颜色：运行绿、停止红、查看蓝、预测黄。状态机：
- 未运行：运行 enabled，停止 disabled，查看 disabled，预测 enabled
- 运行中：运行 disabled，停止 enabled，查看 enabled（仿真产生 smv 后），预测 enabled

### 3.3 可燃物对话框空白（Bug 5）

`FacilityListPanel._open_combustible_dialog` 从 `FacilityManager` 动态拉取当前建筑的 FC 列表：

```python
facility = self._params["facility"]
building_name = self._params["building"]
ftype = self._params["type"]

if ftype == "specialized":
    bdata = self.facility_manager.get_building_data(facility, building_name)
    fcs = []
    for s in bdata.get("stories", []):
        fcs.extend(s.get("fire_compartments", []))
else:  # equivalent
    params_full = self.facility_manager.default_params(facility, building_name)
    bld = self.facility_manager.load_equivalent(facility, building_name, params_full)
    fcs = []
    for s in bld.stories:
        fcs.extend([fc.to_dict() for fc in s.fire_compartments])

dlg = CombustibleSelectionDialog(
    self, self._params.get("combustible_selections", {}),
    fire_compartments=fcs,
)
```

不再依赖 `self._params["fire_compartments"]`（该字段从未被写入，导致旧代码总是拿到空列表）。

### 3.4 移除快捷工具栏（Bug 6）

`MainWindow.setup_toolbar()` 整体删除，`__init__` 中的 `self.setup_toolbar()` 调用也删。菜单栏保留，功能未减少。

### 3.5 门窗面板高度（Bug 6）

`FacilityListPanel.setup_ui` 中：

- `self._door_win_tabs.setFixedHeight(180)` → `setMaximumHeight(130)`
- Tab 内 `QGridLayout.setSpacing(2)` 保持；`setContentsMargins(2,2,2,2)` 保持
- 输入框 `setFixedHeight(30)` → `setFixedHeight(26)`

整体从 180px → ~125px，视觉更紧凑。

## 四、3D Mesh 内存缓存（Bug 7）

### 4.1 缓存结构

```python
@dataclass
class BuildingMeshBundle:
    walls: pv.PolyData          # 4 面外墙 + 防火墙合并后的 PolyData
    openings: pv.PolyData       # 所有外部 + 内部开口合并
    roofs: pv.PolyData          # 各层屋顶合并
    combustibles: pv.PolyData   # 所有可燃物 + 专用组件合并
    actors: dict[str, object]   # 激活后的 actor 句柄，用于 remove/show/hide
```

```python
class Viewer3D:
    self._building_cache: dict[tuple, BuildingMeshBundle] = {}
```

### 4.2 缓存键

`_building_signature(building: Building) -> tuple`：

```python
def _story_sig(s):
    return (
        s.name, s.height,
        tuple((o.wall, o.type, tuple(o.boundary)) for o in s.openings),
        tuple(_fc_sig(fc) for fc in s.fire_compartments),
        (s.roof.thickness, s.roof.material),
    )

def _fc_sig(fc):
    return (
        fc.name, tuple(fc.boundary), fc.firewall_thickness,
        tuple((o.wall, o.type, tuple(o.boundary)) for o in fc.openings),
        tuple((c.get("key", ""), c.get("count", 1), c.get("rotation", 0))
              for c in fc.combustibles),
        tuple((sc.get("key", ""), sc.get("count", 1))
              for sc in fc.specialized_components),
    )

def _building_signature(b):
    return (
        b.name, b.length, b.width, b.height,
        b.wall_thickness, b.offset_x, b.offset_y,
        tuple(_story_sig(s) for s in b.stories),
    )
```

### 4.3 bundle 构建

`_build_bundle(building)`：

- 对每层 → 调 `_draw_exterior_walls` 改版：不直接 `add_mesh`，而是返回 `pv.Box` 列表
- 用 `pv.MultiBlock.combine()` 或 reduce `+` 合并 boxes → 一个 `pv.PolyData`
- 对 openings/roofs/combustibles 同理
- 返回 `BuildingMeshBundle`

每个 bundle 只在第一次创建，后续重用。

### 4.4 更新流程

```python
def update_buildings(self, bg: BuildingGroup):
    active_keys = set()
    for b in bg.buildings:
        sig = self._building_signature(b)
        active_keys.add(sig)
        if sig not in self._building_cache:
            self._building_cache[sig] = self._build_bundle(b)
        bundle = self._building_cache[sig]
        self._ensure_actors(sig, bundle, b)  # add_mesh if not attached

    # 清理不再在场景中的建筑 actor
    for sig in list(self._building_cache.keys()):
        if sig not in active_keys:
            bundle = self._building_cache[sig]
            for actor in bundle.actors.values():
                self.plotter.remove_actor(actor)
            bundle.actors.clear()
            # bundle 本身保留在 cache 中，下次还能复用
```

### 4.5 高亮

`highlight_building(index)` 改为操作 bundle.actors 的 `prop.color` / `prop.opacity`，不触发重渲染，仅 `plotter.render()`。

### 4.6 缓存失效与清理

- **自动失效**：任一 signature 字段变化 → 新 key 不命中 → 重建（旧 bundle 自动丢弃）。
- **LRU 限制**：保留最近 50 条 bundle（warrick 18 栋远低于阈值，够用），超出用 `dict` 插入顺序剔除最旧。
- **显式清理**：`Viewer3D.clear_cache()`，用于 `new_project` 时彻底清空。

### 4.7 预期性能

| 场景 | 旧 | 新（预估） |
|---|---|---|
| 首次加载 warrick（18 栋） | ~500-800ms | ~500-800ms（首次建 bundle） |
| 改热源 | 同上 | <20ms（不触发建筑重建） |
| 平移一栋 | 同上 | ~30ms（只该栋重建） |
| 切换到同一设施 | 同上 | <50ms（bundle 命中） |
| 切换切片/测点 | 同上 | <10ms |

## 五、实现顺序建议

1. **模型层**（低风险）：`BuildingGroup` 默认值调整；新增 `models/heat_source.py` 与测试。
2. **FDS 生成器**：热源重写，接受新字段（含单位 kW/m²）。
3. **UI 面板**：simulation_control_panel 热源区重构 + 默认值 + 按钮布局；facility_panel 门窗高度 + 可燃物对话框修复；mainwindow 移除工具栏。
4. **3D viewer**：actor 分组 + `update_buildings/heat_source/slices_devices` 接口；保持旧行为下可工作。
5. **信号路由**：`parameters_changed(str)`，mainwindow 分派；消除双重刷新。
6. **Mesh 缓存**：最后接入，只改 `_do_full_render` → `update_buildings` 内部，上层接口不变。

每一步独立验证（跑 `pytest tests/test_models.py` + 手动 UI 冒烟）后再进下一步。

## 六、测试策略

- **单测**（无 UI）：
  - `face_fluxes()` 参数表驱动测试
  - `BuildingGroup.from_dict` 对旧格式迁移（`distance`/`enabled` 被忽略，`net_heat_flux` 单位转换）
  - `_building_signature` 的稳定性（同建筑两次取 sig 相等；改一个开口后 sig 不等）
- **集成测**：
  - `FDSGenerator` 在 azimuth=45° elevation=30° 下生成多个 `&VENT` 面，每面 flux 值正确
  - `FDSGenerator` 在各象限下输出的面名正确
- **手动冒烟**：
  1. 生成 warrick 设施 → 只该次渲染慢；
  2. 拖热源滑块 → 建筑不闪烁（未重建）；
  3. 改网格大小 → 3D 不变、FDS 代码变；
  4. 点"可燃物管理" → 看到 FC 列表；
  5. 切片开关 → 建筑不闪烁；
  6. 门窗 tab 目测高度减半；
  7. 菜单栏下无工具栏。

## 七、范围外 / 非目标

- 不重写 `SPECIALIZED_COMPONENTS` 渲染逻辑（部件级仍需单独 `pv.Box`）；后续若要加速可在 bundle 内做 `MultiBlock` 聚合。
- 不引入磁盘缓存（用户选"内存 mesh 缓存"方案）。
- 不改 `FDSGenerator` 其它节（OBST/VENT/SURF）的生成方式。
- 不动 `fds_generator._compute_mesh` 的 padding 参数来源（保留 5m 默认）；但移除"因 distance 扩 domain"的分支，因为热源现在贴在 MESH 面上，domain 不再需要外扩。
