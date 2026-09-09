#!/usr/bin/env python3
"""Generate standalone presentation diagrams and reproducible UI screenshots."""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "presentation" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_MEDIUM = "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"
FONT_BOLD = "/home/blue/.local/share/fonts/SourceHanSansSC-Bold.otf"
if not Path(FONT_BOLD).exists():
    FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

COLORS = {
    "bg0": "#07111f",
    "bg1": "#101d33",
    "panel": "#17253d",
    "panel2": "#1d2d49",
    "ink": "#eef6ff",
    "muted": "#a9bdd6",
    "blue": "#55a7ff",
    "cyan": "#41d8d0",
    "green": "#70e0a1",
    "amber": "#ffc76b",
    "orange": "#ff8a66",
    "red": "#ff6f91",
    "purple": "#b59cff",
    "line": "#355070",
}


def font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def gradient_canvas(w: int, h: int) -> Image.Image:
    top = (7, 17, 31)
    bottom = (16, 29, 51)
    im = Image.new("RGB", (w, h), top)
    px = im.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        row = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    draw = ImageDraw.Draw(im, "RGBA")
    for x in range(0, w, 80):
        draw.line((x, 0, x, h), fill=(80, 130, 180, 18), width=1)
    for y in range(0, h, 80):
        draw.line((0, y, w, y), fill=(80, 130, 180, 18), width=1)
    draw.ellipse((w - 560, -260, w + 180, 480), fill=(70, 160, 255, 18))
    draw.ellipse((-300, h - 420, 450, h + 260), fill=(65, 216, 208, 13))
    return im


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        if not paragraph:
            lines.append("")
            continue
        line = ""
        for char in paragraph:
            candidate = line + char
            if line and draw.textlength(candidate, font=fnt) > max_width:
                lines.append(line)
                line = char
            else:
                line = candidate
        if line:
            lines.append(line)
    return lines


def center_text(draw, box, text, fnt, fill, spacing=10, max_width=None):
    x1, y1, x2, y2 = box
    max_width = max_width or int(x2 - x1 - 24)
    lines = wrap_text(draw, text, fnt, max_width)
    bboxes = [draw.textbbox((0, 0), line, font=fnt) for line in lines]
    heights = [b[3] - b[1] for b in bboxes]
    total_h = sum(heights) + spacing * max(len(lines) - 1, 0)
    y = y1 + (y2 - y1 - total_h) / 2
    for line, bb, hh in zip(lines, bboxes, heights):
        ww = bb[2] - bb[0]
        draw.text((x1 + (x2 - x1 - ww) / 2, y), line, font=fnt, fill=fill)
        y += hh + spacing


def shadow_card(im, box, fill, outline=None, radius=28, shadow=18):
    x1, y1, x2, y2 = map(int, box)
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x1 + 8, y1 + 12, x2 + 8, y2 + 12), radius=radius, fill=(0, 0, 0, 125))
    layer = layer.filter(ImageFilter.GaussianBlur(shadow))
    im.paste(layer, (0, 0), layer)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=fill, outline=outline, width=2 if outline else 1)


def arrow(draw, p1, p2, color, width=8, head=22):
    x1, y1 = p1
    x2, y2 = p2
    draw.line((x1, y1, x2, y2), fill=color, width=width)
    ang = math.atan2(y2 - y1, x2 - x1)
    left = (x2 - head * math.cos(ang - math.pi / 6), y2 - head * math.sin(ang - math.pi / 6))
    right = (x2 - head * math.cos(ang + math.pi / 6), y2 - head * math.sin(ang + math.pi / 6))
    draw.polygon([(x2, y2), left, right], fill=color)


def title_block(draw, title, subtitle, w):
    draw.text((110, 66), title, font=font(58, True), fill=COLORS["ink"])
    draw.rounded_rectangle((110, 148, 310, 157), radius=5, fill=COLORS["cyan"])
    draw.text((110, 178), subtitle, font=font(25), fill=COLORS["muted"])
    draw.text((w - 310, 78), "损伤预测系统", font=font(23, True), fill=COLORS["blue"])


def draw_pills(draw, box, items, accent):
    x1, y1, x2, y2 = box
    gap = 18
    widths = [int(draw.textlength(i, font=font(24)) + 42) for i in items]
    total = sum(widths) + gap * (len(items) - 1)
    x = x1 + (x2 - x1 - total) / 2
    for item, ww in zip(items, widths):
        draw.rounded_rectangle((x, y1, x + ww, y2), radius=18, fill="#223653", outline=accent, width=2)
        center_text(draw, (x, y1, x + ww, y2), item, font(24), COLORS["ink"])
        x += ww + gap


def generate_architecture():
    w, h = 2400, 1350
    im = gradient_canvas(w, h)
    d = ImageDraw.Draw(im)
    title_block(d, "系统总体架构", "交互、领域模型、生成计算与工程预测形成一条可追踪的数据链", w)

    layers = [
        ("01", "可视化交互层", ["设施 / 规模选择", "可燃物管理", "3D 场景交互", "热源与仿真控制", "FDS 代码预览"], COLORS["blue"]),
        ("02", "可计算领域模型", ["BuildingGroup", "建筑 · 楼层 · 防火分区", "门窗与材料", "设备 · 可燃物 · 敏感目标"], COLORS["cyan"]),
        ("03", "建模与生成引擎", ["参数映射", "场景布局", "几何 / 网格处理", "FDS 生成与语法校验"], COLORS["green"]),
        ("04", "双计算引擎", ["FDS 高保真求解", "Smokeview 结果查看", "ExtraTrees 工程代理模型", "已观测权威工况查表"], COLORS["amber"]),
        ("05", "工程输出层", [".fds / .smv", "温度 · 热通量切片", "Dk + 四级损伤", "准确率 · 耗时 · 结果归档"], COLORS["purple"]),
    ]
    y = 280
    card_h = 160
    gap = 30
    for idx, (num, name, pills, accent) in enumerate(layers):
        box = (105, y, w - 105, y + card_h)
        shadow_card(im, box, COLORS["panel"], accent, radius=26, shadow=12)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((130, y + 36, 220, y + 126), radius=22, fill=accent)
        center_text(d, (130, y + 36, 220, y + 126), num, font(31, True), COLORS["bg0"])
        d.text((255, y + 52), name, font=font(33, True), fill=COLORS["ink"])
        draw_pills(d, (665, y + 45, w - 140, y + 120), pills, accent)
        if idx < len(layers) - 1:
            arrow(d, (w / 2, y + card_h + 3), (w / 2, y + card_h + gap - 5), accent, width=6, head=18)
        y += card_h + gap

    d.rounded_rectangle((w - 505, h - 88, w - 110, h - 40), radius=22, fill="#1b2d48", outline=COLORS["line"], width=2)
    center_text(d, (w - 505, h - 88, w - 110, h - 40), "外部能力：FDS · Smokeview · 文件系统", font(20), COLORS["muted"])
    im.save(ASSETS / "system_architecture.png", quality=95)


def generate_quick_flow():
    w, h = 2400, 1100
    im = gradient_canvas(w, h)
    d = ImageDraw.Draw(im)
    title_block(d, "快速建模流程", "以模板选择替代重复手工建模，关键参数始终可见、可改、可导出", w)
    steps = [
        ("1", "选择设施", "等效 / 特异模型", COLORS["blue"]),
        ("2", "确定规模", "小 · 中 · 大", COLORS["cyan"]),
        ("3", "配置资产", "可燃物与敏感目标", COLORS["green"]),
        ("4", "生成设施", "自动映射几何与布局", COLORS["amber"]),
        ("5", "设置工况", "方向 · 热通量 · 时长", COLORS["orange"]),
        ("6", "选择计算", "快速预测 / FDS", COLORS["purple"]),
    ]
    margin = 105
    gap = 30
    card_w = int((w - 2 * margin - 5 * gap) / 6)
    y1, y2 = 340, 720
    for i, (num, title, sub, accent) in enumerate(steps):
        x1 = margin + i * (card_w + gap)
        x2 = x1 + card_w
        shadow_card(im, (x1, y1, x2, y2), COLORS["panel"], accent, radius=30, shadow=14)
        d = ImageDraw.Draw(im)
        d.ellipse((x1 + 30, y1 + 28, x1 + 102, y1 + 100), fill=accent)
        center_text(d, (x1 + 30, y1 + 28, x1 + 102, y1 + 100), num, font(28, True), COLORS["bg0"])
        center_text(d, (x1 + 24, y1 + 125, x2 - 24, y1 + 230), title, font(32, True), COLORS["ink"])
        center_text(d, (x1 + 25, y1 + 245, x2 - 25, y2 - 30), sub, font(23), COLORS["muted"])
        if i < len(steps) - 1:
            arrow(d, (x2 + 5, (y1 + y2) / 2), (x2 + gap - 5, (y1 + y2) / 2), accent, width=6, head=16)

    # Bottom outputs
    outputs = [
        ("秒级输出", "Dk、损伤等级、综合验证准确率", COLORS["cyan"]),
        ("高保真输出", "FDS 输入、切片 / 设备数据、Smokeview 场景", COLORS["orange"]),
    ]
    x = 360
    for title, sub, accent in outputs:
        shadow_card(im, (x, 820, x + 760, 990), "#14253d", accent, radius=25, shadow=10)
        d = ImageDraw.Draw(im)
        d.text((x + 35, 852), title, font=font(28, True), fill=accent)
        d.text((x + 35, 916), sub, font=font(23), fill=COLORS["muted"])
        x += 920
    im.save(ASSETS / "quick_modeling_flow.png", quality=95)


def generate_equivalent_logic():
    w, h = 2400, 1200
    im = gradient_canvas(w, h)
    d = ImageDraw.Draw(im)
    title_block(d, "可计算等效模型", "“规模”不是图片缩放，而是结构、开口、分区、资产数量与计算域的协同参数化", w)

    # Scale selectors
    sx = 120
    for i, (name, color) in enumerate([("小型 S", COLORS["green"]), ("中型 M", COLORS["blue"]), ("大型 L", COLORS["purple"])]):
        y = 350 + i * 190
        shadow_card(im, (sx, y, sx + 350, y + 135), COLORS["panel"], color, radius=26, shadow=10)
        d = ImageDraw.Draw(im)
        d.ellipse((sx + 30, y + 32, sx + 101, y + 103), fill=color)
        center_text(d, (sx + 115, y + 20, sx + 330, y + 115), name, font(30, True), COLORS["ink"])
        arrow(d, (sx + 350, y + 68), (650, 640), color, width=6, head=20)

    shadow_card(im, (650, 430, 1120, 845), "#182b45", COLORS["cyan"], radius=34, shadow=16)
    d = ImageDraw.Draw(im)
    center_text(d, (690, 450, 1080, 545), "参数映射引擎", font(38, True), COLORS["cyan"])
    mapping = ["长度 / 宽度 / 高度", "楼层与防火分区", "门窗比例与材料", "可燃物 / 设备数量", "设施级布局与间距"]
    for i, item in enumerate(mapping):
        yy = 570 + i * 52
        d.ellipse((720, yy + 8, 735, yy + 23), fill=COLORS["cyan"])
        d.text((755, yy), item, font=font(24), fill=COLORS["ink"])

    arrow(d, (1120, 638), (1300, 638), COLORS["cyan"], width=9, head=26)
    # Hierarchy stack
    levels = [
        ("设施 BuildingGroup", COLORS["blue"], 0),
        ("建筑 Building", COLORS["cyan"], 40),
        ("楼层 Story", COLORS["green"], 80),
        ("防火分区 Compartment", COLORS["amber"], 120),
        ("开口 · 可燃物 · 专用设备", COLORS["orange"], 160),
    ]
    for i, (label, color, indent) in enumerate(levels):
        y = 325 + i * 130
        x1 = 1300 + indent
        x2 = 2040 - indent / 2
        shadow_card(im, (x1, y, x2, y + 94), "#1a2d48", color, radius=22, shadow=8)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((x1 + 18, y + 18, x1 + 72, y + 76), radius=16, fill=color)
        d.text((x1 + 96, y + 24), label, font=font(27, True), fill=COLORS["ink"])

    arrow(d, (2045, 638), (2250, 638), COLORS["amber"], width=8, head=24)
    shadow_card(im, (2140, 450, 2330, 825), "#172a43", COLORS["amber"], radius=28, shadow=12)
    d = ImageDraw.Draw(im)
    center_text(d, (2160, 470, 2310, 560), "可计算\n模型", font(31, True), COLORS["amber"])
    center_text(d, (2160, 590, 2310, 790), "FDS 几何\n网格与边界\n设备与切片\n预测特征", font(22), COLORS["ink"], spacing=12)

    draw_pills(d, (700, 1010, 2120, 1085), ["尺度一致", "语义一致", "可复现", "可序列化", "可直接计算"], COLORS["cyan"])
    im.save(ASSETS / "equivalent_model_logic.png", quality=95)


def generate_dual_track():
    w, h = 2400, 1180
    im = gradient_canvas(w, h)
    d = ImageDraw.Draw(im)
    title_block(d, "工程预测代理模型集成", "同一场景、同一工况、两条计算路径：快速筛查与高保真复核", w)

    # Input
    shadow_card(im, (110, 430, 470, 760), COLORS["panel"], COLORS["blue"], radius=30, shadow=14)
    d = ImageDraw.Draw(im)
    center_text(d, (140, 455, 440, 535), "统一输入", font(36, True), COLORS["blue"])
    center_text(d, (145, 560, 435, 725), "设施身份与规模\n方位角 / 俯仰角\n热通量 / 持续时间", font(25), COLORS["ink"], spacing=16)
    arrow(d, (470, 595), (660, 595), COLORS["blue"], width=9, head=26)

    shadow_card(im, (660, 390, 1030, 800), "#172b46", COLORS["cyan"], radius=30, shadow=14)
    d = ImageDraw.Draw(im)
    center_text(d, (690, 420, 1000, 510), "特征与工况构建", font(32, True), COLORS["cyan"])
    center_text(d, (700, 540, 990, 765), "热源特征\n建筑 / 开口特征\n可燃物与敏感目标\nFDS 工况命名与校验", font(24), COLORS["ink"], spacing=15)

    # Branch arrows
    arrow(d, (1030, 515), (1225, 385), COLORS["green"], width=8, head=24)
    arrow(d, (1030, 675), (1225, 805), COLORS["orange"], width=8, head=24)

    shadow_card(im, (1225, 250, 1710, 545), "#173144", COLORS["green"], radius=30, shadow=15)
    d = ImageDraw.Draw(im)
    center_text(d, (1255, 275, 1680, 350), "快速路径 · ExtraTrees", font(32, True), COLORS["green"])
    center_text(d, (1260, 385, 1675, 510), "权威已观测工况优先查表\n否则输出连续 Dk + 四级损伤", font(23), COLORS["ink"], spacing=14)

    shadow_card(im, (1225, 665, 1710, 960), "#37273a", COLORS["orange"], radius=30, shadow=15)
    d = ImageDraw.Draw(im)
    center_text(d, (1255, 690, 1680, 765), "高保真路径 · FDS", font(32, True), COLORS["orange"])
    center_text(d, (1260, 800, 1675, 925), "求解温度 / 热通量场\nSmokeview 查看并形成复核依据", font(23), COLORS["ink"], spacing=14)

    arrow(d, (1710, 400), (1900, 565), COLORS["green"], width=8, head=24)
    arrow(d, (1710, 815), (1900, 650), COLORS["orange"], width=8, head=24)
    shadow_card(im, (1900, 400, 2290, 810), "#1b2b46", COLORS["purple"], radius=32, shadow=16)
    d = ImageDraw.Draw(im)
    center_text(d, (1930, 430, 2260, 520), "工程判读", font(38, True), COLORS["purple"])
    center_text(d, (1940, 555, 2250, 760), "一般工况：快速筛查\n等级边界：建议复核\n关键决策：FDS 复核\n结果归档：持续迭代", font(24), COLORS["ink"], spacing=16)

    d.text((120, 1035), "适用边界：当前代理模型面向已知设施模板的新工况；未知设施不做静默外推。", font=font(26, True), fill=COLORS["amber"])
    im.save(ASSETS / "surrogate_fds_dual_track.png", quality=95)


def build_aerospace_model():
    from models.building import BuildingGroup
    from models.facility import FacilityManager

    manager = FacilityManager()
    buildings = []
    for name in manager.list_buildings("aerospace"):
        params = manager.params_for_scale("aerospace", name, scale_idx=1)
        buildings.append(manager.load_equivalent("aerospace", name, params))
    manager.arrange_buildings_by_layout("aerospace", buildings)
    group = BuildingGroup(name="aerospace", buildings=buildings)
    group.heat_source = {"azimuth": 270, "elevation": 30, "net_heat_flux": 15000, "duration": 2.1}
    group.simulation_time = 1800
    group.update_z_offsets()
    return group


def cuboid_faces(x, y, z, dx, dy, dz):
    p = [
        (x, y, z), (x + dx, y, z), (x + dx, y + dy, z), (x, y + dy, z),
        (x, y, z + dz), (x + dx, y, z + dz), (x + dx, y + dy, z + dz), (x, y + dy, z + dz),
    ]
    return [[p[i] for i in face] for face in [(0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]]


def generate_model_render(group):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from matplotlib.font_manager import FontProperties

    fig = plt.figure(figsize=(16, 9), dpi=160, facecolor="#101a2d")
    ax = fig.add_subplot(111, projection="3d", facecolor="#101a2d")
    palette = ["#55a7ff", "#41d8d0", "#70e0a1", "#ffc76b", "#b59cff"]
    fp = FontProperties(fname=FONT_REGULAR, size=10)
    max_x = max(b.offset_x + b.length for b in group.buildings)
    max_y = max(b.offset_y + b.width for b in group.buildings)
    max_z = max(b.height for b in group.buildings)
    for i, b in enumerate(group.buildings):
        color = palette[i % len(palette)]
        faces = cuboid_faces(b.offset_x, b.offset_y, 0, b.length, b.width, b.height)
        poly = Poly3DCollection(faces, facecolors=color, edgecolors="#d9ecff", linewidths=0.7, alpha=0.76)
        ax.add_collection3d(poly)
        z = 0
        for story in b.stories[:-1]:
            z += story.height
            ax.plot([b.offset_x, b.offset_x+b.length], [b.offset_y, b.offset_y], [z,z], color="#ecf7ff", alpha=.65, lw=.7)
            ax.plot([b.offset_x, b.offset_x], [b.offset_y, b.offset_y+b.width], [z,z], color="#ecf7ff", alpha=.65, lw=.7)
        ax.text(b.offset_x + b.length/2, b.offset_y + b.width/2, b.height + max_z*0.08,
                b.cn_name or b.name, color="#f2f7ff", ha="center", va="bottom", fontproperties=fp,
                bbox=dict(boxstyle="round,pad=.25", facecolor="#0b1425", edgecolor=color, alpha=.9))
    # Heat-source direction arrow from the south-west toward the scene.
    sx, sy, sz = -max_x*0.12, max_y*0.12, max_z*1.55
    tx, ty, tz = max_x*0.42, max_y*0.45, max_z*0.45
    ax.quiver(sx, sy, sz, tx-sx, ty-sy, tz-sz, color="#ff6f91", linewidth=3.2, arrow_length_ratio=.12)
    ax.text(sx, sy, sz+max_z*.08, "外部热辐射", color="#ff9cb3", fontproperties=FontProperties(fname=FONT_BOLD, size=12))

    ax.set_xlim(-max_x*.12, max_x*1.06)
    ax.set_ylim(-max_y*.08, max_y*1.06)
    ax.set_zlim(0, max_z*1.85)
    ax.view_init(elev=27, azim=-58)
    ax.set_box_aspect((max_x, max_y, max_z*2.0))
    ax.set_axis_off()
    fig.text(.04, .94, "航空航天等效设施 · 中型场景", color="#f1f7ff", fontsize=23, fontproperties=FontProperties(fname=FONT_BOLD))
    fig.text(.04, .895, "5 栋建筑 · 参数化布局 · 热源方向可视化", color="#9eb5cf", fontsize=13, fontproperties=fp)
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.98)
    path = ASSETS / "program_3d_view.png"
    # Preserve an exact 16:9 raster for predictable placement in the GUI and PPT.
    fig.savefig(path, facecolor=fig.get_facecolor(), dpi=160)
    plt.close(fig)
    return path


def capture_program(group, render_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # The CI/container has no X server. Use the application's own fallback
    # viewer widget and inject an off-screen rendering built from the same model.
    import ui.viewer_3d as viewer_module
    viewer_module.HAS_PYVISTA = False
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication, QLabel
    from ui.mainwindow import MainWindow
    from ui.styles import DARK_STYLE

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    win = MainWindow()
    win.showNormal()
    win.resize(1920, 1080)
    win.splitter.setSizes([470, 950, 470])
    win._on_facility_selected(group.to_dict())

    panel = win.facility_panel
    root = panel.facility_tree.topLevelItem(0)
    target = None
    for i in range(root.childCount()):
        item = root.child(i)
        data = item.data(0, Qt.UserRole) or {}
        if data.get("facility") == "aerospace":
            target = item
            break
    if target is not None:
        panel.facility_tree.setCurrentItem(target)
        panel._on_tree_clicked(target, 0)
    panel.size_combo.setCurrentText("中")
    win.simulation_control.set_model(win.model)
    win.update_preview(debounce=False)
    win.statusBar().showMessage("航空航天设施（中型）已生成 · 5 栋建筑")
    win.show()
    for _ in range(12):
        app.processEvents()

    labels = win.viewer_3d.findChildren(QLabel)
    if labels:
        label = labels[0]
        pix = QPixmap(str(render_path))
        pix = pix.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setText("")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("background:#101a2d;border:1px solid #33445f;")
        label.setPixmap(pix)
    for _ in range(6):
        app.processEvents()

    screenshot = ASSETS / "program_main_ui.png"
    win.grab().save(str(screenshot))
    win.close()
    app.processEvents()

    # Reusable close-up assets for slides.
    im = Image.open(screenshot).convert("RGB")
    w, h = im.size
    im.crop((0, 25, int(w * .27), h)).save(ASSETS / "program_ui_modeling_detail.png", quality=96)
    im.crop((int(w * .73), 25, w, h)).save(ASSETS / "program_ui_simulation_detail.png", quality=96)


def capture_prediction_dialog(group):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from agent_damage.src.inference.split_model_predictor import load_split_model_predictor
    from services.damage_prediction import predict_current_model
    from ui.damage_result_dialog import ExperimentalDamageResultDialog
    from ui.styles import DARK_STYLE

    predictor = load_split_model_predictor()
    context = predict_current_model(group, predictor)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    dlg = ExperimentalDamageResultDialog(
        context=context,
        heat_source={"azimuth": 270.0, "elevation": 30.0, "heat_flux": 15000.0, "duration": 2.1},
        infer_time_ms=18.4,
    )
    dlg.resize(920, 500)
    dlg.show()
    for _ in range(8):
        app.processEvents()
    dlg.grab().save(str(ASSETS / "program_prediction_dialog.png"))
    dlg.close()
    app.processEvents()


def main():
    generate_architecture()
    generate_quick_flow()
    generate_equivalent_logic()
    generate_dual_track()
    group = build_aerospace_model()
    render_path = generate_model_render(group)
    capture_program(group, render_path)
    capture_prediction_dialog(group)
    for p in sorted(ASSETS.glob("*.png")):
        print(f"{p.relative_to(ROOT)}\t{p.stat().st_size / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
