# fdsBuilder

基于 PySide6、PyVista 和 FDS 的设施建模桌面程序。

## 获取 Windows 单文件 EXE

### 在 Windows 本机打包

要求 Windows 10/11 x64，并已安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)。在仓库根目录双击 `build_windows.bat`，或在命令提示符执行：

```bat
build_windows.bat
```

完成后可执行文件位于：

```text
dist\fdsBuilder.exe
```

该文件已经包含 Python、Qt、VTK、项目设施数据和毁伤预测模型，目标电脑不需要安装 Python。FDS/Smokeview 属于外部仿真软件，若使用“运行 FDS”或结果查看功能，仍需在程序设置中选择相应程序路径。

### 使用 GitHub Actions 打包（无需 Windows 电脑）

1. 打开 GitHub 仓库的 **Actions** 页面。
2. 选择 **Build Windows EXE**。
3. 点击 **Run workflow**。
4. 构建完成后，在该次运行页面的 **Artifacts** 下载 `fdsBuilder-windows-x64`。

也可推送以 `v` 开头的 tag（如 `v0.1.0`）自动触发构建。

## 开发运行

```bash
uv sync
uv run python main.py
```

## 打包说明

打包配置位于 `fdsBuilder.spec`。当前使用 PyInstaller 单文件窗口模式，因此首次启动时会先释放 Qt/VTK 等运行库，启动时间会比源码运行稍长。Windows EXE 必须在 Windows 环境构建；Linux 上执行同一 spec 只能生成 Linux 可执行文件，不能生成 `.exe`。
