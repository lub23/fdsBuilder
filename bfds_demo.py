#!/usr/bin/env python3
"""
Blender 3D Viewer Demo
从预定义建筑创建Blender场景并渲染
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from bfds_viewer.blender_client import BlenderClient
from models.facility import FacilityManager


def main():
    print("=== Blender 3D Viewer Demo ===")

    # 1. 加载预定义建筑
    fm = FacilityManager()

    cats = fm.categories()
    if not cats:
        print("No facilities found")
        return

    cat_key, cat_name = cats[0]
    subs = fm.sub_types(cat_key)
    if not subs:
        print("No sub types found")
        return

    sub_key, sub_name = subs[0]

    params = fm.default_params(cat_key, sub_key)
    model = fm.generate_model(params)

    print(f"Created model: {model.length}x{model.width}x{model.total_height}m")
    print(f"  Category: {cat_name} / {sub_name}")

    # 2. 构建场景并渲染
    client = BlenderClient()

    output_path = os.path.join(os.path.dirname(__file__), "render_demo.png")
    # 构建脚本 (不使用f-string避免复杂转义)
    script_lines = [
        "import bpy",
        "import math",
        "",
        "# 清空场景",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete()",
        "for mat in bpy.data.materials:",
        "    bpy.data.materials.remove(mat)",
        "",
        "# 材质创建函数",
        "def create_material(name, color):",
        "    mat = bpy.data.materials.new(name=name)",
        "    mat.use_nodes = True",
        "    nodes = mat.node_tree.nodes",
        "    nodes.clear()",
        "    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')",
        "    bsdf.location = (0, 0)",
        "    bsdf.inputs['Base Color'].default_value = color",
        "    output = nodes.new(type='ShaderNodeOutputMaterial')",
        "    output.location = (300, 0)",
        "    mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])",
        "    return mat",
        "",
        "# 墙体创建函数",
        "def create_wall(name, x, y, z, length, width, height, color):",
        "    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))",
        "    obj = bpy.context.active_object",
        "    obj.name = name",
        "    obj.scale = (length, width, height)",
        "    mat = create_material(name + '_mat', color)",
        "    obj.data.materials.append(mat)",
        "",
        f"# 建筑参数",
        f"L = {model.length}",
        f"W = {model.width}",
        f"t = {model.wall_thickness}",
        f"H = {model.total_height}",
        "",
        "# 颜色",
        "wall_color = (0.8, 0.8, 0.8, 1.0)",
        "floor_color = (0.5, 0.5, 0.5, 1.0)",
        "roof_color = (0.6, 0.4, 0.3, 1.0)",
        "",
        "# 创建墙体",
        'create_wall("wall_north", 0, W/2, H/2, L, t, H, wall_color)',
        'create_wall("wall_south", 0, -W/2, H/2, L, t, H, wall_color)',
        'create_wall("wall_west", -L/2, 0, H/2, t, W, H, wall_color)',
        'create_wall("wall_east", L/2, 0, H/2, t, W, H, wall_color)',
        "create_wall('floor', 0, 0, -0.1, L+2, W+2, 0.2, floor_color)",
        "create_wall('roof', 0, 0, H+0.1, L+2, W+2, 0.2, roof_color)",
        "",
        "# 相机",
        "dist = max(L, W) * 1.5",
        "bpy.ops.object.camera_add(location=(dist, -dist, H*0.8), rotation=(math.radians(60), 0, math.radians(45)))",
        "camera = bpy.context.active_object",
        'camera.name = "MainCamera"',
        "bpy.context.scene.camera = camera",
        "",
        "# 光照",
        "bpy.ops.object.light_add(type='SUN', location=(10, -10, 20))",
        "sun = bpy.context.active_object",
        "sun.data.energy = 3",
        "",
        "print(f'Scene built: {L}x{W}x{H}m')",
        "",
        "# 渲染",
        f"output_path = r'{output_path}'",
        "bpy.context.scene.render.filepath = output_path",
        "bpy.ops.render.render(write_still=True)",
        "print('Render complete')",
    ]
    script = "\n".join(script_lines)

    print("\nBuilding Blender scene and rendering...")
    result = client.run_script(script, timeout=180)
    print(result)

    # 检查输出
    if os.path.exists(output_path):
        print(f"\nRendered image saved: {output_path}")

    # 3. FDS导出测试
    print("\n=== Testing FDS Export ===")
    check_script = """
import bpy
addons = list(bpy.context.preferences.addons.keys())
print("INSTALLED_ADDONS:" + ",".join(addons))
"""
    result = client.run_script(check_script)
    print(result)

    # 解析插件列表
    bfds_available = False
    addons = []
    for line in result.split("\n"):
        if line.startswith("INSTALLED_ADDONS:"):
            addons = line.split(":", 1)[1].split(",")
            # BFDS可能是 "bfds" 或 "bl_ext.user_default.bfds"
            bfds_available = any("bfds" in a.strip().lower() for a in addons)
            break

    if bfds_available:
        print("BFDS plugin found! Testing FDS export...")
        fds_output = os.path.join(os.path.dirname(__file__), "case", "building.fds")
        os.makedirs(os.path.dirname(fds_output), exist_ok=True)

        # 尝试导出FDS - 使用行格式
        export_lines = [
            "import bpy",
            f"output = r'{fds_output}'",
            "try:",
            "    bpy.ops.bfds.export_fds(filepath=output)",
            "    print('FDS exported:', output)",
            "except Exception as e:",
            "    print('BFDS export error:', e)",
        ]
        export_script = "\n".join(export_lines)

        result = client.run_script(export_script)
        print(result)
    else:
        print(f"Addons found: {addons}")
        print("BFDS not detected")

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    main()
