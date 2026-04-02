#!/usr/bin/env python3
"""
Blender 3D Viewer Demo
测试bpy API是否可用于建筑3D可视化
"""

import bpy
import math

# 清理现有场景
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# 删除所有材质
for mat in bpy.data.materials:
    bpy.data.materials.remove(mat)


# 创建材质
def create_material(name, color):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    # 清空默认节点
    nodes.clear()
    # 创建 Principled BSDF 节点
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = color
    # 创建输出节点
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (300, 0)
    mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


# 创建建筑墙体 (简化: 用立方体表示)
def create_wall(name, x, y, z, length, width, height, color):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (length, width, height)

    mat = create_material(name + "_mat", color)
    obj.data.materials.append(mat)

    return obj


# 参数 (单位: 米)
wall_thickness = 0.24
story_height = 3.0
building_length = 10.0
building_width = 8.0

# 创建4面墙体
# 顺序: 北墙(上), 南墙(下), 西墙(左), 东墙(右)

# 北墙 (y = +W/2)
create_wall(
    "wall_north",
    x=0,
    y=building_width / 2,
    z=story_height / 2,
    length=building_length,
    width=wall_thickness,
    height=story_height,
    color=(0.8, 0.8, 0.8, 1.0),
)

# 南墙 (y = -W/2)
create_wall(
    "wall_south",
    x=0,
    y=-building_width / 2,
    z=story_height / 2,
    length=building_length,
    width=wall_thickness,
    height=story_height,
    color=(0.7, 0.7, 0.7, 1.0),
)

# 西墙 (x = -L/2)
create_wall(
    "wall_west",
    x=-building_length / 2,
    y=0,
    z=story_height / 2,
    length=wall_thickness,
    width=building_width,
    height=story_height,
    color=(0.6, 0.6, 0.6, 1.0),
)

# 东墙 (x = +L/2)
create_wall(
    "wall_east",
    x=building_length / 2,
    y=0,
    z=story_height / 2,
    length=wall_thickness,
    width=building_width,
    height=story_height,
    color=(0.5, 0.5, 0.5, 1.0),
)

# 创建地面
create_wall(
    "floor",
    x=0,
    y=0,
    z=-0.1,
    length=building_length + 2,
    width=building_width + 2,
    height=0.2,
    color=(0.3, 0.3, 0.3, 1.0),
)

# 创建开口 (窗) - 在北墙挖洞效果用另一个颜色表示
create_wall(
    "window",
    x=0,
    y=building_width / 2 + wall_thickness / 2,
    z=story_height * 0.6,
    length=2.0,
    width=0.1,
    height=1.5,
    color=(0.2, 0.5, 0.8, 1.0),
)

# 设置相机
bpy.ops.object.camera_add(
    location=(15, -15, 12), rotation=(math.radians(60), 0, math.radians(45))
)
camera = bpy.context.active_object
camera.name = "MainCamera"
bpy.context.scene.camera = camera

# 设置光照
bpy.ops.object.light_add(type="SUN", location=(10, -10, 20))
sun = bpy.context.active_object
sun.data.energy = 3

# 设置渲染输出
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
bpy.context.scene.render.film_transparent = False

print("Blender Demo: 创建了建筑墙体模型")
print(f"  - 建筑尺寸: {building_length}m x {building_width}m x {story_height}m")
print(f"  - 墙体厚度: {wall_thickness}m")
print(f"  - 包含北墙/南墙/西墙/东墙/地面/窗户")

# 渲染输出
output_path = "D:\\code\\fdsBuilder\\.worktrees\\blender-demo\\render.png"
bpy.context.scene.render.filepath = output_path
bpy.ops.render.render(write_still=True)
print(f"渲染输出: {output_path}")
