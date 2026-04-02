"""
Blender进程管理客户端
支持一次性脚本和持续运行模式
"""

import subprocess
import os
import socket
import threading
import time


class BlenderClient:
    """Blender进程管理 - 支持持续运行"""

    BLENDER_PATH = r"D:\Software\Blender 4.5\blender.exe"
    STARTUP_BLEND = r"D:\code\fdsBuilder\bfds-7.0.0\startup.blend"

    def __init__(self):
        self.process = None  # type: subprocess.Popen
        self.socket_port = None
        self._server_ready = False

    def run_script(self, script: str, timeout: int = 60) -> str:
        """执行Python脚本，返回stdout (一次性模式)"""
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            temp_script = f.name

        try:
            args = [self.BLENDER_PATH, "--background", "--python", temp_script]

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                raise RuntimeError(f"Blender error: {result.stderr}")

            if result.stderr and "error" in result.stderr.lower():
                print(f"Blender warning: {result.stderr}")

            return result.stdout
        finally:
            try:
                os.unlink(temp_script)
            except:
                pass

    def start_server(self, port: int = 9876) -> bool:
        """启动Blender后台模式 (简化实现: 保持进程运行)"""
        self.socket_port = port
        self._script_counter = 0
        self._scripts_dir = os.path.join(os.path.dirname(__file__), "_blender_scripts")
        os.makedirs(self._scripts_dir, exist_ok=True)

        self.process = subprocess.Popen(
            [self.BLENDER_PATH, "--background"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )

        time.sleep(3)
        self._server_ready = True
        print(f"Blender started in background mode")
        return True

    def execute(self, code: str, timeout: int = 30) -> str:
        """发送代码到Blender执行 (通过临时文件)"""
        if not self.process or not self._server_ready:
            raise RuntimeError("Blender not started")

        self._script_counter += 1
        script_path = os.path.join(
            self._scripts_dir, f"script_{self._script_counter}.py"
        )

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        args = [self.BLENDER_PATH, "--background", "--python", script_path]

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

        os.unlink(script_path)

        if result.returncode != 0:
            return f"ERROR: {result.stderr}"

        return result.stdout

    def load_startup(self) -> str:
        """加载BFDS startup.blend"""
        code = f'''
import bpy
bpy.ops.wm.open_mainfile(filepath=r"{self.STARTUP_BLEND}")
print("BFDS startup.blend loaded")
'''
        return self.execute(code)

    def create_building(
        self, length: float, width: float, height: float, wall_thickness: float = 0.24
    ) -> str:
        """创建建筑物体"""
        code = f"""
import bpy

L = {length}
W = {width}
H = {height}
t = {wall_thickness}

def create_bfds_obst(name, x, y, z, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)
    return obj

# 清空现有物体
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 外墙
create_bfds_obst("wall_north", 0, W/2, H/2, L, t, H)
create_bfds_obst("wall_south", 0, -W/2, H/2, L, t, H)
create_bfds_obst("wall_west", -L/2, 0, H/2, t, W, H)
create_bfds_obst("wall_east", L/2, 0, H/2, t, W, H)

# 地面
create_bfds_obst("floor", 0, 0, -0.1, L+2, W+2, 0.2)

print(f"Building created: {{L}}x{{W}}x{{H}}")
"""
        return self.execute(code)

    def export_fds(self, output_path: str) -> str:
        """导出FDS文件"""
        code = f'''
import bpy
output = r"{output_path}"
try:
    bpy.ops.export_scene.fds(filepath=output)
    print(f"FDS exported: {{output}}")
except Exception as e:
    print(f"Export error: {{e}}")
'''
        return self.execute(code)

    def render_to_image(self, width: int = 1920, height: int = 1080) -> str:
        """渲染场景到内存并返回"""
        code = f"""
import bpy
import io
from PIL import Image
import bpy.path

bpy.context.scene.render.resolution_x = {width}
bpy.context.scene.render.resolution_y = {height}
bpy.context.scene.render.film_transparent = True

# 渲染
bpy.ops.render.render(scene=bpy.context.scene, write_still=False)
print("RENDER_DONE")
"""
        return self.execute(code)

    def stop(self):
        """停止Blender服务器"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self._server_ready = False

    def render_scene(self, output_path: str, width: int = 1920, height: int = 1080):
        """渲染场景到文件"""
        script = f'''
import bpy
bpy.context.scene.render.filepath = r"{output_path}"
bpy.context.scene.render.resolution_x = {width}
bpy.context.scene.render.resolution_y = {height}
bpy.ops.render.render(write_still=True)
'''
        self.run_script(script)

    def export_fds_simple(self, output_path: str):
        """使用BFDS插件导出FDS (一次性模式)"""
        script = f'''
import bpy
try:
    bpy.ops.bfds.export_fds(filepath=r"{output_path}")
    print(f"FDS exported: {output_path}")
except Exception as e:
    print(f"BFDS export error: {{e}}")
'''
        return self.run_script(script)

    def check_addons(self) -> list:
        """检查已安装的插件"""
        script = """
import bpy
addons = list(bpy.context.preferences.addons.keys())
print("INSTALLED_ADDONS:" + ",".join(addons))
"""
        result = self.run_script(script)

        for line in result.split("\n"):
            if line.startswith("INSTALLED_ADDONS:"):
                addons_str = line.split(":", 1)[1]
                return addons_str.split(",") if addons_str else []
        return []
