"""
Blender 3D查看器Qt控件
支持后台渲染和交互模式
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QComboBox,
)
from PySide6.QtCore import Qt


class BlenderViewerWidget(QWidget):
    """Blender 3D查看器控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.blender_client = None
        self._interactive_mode = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_label = QLabel("Blender 3D 预览")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setStyleSheet(
            "background: #1e1e2e; color: #a6adc8; font-size: 18px;"
        )
        layout.addWidget(self.image_label)

        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(5, 5, 5, 5)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["后台渲染", "交互模式"])
        self.mode_combo.setMinimumWidth(100)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        control_layout.addWidget(QLabel("模式:"))
        control_layout.addWidget(self.mode_combo)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self.refresh_view)
        control_layout.addWidget(self.refresh_btn)

        self.open_btn = QPushButton("🖼️ 打开Blender")
        self.open_btn.clicked.connect(self.open_blender)
        self.open_btn.setVisible(False)
        control_layout.addWidget(self.open_btn)

        self.status_label = QLabel("状态: 未连接")
        self.status_label.setStyleSheet("color: #a6adc8; padding: 5px;")
        control_layout.addWidget(self.status_label)

        control_layout.addStretch()
        layout.addLayout(control_layout)

        self.setVisible(False)

    def _on_mode_changed(self, mode: str):
        """模式切换"""
        if mode == "交互模式":
            self._interactive_mode = True
            self.refresh_btn.setVisible(False)
            self.open_btn.setVisible(True)
        else:
            self._interactive_mode = False
            self.refresh_btn.setVisible(True)
            self.open_btn.setVisible(False)

    def connect_blender(self, client):
        """连接Blender客户端"""
        self.blender_client = client
        self.status_label.setText("状态: 已连接")

    def open_blender(self):
        """打开Blender交互窗口"""
        if not self.blender_client:
            from bfds_viewer import BlenderClient

            self.blender_client = BlenderClient()

        self.status_label.setText("状态: 启动Blender交互模式...")

        try:
            ok = self.blender_client.start_interactive()
            if ok:
                self.status_label.setText("状态: 交互模式运行中 (可拖拽旋转)")
                self.image_label.setText(
                    "✅ Blender交互窗口已打开\n\n请在Blender窗口中:\n- 拖拽旋转视角\n- 滚轮缩放\n- 右键平移\n\n关闭窗口即停止"
                )
            else:
                self.status_label.setText("状态: 启动失败")
        except Exception as e:
            self.status_label.setText(f"状态: 错误 - {e}")

    def refresh_view(self):
        """刷新视图 - 后台渲染模式"""
        if not self.blender_client:
            from bfds_viewer import BlenderClient

            self.blender_client = BlenderClient()

        self.status_label.setText("状态: 渲染中...")

        code = """
import bpy
import math

L = 20
W = 15
H = 9
t = 0.24

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

for mat in bpy.data.materials:
    bpy.data.materials.remove(mat)

def create_mat(name, color):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color
    out = nodes.new(type="ShaderNodeOutputMaterial")
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
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

bpy.ops.object.light_add(type="SUN", location=(10, -10, 20))
sun = bpy.context.active_object
sun.data.energy = 3

bpy.context.scene.render.filepath = r"D:\\code\\fdsBuilder\\blender_render.png"
bpy.ops.render.render(write_still=True)
print("Scene ready and rendered")
"""
        result = self.blender_client.execute(code, timeout=60)
        print(f"Scene build: {result}")

        self.status_label.setText("状态: 已渲染 (点击刷新)")

    def render_and_update(self, model_data: dict):
        """渲染建筑模型"""
        if self._interactive_mode:
            self._update_interactive(model_data)
        else:
            self._render_background(model_data)

    def _render_background(self, model_data: dict):
        """后台渲染"""
        if not self.blender_client:
            from bfds_viewer import BlenderClient

            self.blender_client = BlenderClient()

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

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

def create_mat(name, color):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color
    out = nodes.new(type="ShaderNodeOutputMaterial")
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
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

bpy.ops.object.light_add(type="SUN", location=(10, -10, 20))
sun = bpy.context.active_object
sun.data.energy = 3

bpy.context.scene.render.filepath = r"D:\\code\\fdsBuilder\\blender_render.png"
bpy.ops.render.render(write_still=True)
print("Done")
"""
        self.status_label.setText("状态: 渲染中...")
        result = self.blender_client.execute(code, timeout=60)
        self.status_label.setText("状态: 渲染完成")

    def _update_interactive(self, model_data: dict):
        """通过socket更新交互模式"""
        if not self.blender_client or not self._interactive_mode:
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

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

for mat in bpy.data.materials:
    bpy.data.materials.remove(mat)

def create_mat(name, color):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color
    out = nodes.new(type="ShaderNodeOutputMaterial")
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
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

bpy.ops.object.light_add(type="SUN", location=(10, -10, 20))
sun = bpy.context.active_object
sun.data.energy = 3
"""

        try:
            result = self.blender_client.execute_interactive(code)
            print(f"Interactive update: {result}")
        except Exception as e:
            print(f"Interactive update error: {e}")

    def showEvent(self, event):
        """显示时初始化"""
        super().showEvent(event)
        if not self._interactive_mode and self.blender_client:
            self.refresh_view()

    def hideEvent(self, event):
        """隐藏时停止交互模式"""
        super().hideEvent(event)
        if self._interactive_mode and self.blender_client:
            self.blender_client.stop_interactive()
            self._interactive_mode = False
