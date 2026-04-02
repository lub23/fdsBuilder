"""
Blender 3D查看器Qt控件
混合模式：Blender渲染 -> QLabel显示
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage


class BlenderViewerWidget(QWidget):
    """Blender 3D查看器控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.blender_client = None
        self._setup_ui()
        self._update_timer = None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_label = QLabel("Blender 3D 预览")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setStyleSheet(
            "background: #1e1e2e; color: #a6adc8; font-size: 24px;"
        )
        layout.addWidget(self.image_label)

        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(5, 5, 5, 5)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self.refresh_view)
        control_layout.addWidget(self.refresh_btn)

        self.status_label = QLabel("状态: 未连接")
        self.status_label.setStyleSheet("color: #a6adc8; padding: 5px;")
        control_layout.addWidget(self.status_label)

        control_layout.addStretch()
        layout.addLayout(control_layout)

        self.setVisible(False)

    def connect_blender(self, client):
        """连接Blender客户端"""
        self.blender_client = client
        self.status_label.setText("状态: 已连接")

    def refresh_view(self):
        """刷新视图 - 每次启动新Blender"""
        if not self.blender_client:
            self.blender_client = BlenderClient()

        self.status_label.setText("状态: 渲染中...")

        code = """
import bpy
import math

L = 20
W = 15
H = 9
t = 0.24

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

for mat in bpy.data.materials:
    bpy.data.materials.remove(mat)

def create_mat(name, color):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = color
    out = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat

def create_wall(name, x, y, z, sx, sy, sz, color):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)
    mat = create_mat(name + "_mat", color)
    obj.data.materials.append(mat)

wall_color = (0.8, 0.8, 0.8, 1.0)
floor_color = (0.5, 0.5, 0.5, 1.0)

create_wall("wall_north", 0, W/2, H/2, L, t, H, wall_color)
create_wall("wall_south", 0, -W/2, H/2, L, t, H, wall_color)
create_wall("wall_west", -L/2, 0, H/2, t, W, H, wall_color)
create_wall("wall_east", L/2, 0, H/2, t, W, H, wall_color)
create_wall("floor", 0, 0, -0.1, L+2, W+2, 0.2, floor_color)

dist = max(L, W) * 1.5
bpy.ops.object.camera_add(location=(dist, -dist, H*0.8), rotation=(math.radians(60), 0, math.radians(45)))
camera = bpy.context.active_object
camera.name = "MainCamera"
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type='SUN', location=(10, -10, 20))
sun = bpy.context.active_object
sun.data.energy = 3

# 渲染
bpy.context.scene.render.filepath = r"D:\\code\\fdsBuilder\\blender_render.png"
bpy.ops.render.render(write_still=True)
print("Scene ready and rendered")
"""
        result = self.blender_client.execute(code, timeout=60)
        print(f"Scene build: {result}")

        self.status_label.setText("状态: 已连接 (点击刷新)")

    def render_and_update(self, model_data: dict):
        """渲染建筑模型"""
        if not self.blender_client:
            return

        L = model_data.get("length", 20)
        W = model_data.get("width", 15)
        H = model_data.get("height", 9)
        t = model_data.get("wall_thickness", 0.24)

        code = f"""
import bpy
import math

L = {L}
W = {W}
H = {H}
t = {t}

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

for mat in bpy.data.materials:
    bpy.data.materials.remove(mat)

def create_mat(name, color):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = color
    out = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat

def create_wall(name, x, y, z, sx, sy, sz, color):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)
    mat = create_mat(name + "_mat", color)
    obj.data.materials.append(mat)

wall_color = (0.8, 0.8, 0.8, 1.0)
floor_color = (0.5, 0.5, 0.5, 1.0)

create_wall("wall_north", 0, W/2, H/2, L, t, H, wall_color)
create_wall("wall_south", 0, -W/2, H/2, L, t, H, wall_color)
create_wall("wall_west", -L/2, 0, H/2, t, W, H, wall_color)
create_wall("wall_east", L/2, 0, H/2, t, W, H, wall_color)
create_wall("floor", 0, 0, -0.1, L+2, W+2, 0.2, floor_color)

dist = max(L, W) * 1.5
bpy.ops.object.camera_add(location=(dist, -dist, H*0.8), rotation=(math.radians(60), 0, math.radians(45)))
camera = bpy.context.active_object
camera.name = "MainCamera"
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type='SUN', location=(10, -10, 20))
sun = bpy.context.active_object
sun.data.energy = 3

print(f"Building: {{L}}x{{W}}x{{H}}")
"""
        result = self.blender_client.execute(code)
        print(f"Model update: {result}")

    def showEvent(self, event):
        """显示时初始化"""
        super().showEvent(event)
        if self.blender_client:
            self.refresh_view()

    def hideEvent(self, event):
        """隐藏时停止"""
        super().hideEvent(event)
