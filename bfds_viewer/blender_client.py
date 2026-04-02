"""
Blender进程管理客户端
启动Blender后台进程，发送Python脚本执行
"""

import subprocess
import os


class BlenderClient:
    """Blender进程管理"""

    BLENDER_PATH = r"D:\Software\Blender 4.5\blender.exe"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.process = None

    def run_script(self, script: str, timeout: int = 60) -> str:
        """执行Python脚本，返回stdout"""
        args = [self.BLENDER_PATH, "--background", "--python", "-"]

        result = subprocess.run(
            args,
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            raise RuntimeError(f"Blender error: {result.stderr}")

        return result.stdout

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

    def export_fds(self, output_path: str):
        """使用BFDS插件导出FDS"""
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
