# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the distributable fdsBuilder desktop application."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)

# PyVista/VTK and scikit-learn are handled by PyInstaller's official hooks.
# Avoid collect_all here: it also sweeps in optional documentation, tests,
# Torch and notebook stacks, making the executable several gigabytes larger.
datas = [
    (str(ROOT / "facilities"), "facilities"),
    (
        str(ROOT / "agent_damage" / "checkpoints" / "experimental_dk_regressor.pkl"),
        "agent_damage/checkpoints",
    ),
]
binaries = []
hiddenimports = collect_submodules("agent_damage.src")

analysis = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "runtime_hook.py")],
    excludes=[
        "pytest",
        "IPython",
        "notebook",
        "jupyter",
        "sphinx",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="fdsBuilder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
