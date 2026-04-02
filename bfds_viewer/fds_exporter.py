"""
FDS文件导出器
使用BFDS插件导出FDS文件
"""

import bpy


class FDSExporter:
    """FDS导出器"""

    def __init__(self):
        self.model = None

    def set_model(self, model):
        """设置建筑模型"""
        self.model = model
        return self

    def export(self, output_path: str) -> bool:
        """导出FDS文件"""
        if not self.model:
            raise ValueError("Model not set")

        self._prepare_bfds_objects()

        try:
            bpy.ops.bfds.export_fds(
                filepath=output_path, export_settings={"chid": self.model.chid}
            )
            return True
        except Exception as e:
            print(f"BFDS export failed: {e}")
            return False

    def _prepare_bfds_objects(self):
        """准备BFDS所需的对象"""
        pass
