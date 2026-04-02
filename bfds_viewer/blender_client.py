"""
Blender进程管理客户端
支持交互模式和后台模式
"""

import subprocess
import os
import time
import socket


class BlenderClient:
    """Blender进程管理"""

    BLENDER_PATH = r"D:\Software\Blender 4.5\blender.exe"
    STARTUP_BLEND = r"D:\code\fdsBuilder\bfds-7.0.0\startup.blend"

    def __init__(self):
        self._script_counter = 0
        self._scripts_dir = os.path.join(os.path.dirname(__file__), "_blender_scripts")
        os.makedirs(self._scripts_dir, exist_ok=True)
        self.process = None
        self._server_socket = None
        self._server_port = 9876

    def run_script(self, script: str, timeout: int = 60) -> str:
        """执行Python脚本，返回stdout (后台模式)"""
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

            return result.stdout
        finally:
            try:
                os.unlink(temp_script)
            except:
                pass

    def execute(self, code: str, timeout: int = 30) -> str:
        """发送代码到Blender执行"""
        return self.run_script(code, timeout)

    def start_interactive(self) -> bool:
        """启动Blender交互模式 - 打开窗口供用户交互"""
        self._script_counter = 0

        # 启动Blender交互模式（带窗口）
        script_path = os.path.join(self._scripts_dir, "interactive_startup.py")

        startup_code = f"""
import bpy
import socket
import threading
import time

PORT = {self._server_port}

# 基础场景
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

# 默认建筑
L, W, H, t = 20, 15, 9, 0.24
wall_color = (0.8, 0.8, 0.8, 1.0)
floor_color = (0.5, 0.5, 0.5, 1.0)

create_wall("wall_north", 0, W/2, H/2, L, t, H, wall_color)
create_wall("wall_south", 0, -W/2, H/2, L, t, H, wall_color)
create_wall("wall_west", -L/2, 0, H/2, t, W, H, wall_color)
create_wall("wall_east", L/2, 0, H/2, t, W, H, wall_color)
create_wall("floor", 0, 0, -0.1, L+2, W+2, 0.2, floor_color)

# 相机
import math
dist = max(L, W) * 1.5
bpy.ops.object.camera_add(location=(dist, -dist, H*0.8), rotation=(math.radians(60), 0, math.radians(45)))
camera = bpy.context.active_object
camera.name = "MainCamera"
bpy.context.scene.camera = camera

# 光照
bpy.ops.object.light_add(type="SUN", location=(10, -10, 20))
sun = bpy.context.active_object
sun.data.energy = 3

print("BLENDER_INTERACTIVE_READY")

# socket服务器
def handle_client(conn, addr):
    try:
        while True:
            data = conn.recv(16384)
            if not data:
                break
            code = data.decode("utf-8")
            try:
                exec(code, {{"bpy": bpy}})
                conn.send(b"OK")
            except Exception as e:
                conn.send(f"ERROR: {{e}}".encode("utf-8"))
    except:
        pass
    finally:
        conn.close()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", PORT))
sock.listen(1)
print(f"Server ready on port {{PORT}}")

while True:
    try:
        conn, addr = sock.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        thread.start()
    except:
        break
"""

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(startup_code)

        # 启动Blender（不带有--background，让窗口显示）
        self.process = subprocess.Popen(
            [self.BLENDER_PATH, "--python", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )

        # 等待Blender启动并socket就绪
        time.sleep(5)

        # 检查是否成功启动
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(2)
            test_sock.connect(("127.0.0.1", self._server_port))
            test_sock.send(b"print('connected')")
            response = test_sock.recv(1024)
            test_sock.close()
            print("Blender interactive mode started successfully")
            return True
        except Exception as e:
            print(f"Blender interactive mode start error: {e}")
            return False

    def execute_interactive(self, code: str) -> str:
        """通过socket发送代码到交互模式Blender"""
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Blender not running in interactive mode")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect(("127.0.0.1", self._server_port))
            sock.send(code.encode("utf-8"))
            response = sock.recv(8192).decode("utf-8")
            sock.close()
            return response
        except Exception as e:
            return f"ERROR: {e}"

    def stop_interactive(self):
        """停止交互模式Blender"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            self.process = None

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

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

create_bfds_obst("wall_north", 0, W/2, H/2, L, t, H)
create_bfds_obst("wall_south", 0, -W/2, H/2, L, t, H)
create_bfds_obst("wall_west", -L/2, 0, H/2, t, W, H)
create_bfds_obst("wall_east", L/2, 0, H/2, t, W, H)
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
