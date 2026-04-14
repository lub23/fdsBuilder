# Phase A 设计文档：数据结构与模型重构

**日期**: 2026-04-14
**范围**: 数据结构重构 + type 修正 + 冗余字段清理 + 门窗定位重构 + 参数引擎 + FDS Generator 适配 + UI 更新
**策略**: Schema-First（自底向上）——先定义目标 JSON Schema，迁移数据，再重构代码

---

## 1. 总体架构

### 1.1 三阶段规划

- **Phase A**（本文档）：数据结构重构、门窗定位、参数引擎、FDS/UI 适配
- **Phase B**：防火分区与外墙解耦深化、L 型建筑轮廓驱动渲染、3D 预览修复
- **Phase C**：空间碰撞检测、防穿墙算法、FDS 网格吸附、导出兼容性验证

### 1.2 核心设计原则

- **JSON = 内存表现形式**：废除"JSON 导入后二次转换"逻辑，Python 模型类直接映射 JSON 结构
- **统一开口格式**：所有门窗统一为 `{"wall": str, "type": str, "boundary": [w_offset, width, h_offset, height]}`
- **统一墙体引用**：字符串标识 `"x_min"` / `"x_max"` / `"y_min"` / `"y_max"`，废除整数索引
- **共面检测驱动**：防火分区墙面与建筑外壳共面时，其 openings 自动映射为外墙开孔
- **等效模型动态性**：等效模型 JSON 存储比例模板，运行时由 ParameterEngine 生成绝对值

---

## 2. 目标 JSON Schema

### 2.1 boundary 语义对照表

| 类 | boundary 含义 | 格式 |
|---|---|---|
| `Building` | `[offset_x, length, offset_y, width]` | 位置 + 尺寸 |
| `Opening` | `[w_offset, width, h_offset, height]` | 偏移 + 尺寸 |
| `Roof.openings[]` | `[x, length, y, width]` | 位置 + 尺寸 |
| `FireCompartment` | `[x_min, x_max, y_min, y_max]` | 绝对坐标范围（建筑局部） |

Opening.boundary 中 `w_offset` 为正数表示距墙起始侧距离，负数表示距墙末端距离。

### 2.2 特异模型 JSON

```json
{
  "type": "specialized",
  "cn_name": "美铝公司",
  "buildings": [
    {
      "name": "Alcoa Smelting Plant",
      "cn_name": "铝冶炼厂",
      "boundary": [0, 176, 0, 150],
      "wall_thickness": 0.24,
      "height": 10,
      "boundary_polygons": null,
      "stories": [
        {
          "name": "1F",
          "height": 10.0,
          "openings": [],
          "fire_compartments": [
            {
              "name": "Potline Hall A",
              "boundary": [0, 88, 0, 75],
              "firewall_thickness": 0.3,
              "firewall_material": "CONCRETE",
              "openings": [
                {"wall": "x_max", "type": "door", "boundary": [10.0, 5.0, 0, 4.0]}
              ],
              "combustibles": [{"key": "WOOD_DESK", "count": 3}],
              "specialized_components": [{"key": "BOILER_IGNITION_SYSTEM", "count": 1}]
            },
            {
              "name": "Potline Hall B",
              "boundary": [88, 176, 0, 75],
              "firewall_thickness": 0.3,
              "firewall_material": "CONCRETE",
              "openings": [],
              "combustibles": [],
              "specialized_components": []
            }
          ],
          "roof": {
            "thickness": 0.2,
            "material": "CONCRETE",
            "openings": []
          }
        }
      ]
    }
  ]
}
```

关键特征：
- `type` 在根节点，值为 `"specialized"`
- 无全局 `doors` / `windows` 字段
- 无 `rotation` 字段
- 所有开口在 `fire_compartments[].openings` 中定义
- 每层至少一个 fire_compartment（可覆盖整层范围）
- `combustibles` 和 `specialized_components` 在 fire_compartment 内部
- `boundary_polygons`: `null` 表示标准矩形（L 型支持为 Phase B 预留）

### 2.3 BuildingGroup JSON（运行时配置 / 项目保存）

```json
{
  "building_group": {
    "buildings": [
      {
        "name": "Building 1",
        "cn_name": "建筑1",
        "boundary": [0, 176, 0, 150],
        "wall_thickness": 0.24,
        "height": 10,
        "boundary_polygons": null,
        "stories": [
          {
            "name": "1F",
            "height": 10.0,
            "openings": [
              {"wall": "y_min", "type": "door", "boundary": [5.0, 3.0, 0, 2.5]}
            ],
            "fire_compartments": [
              {
                "name": "Zone A",
                "boundary": [0, 176, 0, 150],
                "firewall_thickness": 0.0,
                "firewall_material": "CONCRETE",
                "openings": [],
                "combustibles": [{"key": "WOOD_DESK", "count": 3}],
                "specialized_components": []
              }
            ],
            "roof": {
              "thickness": 0.2,
              "material": "CONCRETE",
              "openings": [{"boundary": [8, 3, 6, 3]}]
            }
          }
        ]
      }
    ],
    "heat_source": {},
    "simulation_time": 300,
    "domain": {"padding": 5.0, "mesh_cells": [80, 60, 40]},
    "output": {"slices": true, "devices": true}
  }
}
```

与特异模型的区别：
- 外层包裹 `building_group`，含 FDS 配置（`heat_source`, `simulation_time`, `domain`, `output`）
- story 级 `openings` 用于外墙开口（不通过 fire_compartment 设置的情况）
- 单 fire_compartment 覆盖整层时 `firewall_thickness: 0.0` 表示无隔墙

### 2.4 等效模型 JSON

```json
{
  "type": "equivalent",
  "cn_name": "航空航天设施",
  "buildings": [
    {
      "name": "Large Rocket Manufacturing Plant",
      "cn_name": "大型火箭制造厂",
      "length_range": [50, 120],
      "width_range": [15, 50],
      "height_range": [8, 12],
      "stories_range": [2, 4, 3],
      "stories_template": [
        {
          "name": "1F",
          "height": 10.0,
          "doors": {
            "width": [4, 4],
            "height": [4, 4],
            "count": [1, 3]
          },
          "windows": {
            "width": [2, 3],
            "height": [1.5, 2],
            "count": [2, 6]
          },
          "fire_compartment_ratios": [
            {
              "name": "Zone A",
              "boundary_ratio": [0.0, 0.5, 0.0, 1.0],
              "firewall_thickness": 0.3,
              "firewall_material": "CONCRETE",
              "opening_templates": [
                {
                  "wall": "x_max",
                  "type": "door",
                  "w_offset_ratio": 0.2,
                  "width_ratio": 0.1,
                  "h_offset": 0,
                  "height": 4.0
                }
              ],
              "combustibles": [{"key": "WOOD_DESK", "count": 3}],
              "specialized_components": []
            }
          ],
          "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []}
        }
      ],
      "stories": []
    }
  ]
}
```

运行时流程：
1. 用户选择 building，UI 显示各 `*_range` 的 `[min, max]`，默认值取第 3 元素或 `(min+max)/2`
2. 用户调整 length/width/height/stories 数值
3. `ParameterEngine.generate()` 从 `stories_template` + 用户尺寸实时生成 `stories[]`
4. 生成的 `stories` 结构与特异模型 / BuildingGroup 完全一致
5. 保存时 `stories[]` 存储当前快照，`stories_template` 保留（可重算）

等效模型 range 格式：
- `[min, max]` → 默认值 = (min + max) / 2
- `[min, max, default]` → 默认值 = default

---

## 3. 数据迁移策略

### 3.1 总体方案

编写独立脚本 `tools/migrate_schema.py`，一次性转换 11 个 facility JSON + `building_config.json`。迁移前自动备份到 `data/facilities/_backup/`。

### 3.2 特异模型迁移（7 个文件）

| 旧结构 | 新结构 |
|--------|--------|
| `sub_types: { "Name": {...} }` (dict) | `buildings: [{"name": "Name", ...}]` (array) |
| sub_type 内 `"type": "specialized"` | 根节点 `"type": "specialized"` |
| `fire_separation: 15.0` | 删除 |
| `rotation: 0` | 删除 |
| `building.length: {"value": 176, "unit": "m"}` | `boundary: [0, 176, 0, 150]`（由 length.value + width.value 合成） |
| `building.height: {"value": 10, ...}` | `height: 10` |
| fire_compartment `x_min/x_max/y_min/y_max` 四字段 | `boundary: [x_min, x_max, y_min, y_max]` |
| `doors: {}`, `windows: {}` (全局) | 删除 |
| opening `position: 0.5, width: 5, height: 4, z_bottom: 0` | `boundary: [w_offset, 5, 0, 4]` |

position → w_offset 转换公式：

```python
# 确定墙段长度
if wall in ("x_min", "x_max"):
    wall_length = y_max - y_min  # 沿 Y 方向
elif wall in ("y_min", "y_max"):
    wall_length = x_max - x_min  # 沿 X 方向

# 旧 position 是中心点比例 (0-1)
center = position * wall_length
w_offset = center - width / 2
```

补全 story 结构：根据 `building.stories.value` 生成 story 包裹层，将 fire_compartments 放入，添加默认 roof。确保每层至少一个 fire_compartment。

### 3.3 等效模型迁移（4 个文件）

| 旧结构 | 新结构 |
|--------|--------|
| `sub_types: {...}` (dict) | `buildings: [...]` (array) |
| 无 `type` 字段 | 根节点 `"type": "equivalent"` |
| `fire_separation` | 删除 |
| `building.length: {"min":50,"max":120,"median":-1,"mean":-1,"unit":"m"}` | `length_range: [50, 120]`（median > 0 时为 `[min, max, median]`） |
| 全局 `doors/windows` | 移入 `stories_template[].doors/.windows` |
| fire_compartment 绝对坐标 | 转为 `fire_compartment_ratios` 的比例 |
| opening 的 `position` | 转为 `w_offset_ratio` 和 `width_ratio` |

比例计算：

```python
default_length = (min + max) / 2  # 或 median if > 0
default_width = ...

boundary_ratio = [
    fc.x_min / default_length,
    fc.x_max / default_length,
    fc.y_min / default_width,
    fc.y_max / default_width
]

wall_length = ...  # 取决于 wall 方向
w_offset = position * wall_length - width / 2
w_offset_ratio = w_offset / wall_length
width_ratio = width / wall_length
```

### 3.4 building_config.json 迁移

| 旧结构 | 新结构 |
|--------|--------|
| `length: 29.2, width: 56.5` | `boundary: [0, 29.2, 0, 56.5]` |
| `stories[].walls` | 删除 |
| `stories[].openings[].wall_index: 0` (int) | `wall: "y_min"` (str)，映射：0→y_min, 1→y_max, 2→x_min, 3→x_max |
| `openings[].position/width/height/z_bottom` | `boundary: [w_offset, width, z_bottom, height]` |
| `stories[].floor_slab` | 第 N 层 floor_slab → 第 N-1 层 roof |
| 无 `fire_compartments` | 生成默认 1 个覆盖整层的 fire_compartment |
| `stories[].combustibles` | 移入默认 fire_compartment |
| building 级 `roof` | 移入最顶层 story.roof |

### 3.5 验证策略

1. **几何等价校验**：迁移前后分别生成 FDS 文本，提取所有 `&OBST` 和 `&HOLE` 的坐标，对比浮点精度内一致
2. **结构完整性校验**：每层有 >= 1 fire_compartment、所有 opening 有 boundary 数组、无残留旧字段
3. **脚本输出 diff 报告**：对每个文件列出字段变更摘要

---

## 4. Python 模型类重构

### 4.1 类结构

```
BuildingGroup                        # 顶层容器（替代 BuildingModel）
├── buildings: list[Building]
│   ├── boundary: [offset_x, length, offset_y, width]
│   ├── stories: list[Story]
│   │   ├── openings: list[Opening]          # 外墙开口
│   │   ├── fire_compartments: list[FireCompartment]
│   │   │   ├── openings: list[Opening]      # 内墙/共面外墙开口
│   │   │   ├── combustibles: list[dict]
│   │   │   └── specialized_components: list[dict]
│   │   └── roof: Roof
│   └── length, width (computed properties)
├── heat_source, simulation_time, domain, output   # FDS 配置
```

### 4.2 Dataclass 定义

```python
@dataclass
class Opening:
    wall: str                    # "x_min", "x_max", "y_min", "y_max"
    type: str                    # "door", "window", "opening", "loading_dock", "ribbon_window"
    boundary: list[float]        # [w_offset, width, h_offset, height]

@dataclass
class Roof:
    thickness: float = 0.2
    material: str = "CONCRETE"
    openings: list[dict] = field(default_factory=list)  # [{"boundary": [x, length, y, width]}]

@dataclass
class FireCompartment:
    name: str = ""
    boundary: list[float] = field(default_factory=lambda: [0, 0, 0, 0])  # [x_min, x_max, y_min, y_max]
    firewall_thickness: float = 0.3
    firewall_material: str = "CONCRETE"
    openings: list[Opening] = field(default_factory=list)
    combustibles: list[dict] = field(default_factory=list)
    specialized_components: list[dict] = field(default_factory=list)

@dataclass
class Story:
    name: str = "1F"
    height: float = 3.0
    openings: list[Opening] = field(default_factory=list)
    fire_compartments: list[FireCompartment] = field(default_factory=list)
    roof: Roof = field(default_factory=Roof)
    z_bottom: float = 0.0      # 运行时计算

    @property
    def z_top(self) -> float:
        return self.z_bottom + self.height

@dataclass
class Building:
    name: str = ""
    cn_name: str = ""
    boundary: list[float] = field(default_factory=lambda: [0, 20, 0, 10])
    wall_thickness: float = 0.24
    height: float = 3.0
    boundary_polygons: list | None = None
    stories: list[Story] = field(default_factory=list)

    # height 为概要字段，权威值来自 sum(story.height)。
    # 单层建筑时 height == stories[0].height；
    # 多层建筑时 height 应由 update_z_offsets() 后校验一致性。

    @property
    def length(self) -> float:
        return self.boundary[1]

    @property
    def width(self) -> float:
        return self.boundary[3]

    @property
    def offset_x(self) -> float:
        return self.boundary[0]

    @property
    def offset_y(self) -> float:
        return self.boundary[2]

    def update_z_offsets(self):
        z = 0.0
        for story in self.stories:
            story.z_bottom = z
            z += story.height

    def get_exterior_walls(self, story_index: int) -> dict[str, list[float]]:
        """从 boundary 自动生成 4 面外墙几何 (运行时计算，不存储)"""
        ...

@dataclass
class BuildingGroup:
    buildings: list[Building] = field(default_factory=list)
    heat_source: dict = field(default_factory=dict)
    simulation_time: float = 300
    domain: dict = field(default_factory=lambda: {"padding": 5.0, "mesh_cells": [80, 60, 40]})
    output: dict = field(default_factory=lambda: {"slices": True, "devices": True})

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> "BuildingGroup": ...
```

### 4.3 删除清单

| 删除项 | 原因 |
|--------|------|
| `BuildingModel` 类 | `BuildingGroup` 直接替代 |
| `FloorSlab` 类 | `Roof` 替代（N 层 roof = N+1 层地板） |
| `Story.walls` | 外墙由 `Building.boundary` 自动生成 |
| `update_external_walls()` | 替换为 `get_exterior_walls()` 运行时计算 |
| `Story.combustibles` / `CombustibleManager` 作为 Story 直属 | 移入 `FireCompartment` |
| Opening dict 格式 | 替换为 `Opening` dataclass |
| `Building.x_offset` / `y_offset` | 由 `boundary[0]` / `boundary[2]` 承担 |
| `Building.rotation` | 删除 |
| `BuildingGroup.fire_separation` | 删除 |

### 4.4 CombustibleManager 调整

保留分布算法（`UNIFORM_GRID`, `RANDOM`, `ALONG_WALLS` 等），职责变更：
- 输入：`key + count + FireCompartment.boundary`（生成范围限定在分区内）
- 输出：具体位置的 `Combustible` 列表，用于 3D 渲染和 FDS 导出
- 存储：JSON 中只存 `{"key": "WOOD_DESK", "count": 3}`，位置在加载时按分布策略生成

### 4.5 序列化

`to_dict()` / `from_dict()` 直接映射 JSON 结构。对于特异模型 JSON（无 `building_group` 包裹），`from_dict` 同样读取 `buildings` 数组。加载时检测 `type` 字段决定是否标记为只读。

---

## 5. FacilityManager + 参数引擎

### 5.1 FacilityManager 重构

```python
class FacilityManager:
    def __init__(self, data_dir: str):
        self.facilities: dict[str, dict] = {}
        self._load_all(data_dir)

    def _load_all(self, data_dir):
        for f in glob(data_dir + "/*.json"):
            self.facilities[f.stem] = json.load(open(f))

    def get_type(self, facility_name: str) -> str:
        return self.facilities[facility_name]["type"]

    def list_buildings(self, facility_name: str) -> list[str]:
        return [b["name"] for b in self.facilities[facility_name]["buildings"]]

    def load_specialized(self, facility_name: str, building_name: str) -> Building:
        bdata = self._find_building(facility_name, building_name)
        return Building.from_dict(bdata)

    def load_equivalent(self, facility_name: str, building_name: str,
                        params: dict) -> Building:
        bdata = self._find_building(facility_name, building_name)
        return ParameterEngine.generate(bdata, params)
```

删除 `_rv()` / `_rng()` / `default_params()` 等旧方法。

### 5.2 ParameterEngine（新增）

```python
class ParameterEngine:
    @staticmethod
    def resolve_range(r: list) -> float:
        """[min, max] -> (min+max)/2; [min, max, default] -> default"""
        if len(r) >= 3:
            return r[2]
        return (r[0] + r[1]) / 2

    @staticmethod
    def generate(template_building: dict, params: dict) -> Building:
        """
        params = {"length": 85.0, "width": 32.5, "height": 10.0, "stories": 3}
        """
        length = params["length"]
        width = params["width"]
        height = params["height"]
        num_stories = int(params["stories"])

        stories = []
        for i in range(num_stories):
            tmpl = template_building["stories_template"][
                min(i, len(template_building["stories_template"]) - 1)
            ]
            story = ParameterEngine._expand_story_template(tmpl, length, width, height / num_stories)
            story["name"] = f"{i+1}F"
            stories.append(story)

        return Building.from_dict({
            "name": template_building["name"],
            "cn_name": template_building["cn_name"],
            "boundary": [0, length, 0, width],
            "wall_thickness": 0.24,
            "height": height,
            "boundary_polygons": None,
            "stories": stories
        })

    @staticmethod
    def _expand_story_template(tmpl, length, width, story_height) -> dict:
        compartments = []
        for fc_ratio in tmpl.get("fire_compartment_ratios", []):
            br = fc_ratio["boundary_ratio"]
            fc = {
                "name": fc_ratio["name"],
                "boundary": [br[0]*length, br[1]*length, br[2]*width, br[3]*width],
                "firewall_thickness": fc_ratio["firewall_thickness"],
                "firewall_material": fc_ratio["firewall_material"],
                "openings": [],
                "combustibles": fc_ratio.get("combustibles", []),
                "specialized_components": fc_ratio.get("specialized_components", [])
            }
            for ot in fc_ratio.get("opening_templates", []):
                wall_len = ParameterEngine._wall_length(fc["boundary"], ot["wall"])
                fc["openings"].append({
                    "wall": ot["wall"],
                    "type": ot["type"],
                    "boundary": [
                        ot["w_offset_ratio"] * wall_len,
                        ot["width_ratio"] * wall_len,
                        ot["h_offset"],
                        ot["height"]
                    ]
                })
            compartments.append(fc)

        exterior_openings = ParameterEngine._distribute_exterior_openings(tmpl, length, width, story_height)

        return {
            "height": story_height,
            "openings": exterior_openings,
            "fire_compartments": compartments,
            "roof": tmpl.get("roof", {"thickness": 0.2, "material": "CONCRETE", "openings": []})
        }

    @staticmethod
    def _wall_length(fc_boundary, wall) -> float:
        x_min, x_max, y_min, y_max = fc_boundary
        if wall in ("x_min", "x_max"):
            return y_max - y_min
        return x_max - x_min

    @staticmethod
    def _distribute_exterior_openings(tmpl, length, width, story_height) -> list:
        openings = []
        for kind, walls in [("door", ["y_min", "y_max"]), ("window", ["x_min", "x_max"])]:
            spec = tmpl.get(f"{kind}s", {})
            if not spec:
                continue
            w = ParameterEngine.resolve_range(spec["width"])
            h = ParameterEngine.resolve_range(spec["height"])
            count = int(ParameterEngine.resolve_range(spec["count"]))
            h_offset = 0 if kind == "door" else max(0, story_height * 0.4)
            for wall in walls:
                wall_len = length if wall in ("y_min", "y_max") else width
                spacing = wall_len / (count + 1)
                for i in range(count):
                    openings.append({
                        "wall": wall,
                        "type": kind,
                        "boundary": [spacing * (i + 1) - w / 2, w, h_offset, h]
                    })
        return openings
```

### 5.3 尺寸变更实时重算

用户在 UI 修改等效模型参数时：
1. UI 发出 `parameters_changed` 信号
2. `ParameterEngine.generate()` 从 `stories_template` 重新生成 `Building`
3. 替换 `BuildingGroup.buildings[i]`
4. 触发 3D 渲染和 FDS 预览刷新

特异模型不触发此流程——UI 参数锁定为只读。

---

## 6. FDS Generator 适配

### 6.1 坐标系统

```
Building.boundary = [ox, L, oy, W]
  世界坐标 X: [ox, ox+L], Y: [oy, oy+W]

FireCompartment.boundary = [x_min, x_max, y_min, y_max]  (建筑局部坐标)
  世界坐标: [ox+x_min, ox+x_max, oy+y_min, oy+y_max]

Story.z_bottom → Z 偏移
  墙体世界 Z: [z_bottom, z_bottom + story.height]
```

FDS 输出坐标 = 世界坐标。域边界由所有建筑包围盒 + padding 计算。

### 6.2 生成流程

```
&HEAD, &TIME, &REAC
&MESH
&MATL, &SURF

遍历 building_group.buildings:
  遍历 building.stories:
    1. 外墙生成 (4面, 从 boundary 自动计算)
    2. 外墙开口切分 (story.openings + 共面检测映射)
    3. 防火隔墙生成 (非共面的 fire_compartment 边界)
    4. 防火隔墙开口切分
    5. Roof 生成 (&OBST + &HOLE)
    6. 可燃物 (&OBST, 位置由 CombustibleManager 在分区内生成)
    7. 特异性组件

外部热源
&SLCF, &BNDF, &DEVC
&TAIL
```

### 6.3 外墙生成

```python
def _generate_exterior_walls(self, building, story):
    ox, L, oy, W = building.boundary
    t = building.wall_thickness
    z0, z1 = story.z_bottom, story.z_top

    walls = {
        "y_min": [ox - t/2, ox + L + t/2, oy - t,     oy,         z0, z1],
        "y_max": [ox - t/2, ox + L + t/2, oy + W,      oy + W + t, z0, z1],
        "x_min": [ox - t,   ox,            oy - t/2,   oy + W + t/2, z0, z1],
        "x_max": [ox + L,   ox + L + t,    oy - t/2,   oy + W + t/2, z0, z1],
    }

    all_exterior_openings = list(story.openings)
    all_exterior_openings += self._detect_coplanar_openings(building, story)

    for wall_id, obst_bounds in walls.items():
        wall_openings = [o for o in all_exterior_openings if o.wall == wall_id]
        self._generate_wall_with_holes(wall_id, obst_bounds, wall_openings, t)
```

### 6.4 共面检测

```python
def _detect_coplanar_openings(self, building, story) -> list[Opening]:
    """检测 FC 墙面与建筑外壳共面，将 openings 映射为外墙开口（含坐标平移）"""
    ox, L, oy, W = building.boundary
    coplanar = []
    for fc in story.fire_compartments:
        x_min, x_max, y_min, y_max = fc.boundary
        checks = [
            ("x_min", x_min, 0),
            ("x_max", x_max, L),
            ("y_min", y_min, 0),
            ("y_max", y_max, W),
        ]
        for wall_id, fc_val, building_val in checks:
            if abs(fc_val - building_val) < 1e-6:
                # FC 墙段在建筑外墙上的起点偏移量
                # 例：FC boundary=[88,176,0,75]，y_min 墙从 x=88 开始
                # 建筑 y_min 墙从 x=0 开始，需要 w_offset += 88
                if wall_id in ("y_min", "y_max"):
                    fc_wall_start = x_min   # FC 的 y 向墙沿 X 方向展开
                elif wall_id in ("x_min", "x_max"):
                    fc_wall_start = y_min   # FC 的 x 向墙沿 Y 方向展开

                for opening in fc.openings:
                    if opening.wall == wall_id:
                        # 创建平移后的副本，w_offset 加上 FC 墙段起点偏移
                        shifted = Opening(
                            wall=opening.wall,
                            type=opening.type,
                            boundary=[
                                opening.boundary[0] + fc_wall_start,
                                opening.boundary[1],
                                opening.boundary[2],
                                opening.boundary[3]
                            ]
                        )
                        coplanar.append(shifted)
    return coplanar
```

### 6.5 开口切分 + HOLE 厚度冗余

采用 FDS 原生 `&OBST` + `&HOLE` 组合：输出完整墙体 OBST，再用 HOLE 切穿。

HOLE 在法线方向两侧各扩展 5cm（`REDUNDANCY = 0.05`），确保完全切穿厚度不一的 OBST。

负 `w_offset` 处理：`w_off < 0` 时转换为 `wall_length + w_off - width`。

### 6.6 防火隔墙

只对非共面的 fire_compartment 边界生成隔墙 OBST。共面边界的开口已映射到外墙处理。

---

## 7. UI 变更

### 7.1 FacilityPanel

- 树形列表节点显示 `[等效]` / `[特异]` 标签 + 颜色区分图标
- 选中等效模型 building：显示可编辑 spinbox（带 range 限制和 `[min ~ max]` 提示）
- 选中特异模型 building：显示只读参数（spinbox 禁用，灰色背景）

### 7.2 ParameterPanel

| 旧控件 | 变更 |
|--------|------|
| 墙体表格 (walls table) | 删除 |
| 开口表格 列 `位置(0-1)` | 改为 `w_offset(m)` |
| 开口表格 列 `所属墙(index)` | 改为 `所属墙(str)` 下拉框 |
| `z_bottom` 列 | 改为 `h_offset` 列 |
| 可燃物管理 | 来源为当前选中 fire_compartment |
| 楼板开洞 | 合并到 roof openings 编辑 |

新增控件：
- 防火分区编辑器：fire_compartments 列表 + boundary 编辑
- 当前分区选择器：下拉框切换当前编辑的 fire_compartment
- 只读模式标志：特异模型加载后所有编辑控件 `setEnabled(False)`

### 7.3 对话框

| 对话框 | 变更 |
|--------|------|
| `OpeningDialog` | position → w_offset; wall_index → wall str; z_bottom → h_offset |
| `WallDialog` | 删除 |
| `FloorSlabHoleDialog` | 重命名为 `RoofOpeningDialog`，用 `[x, length, y, width]` |
| `BatchOpeningDialog` | 适配新 boundary 格式 |
| `BatchWallDialog` | 删除 |
| `CombustibleDialog` | 增加 fire_compartment 选择器 |

### 7.4 Viewer3D

- 外墙从 `building.boundary` 自动生成 4 面 Box
- 合并 story.openings + 共面检测结果渲染外墙开口
- 防火隔墙用红色半透明渲染
- 可燃物按 fire_compartment 分区生成
- 共面检测逻辑抽取为 `models/geometry.py` 共享工具函数

### 7.5 3D 预览崩溃修复

重构后外墙由 boundary 自动生成，开口从 story.openings + 共面映射读取，不再依赖 `story.walls` 和全局 `doors/windows`，崩溃问题自然消除。

---

## 8. 共享工具模块

新增 `models/geometry.py`，提供 Viewer3D 和 FDSGenerator 共用的几何计算：

- `detect_coplanar_openings(building, story) -> list[Opening]`（含 w_offset 坐标平移）
- `is_coplanar(fc_boundary, building_boundary, wall_id) -> bool`
- `fc_wall_start_offset(fc_boundary, wall_id) -> float`（FC 墙段在建筑外墙上的起点偏移）
- `wall_length(boundary, wall_id) -> float`
- `resolve_negative_offset(w_offset, width, wall_length) -> float`
- `opening_to_world_coords(opening, wall_id, building, story) -> tuple[6]`
