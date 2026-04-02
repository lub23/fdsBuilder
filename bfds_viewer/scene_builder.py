"""
Blender场景构建器
将BuildingModel转换为Blender场景
"""

import bpy
import math


class SceneBuilder:
    """Blender场景构建器"""

    def __init__(self):
        self.model = None

    def set_model(self, model):
        """设置建筑模型"""
        self.model = model
        return self

    def clear_scene(self):
        """清空场景"""
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

        for mat in bpy.data.materials:
            bpy.data.materials.remove(mat)

    def create_material(self, name: str, color: tuple) -> bpy.types.Material:
        """创建材质"""
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()

        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        bsdf.inputs["Base Color"].default_value = color

        output = nodes.new(type="ShaderNodeOutputMaterial")
        output.location = (300, 0)

        mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
        return mat

    def create_wall(
        self,
        name: str,
        x: float,
        y: float,
        z: float,
        length: float,
        width: float,
        height: float,
        color: tuple,
    ):
        """创建墙体"""
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = (length, width, height)

        mat = self.create_material(name + "_mat", color)
        obj.data.materials.append(mat)
        return obj

    def build(self):
        """构建场景"""
        if not self.model:
            raise ValueError("Model not set")

        self.clear_scene()

        L = self.model.length
        W = self.model.width
        t = self.model.wall_thickness
        total_h = self.model.total_height

        wall_color = (0.8, 0.8, 0.8, 1.0)
        floor_color = (0.5, 0.5, 0.5, 1.0)
        roof_color = (0.6, 0.4, 0.3, 1.0)

        self.create_wall("wall_north", 0, W / 2, total_h / 2, L, t, total_h, wall_color)

        self.create_wall(
            "wall_south", 0, -W / 2, total_h / 2, L, t, total_h, wall_color
        )

        self.create_wall("wall_west", -L / 2, 0, total_h / 2, t, W, total_h, wall_color)

        self.create_wall("wall_east", L / 2, 0, total_h / 2, t, W, total_h, wall_color)

        self.create_wall("floor", 0, 0, -0.1, L + 2, W + 2, 0.2, floor_color)

        self.create_wall("roof", 0, 0, total_h + 0.1, L + 2, W + 2, 0.2, roof_color)

        self.setup_camera()

        self.setup_lighting()

    def setup_camera(self):
        """设置相机"""
        if not self.model:
            return
        distance = max(self.model.length, self.model.width) * 1.5
        bpy.ops.object.camera_add(
            location=(distance, -distance, self.model.total_height * 0.8),
            rotation=(math.radians(60), 0, math.radians(45)),
        )
        camera = bpy.context.active_object
        camera.name = "MainCamera"
        bpy.context.scene.camera = camera

    def setup_lighting(self):
        """设置光照"""
        bpy.ops.object.light_add(type="SUN", location=(10, -10, 20))
        sun = bpy.context.active_object
        sun.data.energy = 3

    def render(self, output_path: str):
        """渲染并保存"""
        bpy.context.scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)
