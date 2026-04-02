# industrial.json 拆分实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `models/industrial.json` 按类别拆分成独立文件，移动到 `data/facilities/` 目录，并更新 `FacilityManager` 加载逻辑。

**Architecture:** 
- 每个类别(Aerospace, Power_Plant 等)一个 JSON 文件
- `FacilityManager` 从目录扫描加载所有类别
- 保持原有接口不变，兼容现有代码

**Tech Stack:** Python, JSON

---

### Task 1: 创建 data/facilities 目录并拆分 JSON 文件

**Files:**
- Create: `data/facilities/aerospace.json`
- Create: `data/facilities/power_plant.json`
- Create: `data/facilities/industrial_manufacturing.json`
- Create: `data/facilities/chemical.json`
- Create: `data/facilities/warehouse.json`
- Create: `data/facilities/transportation.json`
- Create: `data/facilities/__init__.py`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p data/facilities
```

- [ ] **Step 2: 读取 industrial.json 获取所有类别**

```python
# 类别列表(从 industrial.json 键获取):
# - Aerospace
# - Power_Plant
# - Industrial_Manufacturing
# - Chemical
# - Warehouse
# - Transportation
```

- [ ] **Step 3: 为每个类别创建 JSON 文件**

每个文件格式: `{"cn_name": "...", "fire_separation": ..., "sub_types": {...}}`

- [ ] **Step 4: 创建 __init__.py**

```python
# data/facilities/__init__.py
```

- [ ] **Step 5: 提交**

```bash
git add data/facilities/
git commit -m "refactor: 拆分 industrial.json 为独立文件"
```

---

### Task 2: 修改 FacilityManager 加载逻辑

**Files:**
- Modify: `models/facility.py:47-50`

- [ ] **Step 1: 修改 FacilityManager 加载逻辑**

```python
# 原代码:
path = os.path.join(os.path.dirname(__file__), "industrial.json")
with open(path, "r", encoding="utf-8") as f:
    self._data: Dict[str, Any] = json.load(f)

# 新代码(扫描目录):
import os
self._data = {}
facilities_dir = os.path.join(os.path.dirname(__file__), "..", "data", "facilities")
for filename in os.listdir(facilities_dir):
    if filename.endswith('.json') and filename != '__init__.py':
        with open(os.path.join(facilities_dir, filename), 'r', encoding='utf-8') as f:
            category_data = json.load(f)
            # 使用文件名(去掉.json)作为键
            category_key = filename[:-5]  # 去掉 .json
            self._data[category_key] = category_data
```

- [ ] **Step 2: 运行测试验证加载正常**

```bash
python -c "from models.facility import FacilityManager; fm = FacilityManager(); print(fm.categories())"
```

预期输出: `[('Aerospace', '航空航天设施'), ('Power_Plant', '电力设施'), ...]`

- [ ] **Step 3: 提交**

```bash
git add models/facility.py
git commit -m "refactor: FacilityManager 从目录扫描加载设施数据"
```

---

### Task 3: 清理旧文件(可选)

**Files:**
- Delete: `models/industrial.json`

- [ ] **Step 1: 确认新加载方式正常工作后删除旧文件**

```bash
rm models/industrial.json
git add models/industrial.json
git commit -m "refactor: 删除已拆分的 industrial.json"
```

---

### Task 4: 验证整个系统正常工作

**Files:**
- Test: `ui/mainwindow.py`

- [ ] **Step 1: 运行主程序测试**

```bash
python -c "
from models.building import BuildingModel
from generators.fds_generator import FDSGenerator
model = BuildingModel()
generator = FDSGenerator(model)
fds_code = generator.generate()
print('FDS generated, length:', len(fds_code))
"
```

预期: 生成成功，长度 > 1000

- [ ] **Step 2: 提交**

```bash
git status
git commit -m "fix: 修复 FDS 生成器 math 导入问题并拆分 industrial.json"
```