"""
大型设施预设 - Blender场景生成
"""


class FacilityPreset:
    """设施预设生成器"""

    @staticmethod
    def generate_code(preset_type: str, params: dict) -> str:
        """生成Blender场景代码"""

        if preset_type == "industrial_plant":
            return FacilityPreset._industrial_plant(params)
        elif preset_type == "warehouse":
            return FacilityPreset._warehouse(params)
        elif preset_type == "data_center":
            return FacilityPreset._data_center(params)
        elif preset_type == "office_building":
            return FacilityPreset._office_building(params)
        else:
            return FacilityPreset._simple_building(params)

    @staticmethod
    def _industrial_plant(params: dict) -> str:
        """工业园区"""
        L = params.get("length", 100)
        W = params.get("width", 80)
        H = params.get("height", 12)
        t = params.get("wall_thickness", 0.3)

        return f"""
import bpy

L = {L}
W = {W}
H = {H}
t = {t}

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def create_wall(name, x, y, z, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x,y,z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)

create_wall("wall_north", 0, W/2, H/2, L, t, H)
create_wall("wall_south", 0, -W/2, H/2, L, t, H)
create_wall("wall_west", -L/2, 0, H/2, t, W, H)
create_wall("wall_east", L/2, 0, H/2, t, W, H)
create_wall("floor", 0, 0, -0.1, L+4, W+4, 0.2)

print(f"Industrial plant: {{L}}x{{W}}x{{H}}")
"""

    @staticmethod
    def _warehouse(params: dict) -> str:
        """仓库"""
        L = params.get("length", 50)
        W = params.get("width", 30)
        H = params.get("height", 8)
        t = params.get("wall_thickness", 0.24)

        return f"""
import bpy

L = {L}
W = {W}
H = {H}
t = {t}

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def create_wall(name, x, y, z, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x,y,z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)

create_wall("wall_north", 0, W/2, H/2, L, t, H)
create_wall("wall_south", 0, -W/2, H/2, L, t, H)
create_wall("wall_west", -L/2, 0, H/2, t, W, H)
create_wall("wall_east", L/2, 0, H/2, t, W, H)
create_wall("floor", 0, 0, -0.1, L+2, W+2, 0.2)

print(f"Warehouse: {{L}}x{{W}}x{{H}}")
"""

    @staticmethod
    def _data_center(params: dict) -> str:
        """数据中心"""
        L = params.get("length", 40)
        W = params.get("width", 25)
        H = params.get("height", 6)
        t = params.get("wall_thickness", 0.3)

        return f"""
import bpy

L = {L}
W = {W}
H = {H}
t = {t}

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def create_wall(name, x, y, z, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x,y,z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)

create_wall("wall_north", 0, W/2, H/2, L, t, H)
create_wall("wall_south", 0, -W/2, H/2, L, t, H)
create_wall("wall_west", -L/2, 0, H/2, t, W, H)
create_wall("wall_east", L/2, 0, H/2, t, W, H)
create_wall("floor", 0, 0, -0.1, L+2, W+2, 0.3)

print(f"Data center: {{L}}x{{W}}x{{H}}")
"""

    @staticmethod
    def _office_building(params: dict) -> str:
        """办公楼"""
        L = params.get("length", 30)
        W = params.get("width", 20)
        H = params.get("height", 15)
        t = params.get("wall_thickness", 0.2)

        return f"""
import bpy

L = {L}
W = {W}
H = {H}
t = {t}

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def create_wall(name, x, y, z, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x,y,z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)

create_wall("wall_north", 0, W/2, H/2, L, t, H)
create_wall("wall_south", 0, -W/2, H/2, L, t, H)
create_wall("wall_west", -L/2, 0, H/2, t, W, H)
create_wall("wall_east", L/2, 0, H/2, t, W, H)
create_wall("floor", 0, 0, -0.1, L+2, W+2, 0.2)

print(f"Office building: {{L}}x{{W}}x{{H}}")
"""

    @staticmethod
    def _simple_building(params: dict) -> str:
        """简单建筑"""
        L = params.get("length", 20)
        W = params.get("width", 15)
        H = params.get("height", 9)
        t = params.get("wall_thickness", 0.24)

        return f"""
import bpy

L = {L}
W = {W}
H = {H}
t = {t}

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def create_wall(name, x, y, z, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x,y,z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)

create_wall("wall_north", 0, W/2, H/2, L, t, H)
create_wall("wall_south", 0, -W/2, H/2, L, t, H)
create_wall("wall_west", -L/2, 0, H/2, t, W, H)
create_wall("wall_east", L/2, 0, H/2, t, W, H)
create_wall("floor", 0, 0, -0.1, L+2, W+2, 0.2)

print(f"Building: {{L}}x{{W}}x{{H}}")
"""


FACILITY_PRESETS = {
    "custom": {"name": "自定义", "params": {}},
    "industrial_plant": {
        "name": "工业园区",
        "params": {"length": 100, "width": 80, "height": 12},
    },
    "warehouse": {"name": "仓库", "params": {"length": 50, "width": 30, "height": 8}},
    "data_center": {
        "name": "数据中心",
        "params": {"length": 40, "width": 25, "height": 6},
    },
    "office_building": {
        "name": "办公楼",
        "params": {"length": 30, "width": 20, "height": 15},
    },
}
