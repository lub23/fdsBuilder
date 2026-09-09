#!/usr/bin/env python3
"""Build the polished Chinese system introduction deck."""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "presentation" / "assets"
OUT = ROOT / "presentation" / "output"
OUT.mkdir(parents=True, exist_ok=True)
FIGURES = ROOT / "agent_damage" / "output" / "experimental_figures"

SW, SH = Inches(13.333333), Inches(7.5)
FONT = "Microsoft YaHei"
MONO = "Consolas"

C = {
    "bg": "08131F",
    "bg2": "0F1D30",
    "panel": "14253D",
    "panel2": "1A2D49",
    "line": "36516F",
    "white": "F4F8FD",
    "muted": "A9BDD6",
    "blue": "55A7FF",
    "cyan": "41D8D0",
    "green": "70E0A1",
    "amber": "FFC76B",
    "orange": "FF8A66",
    "red": "FF6F91",
    "purple": "B59CFF",
    "dark": "07111F",
}


def rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr.replace("#", ""))


def set_bg(slide, color=C["bg"]):
    shape = slide.background.fill
    shape.solid()
    shape.fore_color.rgb = rgb(color)


def add_rect(slide, x, y, w, h, fill, line=None, radius=True):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(fill)
    shp.line.color.rgb = rgb(line or fill)
    shp.line.width = Pt(1)
    return shp


def set_text(shape, text, size=18, color=C["white"], bold=False,
             align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.MIDDLE, font_name=FONT,
             margins=(0.08, 0.08, 0.05, 0.05), line_spacing=1.0):
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = valign
    tf.margin_left = Inches(margins[0])
    tf.margin_right = Inches(margins[1])
    tf.margin_top = Inches(margins[2])
    tf.margin_bottom = Inches(margins[3])
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line_spacing
    run = p.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)
    return shape


def add_text(slide, text, x, y, w, h, size=18, color=C["white"], bold=False,
             align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.MIDDLE, font_name=FONT,
             margins=(0, 0, 0, 0), line_spacing=1.0):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    return set_text(box, text, size, color, bold, align, valign, font_name, margins, line_spacing)


def add_bullets(slide, items, x, y, w, h, size=17, color=C["white"],
                bullet_color=None, spacing=7, levels=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(0.02)
    tf.margin_right = Inches(0.02)
    tf.margin_top = Inches(0.02)
    for idx, item in enumerate(items):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = item
        p.font.name = FONT
        p.font.size = Pt(size)
        p.font.color.rgb = rgb(color)
        p.level = (levels[idx] if levels else 0)
        p.space_after = Pt(spacing)
        p.line_spacing = 1.08
        # Native bullet support is not consistently exposed across Office suites;
        # use a stable glyph instead.
        p.text = ("•  " if p.level == 0 else "–  ") + item
    return box


def add_title(slide, eyebrow, title, subtitle=None, slide_no=None):
    add_text(slide, eyebrow.upper(), 0.7, 0.30, 4.2, 0.32, 10.5, C["cyan"], True)
    add_text(slide, title, 0.7, 0.65, 11.8, 0.62, 28, C["white"], True)
    add_rect(slide, 0.7, 1.29, 1.2, 0.045, C["cyan"], C["cyan"], radius=False)
    if subtitle:
        add_text(slide, subtitle, 0.7, 1.40, 11.8, 0.34, 12, C["muted"])
    if slide_no is not None:
        add_text(slide, f"{slide_no:02d}", 12.15, 0.30, 0.48, 0.32, 10.5, C["muted"], True, PP_ALIGN.RIGHT)


def add_footer(slide, slide_no, note="设施火灾热辐射建模与损伤预测系统"):
    add_rect(slide, 0.7, 7.20, 11.95, 0.012, C["line"], C["line"], radius=False)
    add_text(slide, note, 0.7, 7.23, 8.8, 0.18, 8.5, C["muted"])
    add_text(slide, f"{slide_no:02d}", 12.0, 7.23, 0.65, 0.18, 8.5, C["muted"], True, PP_ALIGN.RIGHT)


def add_image_contain(slide, path, x, y, w, h, card=True, pad=0.08):
    path = Path(path)
    if card:
        add_rect(slide, x, y, w, h, C["panel"], C["line"], radius=True)
        x, y, w, h = x + pad, y + pad, w - 2 * pad, h - 2 * pad
    with Image.open(path) as im:
        iw, ih = im.size
    image_ratio = iw / ih
    box_ratio = w / h
    if image_ratio > box_ratio:
        pw = w
        ph = w / image_ratio
        px, py = x, y + (h - ph) / 2
    else:
        ph = h
        pw = h * image_ratio
        px, py = x + (w - pw) / 2, y
    return slide.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(pw), Inches(ph))


def add_image_crop(slide, path, x, y, w, h, card=False):
    path = Path(path)
    if card:
        add_rect(slide, x, y, w, h, C["panel"], C["line"], radius=True)
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    with Image.open(path) as im:
        iw, ih = im.size
    image_ratio = iw / ih
    box_ratio = w / h
    if image_ratio > box_ratio:
        visible = box_ratio / image_ratio
        crop = (1 - visible) / 2
        pic.crop_left = crop
        pic.crop_right = crop
    elif image_ratio < box_ratio:
        visible = image_ratio / box_ratio
        crop = (1 - visible) / 2
        pic.crop_top = crop
        pic.crop_bottom = crop
    return pic


def metric(slide, x, y, w, value, label, accent=C["cyan"], sub=None):
    add_rect(slide, x, y, w, 1.25, C["panel"], accent)
    add_rect(slide, x, y, 0.07, 1.25, accent, accent, radius=False)
    add_text(slide, value, x + 0.22, y + 0.12, w - 0.35, 0.48, 24, accent, True)
    add_text(slide, label, x + 0.22, y + 0.62, w - 0.35, 0.25, 11, C["white"], True)
    if sub:
        add_text(slide, sub, x + 0.22, y + 0.91, w - 0.35, 0.20, 8.5, C["muted"])


def card_title(slide, title, x, y, w, accent=C["cyan"], number=None):
    if number:
        add_rect(slide, x, y, 0.46, 0.46, accent, accent)
        set_text(slide.shapes[-1], number, 13, C["dark"], True, PP_ALIGN.CENTER)
        x += 0.60
        w -= 0.60
    add_text(slide, title, x, y, w, 0.46, 16, C["white"], True)


def new_slide(prs, no, eyebrow, title, subtitle=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_title(slide, eyebrow, title, subtitle, no)
    add_footer(slide, no)
    return slide


def build_deck():
    prs = Presentation()
    prs.slide_width = SW
    prs.slide_height = SH

    # 1 Cover
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_image_crop(slide, ASSETS / "program_3d_view.png", 6.2, 0, 7.133, 7.5)
    add_rect(slide, 0, 0, 6.65, 7.5, C["bg"], C["bg"], radius=False)
    add_rect(slide, 0.7, 1.0, 0.10, 4.75, C["cyan"], C["cyan"], radius=False)
    add_text(slide, "FDS BUILDER", 1.05, 0.95, 3.4, 0.35, 12, C["cyan"], True)
    add_text(slide, "设施火灾热辐射\n建模与损伤预测系统", 1.02, 1.48, 5.2, 1.65, 31, C["white"], True, valign=MSO_ANCHOR.TOP, line_spacing=0.9)
    add_text(slide, "从可计算等效模型到 FDS 高保真计算，再到秒级损伤预测", 1.05, 3.36, 4.85, 0.75, 16, C["muted"], False, valign=MSO_ANCHOR.TOP)
    add_rect(slide, 1.05, 4.48, 4.72, 0.72, C["panel"], C["line"])
    add_text(slide, "快速建模  ·  可视交互  ·  可计算  ·  可预测", 1.28, 4.63, 4.3, 0.35, 13, C["white"], True, PP_ALIGN.CENTER)
    add_text(slide, "系统介绍与工程应用方案", 1.05, 6.35, 3.8, 0.28, 11, C["muted"])
    add_text(slide, "2026.07", 5.0, 6.35, 0.78, 0.28, 11, C["muted"], True, PP_ALIGN.RIGHT)

    # 2 Value overview
    slide = new_slide(prs, 2, "SYSTEM OVERVIEW", "一套程序贯通建模—计算—预测—复核",
                      "同一份设施语义模型驱动 3D、FDS 与工程代理模型，减少重复录入和口径漂移")
    metric(slide, 0.7, 1.85, 2.8, "11 类", "当前界面设施模板", C["blue"], "4 类等效 + 7 类特异")
    metric(slide, 3.7, 1.85, 2.8, "83 个", "建筑单体定义", C["cyan"], "模板内可复用建筑对象")
    metric(slide, 6.7, 1.85, 2.8, "5,479", "代理模型合格工况", C["green"], "36 个训练设施身份")
    metric(slide, 9.7, 1.85, 2.93, "95.8%", "五折等级准确率", C["amber"], "综合已知设施工况口径")
    pipeline = [
        ("设施模板", "选择对象与规模", C["blue"]),
        ("可计算模型", "几何 / 分区 / 资产", C["cyan"]),
        ("FDS 输入", "网格 / 边界 / 输出", C["green"]),
        ("双计算", "代理预测 + FDS", C["amber"]),
        ("工程判读", "Dk / 等级 / 复核", C["purple"]),
    ]
    x = 0.7
    for i, (name, sub, accent) in enumerate(pipeline):
        add_rect(slide, x, 3.55, 2.25, 1.72, C["panel"], accent)
        add_rect(slide, x + 0.16, 3.76, 0.42, 0.42, accent, accent)
        set_text(slide.shapes[-1], str(i + 1), 12, C["dark"], True, PP_ALIGN.CENTER)
        add_text(slide, name, x + 0.68, 3.70, 1.35, 0.48, 15, C["white"], True)
        add_text(slide, sub, x + 0.20, 4.44, 1.85, 0.40, 11, C["muted"], False, PP_ALIGN.CENTER)
        if i < len(pipeline) - 1:
            add_text(slide, "→", x + 2.27, 4.05, 0.38, 0.55, 24, accent, True, PP_ALIGN.CENTER)
        x += 2.5
    add_rect(slide, 0.7, 5.68, 11.95, 0.92, C["bg2"], C["line"])
    add_text(slide, "核心价值", 0.95, 5.91, 1.1, 0.35, 13, C["cyan"], True)
    add_text(slide, "把“场景表达”转化为“可运行模型”，再把高成本计算沉淀为可复用的工程预测能力。",
             2.1, 5.84, 9.95, 0.45, 15, C["white"], True)

    # 3 Architecture
    slide = new_slide(prs, 3, "ARCHITECTURE", "系统总体架构", "五层解耦、单一模型源、多种计算输出")
    add_image_contain(slide, ASSETS / "system_architecture.png", 0.7, 1.75, 11.95, 5.25, card=True, pad=0.02)

    # 4 Main UI
    slide = new_slide(prs, 4, "VISUAL INTERFACE", "三栏一体化可视交互界面",
                      "左侧选设施与管理场景，中间进行 3D 审核，右侧配置工况并同步预览 FDS")
    add_image_contain(slide, ASSETS / "program_main_ui.png", 0.7, 1.74, 11.95, 4.95, card=True, pad=0.08)
    labels = [("① 快速建模", 0.95, C["blue"]), ("② 3D 场景", 5.35, C["cyan"]), ("③ 仿真与代码", 9.95, C["amber"])]
    for text, x, accent in labels:
        add_rect(slide, x, 6.72, 2.05, 0.34, C["panel2"], accent)
        add_text(slide, text, x + .08, 6.76, 1.88, .20, 10, accent, True, PP_ALIGN.CENTER)

    # 5 Quick modeling
    slide = new_slide(prs, 5, "RAPID MODELING", "六步完成设施级快速建模",
                      "规模旁只保留必要选择，实际尺寸在场景列表中统一核对；可燃物管理与生成设施并列为主操作")
    add_image_contain(slide, ASSETS / "quick_modeling_flow.png", 0.7, 1.73, 11.95, 5.25, card=True, pad=0.02)

    # 6 Equivalent model
    slide = new_slide(prs, 6, "EQUIVALENT MODEL", "规模驱动的可计算等效模型",
                      "小 / 中 / 大规模同步作用于几何、楼层、防火分区、开口、设备与可燃物，而不是简单缩放外形")
    add_image_contain(slide, ASSETS / "equivalent_model_logic.png", 0.7, 1.73, 11.95, 5.25, card=True, pad=0.02)

    # 7 Template library
    slide = new_slide(prs, 7, "MODEL LIBRARY", "等效模型与特异模型协同覆盖",
                      "等效模型用于尺度化研究与快速构型，特异模型保留真实工程对象的几何和布局差异")
    add_rect(slide, 0.7, 1.85, 5.85, 4.95, C["panel"], C["blue"])
    card_title(slide, "等效模型 · 4 类 / 12 栋建筑定义", 1.0, 2.05, 5.2, C["blue"], "A")
    rows = [
        ("航空航天设施", "5 栋", "发射控制、总装、部装、加工、发射场"),
        ("机场机库", "1 栋", "单体大空间机库"),
        ("机械制造设施", "3 栋", "总装、部装、机加工"),
        ("冶金设施", "3 栋", "电解、专用电厂、钢铁厂"),
    ]
    yy = 2.75
    for name, count, desc in rows:
        add_rect(slide, 1.0, yy, 5.15, 0.72, C["bg2"], C["line"])
        add_text(slide, name, 1.22, yy + .12, 1.65, .25, 12, C["white"], True)
        add_text(slide, count, 2.90, yy + .12, .55, .25, 11, C["cyan"], True, PP_ALIGN.CENTER)
        add_text(slide, desc, 3.55, yy + .08, 2.35, .37, 10.5, C["muted"], False, valign=MSO_ANCHOR.TOP)
        yy += .85
    add_rect(slide, 6.8, 1.85, 5.85, 4.95, C["panel"], C["amber"])
    card_title(slide, "特异模型 · 7 类 / 71 栋建筑定义", 7.1, 2.05, 5.2, C["amber"], "B")
    specialized = [
        "Alcoa Warrick Operations · 18 栋",
        "Warrick 专用电厂 · 18 栋",
        "Materion Newton · 11 栋",
        "Frymaster · 8 栋",
        "Gleason · 8 栋",
        "Harbison Fischer · 6 栋",
        "Materion Buffalo · 2 栋",
    ]
    yy = 2.74
    for i, text in enumerate(specialized):
        accent = C["amber"] if i < 2 else C["orange"]
        add_rect(slide, 7.1, yy, 0.30, 0.30, accent, accent)
        add_text(slide, str(i + 1), 7.1, yy + .015, .30, .20, 8.5, C["dark"], True, PP_ALIGN.CENTER)
        add_text(slide, text, 7.58, yy - .02, 4.45, .32, 11.5, C["white"], i < 2)
        yy += .49
    add_rect(slide, 7.1, 6.28, 5.15, .35, C["bg2"], C["line"])
    add_text(slide, "模板通过 JSON 序列化，便于校核、扩展和版本管理", 7.25, 6.34, 4.85, .18, 9.2, C["muted"], False, PP_ALIGN.CENTER)

    # 8 Visual interaction
    slide = new_slide(prs, 8, "3D INTERACTION", "3D 场景不是装饰，而是建模质量检查器",
                      "在计算前发现尺寸、位置、层高、构件朝向和热源方向问题")
    add_image_crop(slide, ASSETS / "program_3d_view.png", 0.7, 1.80, 7.6, 4.98, card=True)
    add_rect(slide, 8.55, 1.80, 4.10, 4.98, C["panel"], C["cyan"])
    card_title(slide, "可视校核要点", 8.9, 2.08, 3.4, C["cyan"], "✓")
    add_bullets(slide, [
        "建筑群位置与间距是否合理",
        "楼层、屋面、外墙与防火分区是否闭合",
        "门窗、装卸口和通风开口是否符合预期",
        "可燃物与专用设备是否位于正确分区",
        "热辐射方位角 / 俯仰角是否与工况一致",
        "场景列表同步显示名称、尺寸与位置",
    ], 8.95, 2.72, 3.25, 2.98, 12.5, C["white"], spacing=5)
    add_rect(slide, 8.92, 6.06, 3.40, 0.48, C["bg2"], C["line"])
    add_text(slide, "刷新模型 · 重置视角 · 单体选中高亮", 9.04, 6.15, 3.15, .20, 9.5, C["muted"], True, PP_ALIGN.CENTER)

    # 9 Engineering semantics
    slide = new_slide(prs, 9, "ENGINEERING SEMANTICS", "可燃物、敏感目标与专用构件进入同一工程语义",
                      "不仅生成厂房外壳，还表达影响受热响应和损失计算的内部对象")
    cards = [
        ("防火分区", "按楼层组织边界、隔墙、开口与材料；为对象布置提供约束域。", C["blue"]),
        ("可燃物", "油桶、电缆、托盘等以数量、尺寸、方向和分区位置进入场景。", C["orange"]),
        ("专用设备", "控制台、机加工线、装配工装等保持工程类别与朝向语义。", C["cyan"]),
        ("规则化布置", "总装空间火箭水平放置、发射场竖直放置；越界对象自动检查。", C["green"]),
    ]
    positions = [(0.7, 1.95), (6.75, 1.95), (0.7, 4.45), (6.75, 4.45)]
    for i, ((title, body, accent), (x, y)) in enumerate(zip(cards, positions)):
        add_rect(slide, x, y, 5.88, 2.03, C["panel"], accent)
        add_rect(slide, x + .28, y + .30, .58, .58, accent, accent)
        set_text(slide.shapes[-1], f"{i+1:02d}", 13, C["dark"], True, PP_ALIGN.CENTER)
        add_text(slide, title, x + 1.04, y + .28, 4.35, .45, 17, C["white"], True)
        add_text(slide, body, x + .30, y + 1.02, 5.20, .70, 13, C["muted"], False, valign=MSO_ANCHOR.TOP)

    # 10 Computable FDS
    slide = new_slide(prs, 10, "FDS GENERATION", "从对象模型自动生成可运行 FDS 输入",
                      "模型语义统一映射到网格、材料、实体、开口、边界条件、设备与切片")
    add_rect(slide, 0.7, 1.85, 6.15, 4.95, C["panel"], C["green"])
    card_title(slide, "自动生成链", 1.0, 2.08, 5.5, C["green"], "→")
    chain = [
        ("JSON / 模板参数", "可复现输入"),
        ("BuildingGroup", "结构化语义模型"),
        ("FDSGenerator", "几何与工况映射"),
        ("validate_fds", "输入完整性检查"),
        (".fds", "可运行计算文件"),
    ]
    yy = 2.72
    for i, (name, sub) in enumerate(chain):
        add_rect(slide, 1.05, yy, 5.40, .59, C["bg2"], C["line"])
        add_text(slide, f"{i+1}", 1.22, yy + .13, .28, .25, 10, C["green"], True, PP_ALIGN.CENTER)
        add_text(slide, name, 1.70, yy + .10, 2.15, .26, 12, C["white"], True)
        add_text(slide, sub, 3.95, yy + .10, 2.10, .26, 10, C["muted"], False, PP_ALIGN.RIGHT)
        yy += .72
    add_rect(slide, 7.10, 1.85, 5.55, 4.95, "0B1727", C["blue"])
    card_title(slide, "典型输出片段", 7.45, 2.08, 4.85, C["blue"], "F")
    code = (
        "&HEAD CHID='aerospace_q15000_a270_e30...' /\n"
        "&MESH ID='Mesh01', IJK=62,75,33, ... /\n"
        "&MATL ID='CONCRETE', ... /\n"
        "&OBST XB=..., SURF_ID='CONCRETE' /\n"
        "&VENT XB=..., SURF_ID='RADIATION' /\n"
        "&SLCF PBY=..., QUANTITY='TEMPERATURE' /\n"
        "&DEVC XYZ=..., QUANTITY='GAUGE HEAT FLUX' /"
    )
    add_rect(slide, 7.45, 2.73, 4.85, 2.65, C["dark"], C["line"])
    add_text(slide, code, 7.70, 2.95, 4.35, 2.15, 11, "D7E8FA", False, valign=MSO_ANCHOR.TOP, font_name=MONO, line_spacing=1.0)
    add_bullets(slide, [
        "默认 2×2 四网格划分，便于 MPI 并行",
        "热源侧局部加密带保持 1 m 网格",
        "文件名自动编码 q / a / e / d / t 工况",
    ], 7.52, 5.62, 4.65, 0.92, 10.5, C["muted"], spacing=3)

    # 11 Simulation & review
    slide = new_slide(prs, 11, "SIMULATION", "计算控制、结果组织与 Smokeview 复核",
                      "程序负责场景与输入的一致性，FDS / Smokeview 作为外部求解与结果查看能力接入")
    add_image_contain(slide, ASSETS / "program_ui_simulation_detail.png", 0.7, 1.83, 4.25, 5.02, card=True, pad=.06)
    add_rect(slide, 5.22, 1.83, 7.43, 5.02, C["panel"], C["amber"])
    card_title(slide, "右侧工作区形成完整计算闭环", 5.58, 2.08, 6.72, C["amber"], "C")
    phases = [
        ("工况配置", "方位角、俯仰角、目标热通量、辐射持续时间、总仿真时间和网格尺寸。", C["blue"]),
        ("代码同步", "参数变化触发 FDS 文本更新；滑块与预览采用去抖，避免高频重建。", C["cyan"]),
        ("计算执行", "导出 FDS；按工程环境调用 FDS，结果按设施与工况统一命名归档。", C["green"]),
        ("结果查看", "加载温度 / HRRPUV 等结果；通过 Smokeview 查看 .smv 与空间响应。", C["orange"]),
    ]
    yy = 2.75
    for i, (name, desc, accent) in enumerate(phases):
        add_rect(slide, 5.60, yy, .44, .44, accent, accent)
        set_text(slide.shapes[-1], str(i+1), 11, C["dark"], True, PP_ALIGN.CENTER)
        add_text(slide, name, 6.22, yy - .02, 1.18, .32, 12, accent, True)
        add_text(slide, desc, 7.35, yy - .03, 4.65, .58, 11.5, C["white"], False, valign=MSO_ANCHOR.TOP)
        yy += .94
    add_rect(slide, 5.60, 6.34, 6.60, .34, C["bg2"], C["line"])
    add_text(slide, "程序不替代 FDS 物理求解；它降低建模与重复操作成本，并固化计算口径。",
             5.78, 6.40, 6.22, .19, 9.5, C["muted"], True, PP_ALIGN.CENTER)

    # 12 Surrogate architecture
    slide = new_slide(prs, 12, "SURROGATE MODEL", "工程预测代理模型：Dk 连续值 + 四级损伤双输出",
                      "当前生产快照以已知设施的新工况为目标，权威已观测条件优先直接复用")
    metric(slide, 0.7, 1.78, 2.25, "5,479", "合格训练工况", C["green"])
    metric(slide, 3.10, 1.78, 2.25, "36", "设施训练身份", C["blue"])
    metric(slide, 5.50, 1.78, 2.25, "58 维", "模型输入", C["cyan"], "22 工程/类别 + 36 one-hot")
    metric(slide, 7.90, 1.78, 2.25, "75 + 75", "回归树 + 分类树", C["amber"])
    metric(slide, 10.30, 1.78, 2.35, "≈ 36 MiB", "部署模型", C["purple"], "含权威工况快速查表")
    add_image_contain(slide, FIGURES / "extra_trees_architecture.png", 0.7, 3.28, 7.65, 3.48, card=True, pad=.08)
    add_rect(slide, 8.60, 3.28, 4.05, 3.48, C["panel"], C["purple"])
    card_title(slide, "输出口径", 8.92, 3.56, 3.42, C["purple"], "Dk")
    grades = [
        ("[0, 0.04)", "基本完好", C["green"]),
        ("[0.04, 0.10)", "轻微破坏", C["cyan"]),
        ("[0.10, 0.40)", "中等破坏", C["amber"]),
        ("[0.40, 1.00]", "严重破坏", C["red"]),
    ]
    yy = 4.22
    for rng, name, accent in grades:
        add_rect(slide, 8.95, yy, 3.30, .48, C["bg2"], C["line"])
        add_text(slide, rng, 9.08, yy + .09, 1.20, .20, 9.5, accent, True)
        add_text(slide, name, 10.35, yy + .07, 1.62, .23, 11, C["white"], True, PP_ALIGN.RIGHT)
        yy += .58

    # 13 Features
    slide = new_slide(prs, 13, "FEATURE ENGINEERING", "三组工程特征把热作用、建筑与资产联系起来",
                      "方位角采用 sin / cos 保持 0° 与 360° 连续；入射侧特征随方向动态计算")
    add_rect(slide, 0.7, 1.84, 4.10, 4.98, C["panel"], C["cyan"])
    feature_groups = [
        ("热源特征", "热通量、持续时间、热剂量、方位角、俯仰角", C["orange"]),
        ("建筑特征", "平面面积、体量、高度、入射侧墙面与开口比例、设施类别", C["blue"]),
        ("可燃物与敏感目标", "目标密度、迎火侧目标占比与设施内资产分布", C["green"]),
    ]
    yy = 2.22
    for i, (name, desc, accent) in enumerate(feature_groups):
        add_rect(slide, 1.02, yy, 3.46, 1.16, C["bg2"], accent)
        add_rect(slide, 1.18, yy + .18, .48, .48, accent, accent)
        set_text(slide.shapes[-1], str(i+1), 12, C["dark"], True, PP_ALIGN.CENTER)
        add_text(slide, name, 1.82, yy + .13, 2.32, .32, 13, C["white"], True)
        add_text(slide, desc, 1.18, yy + .68, 2.95, .30, 9.5, C["muted"], False, valign=MSO_ANCHOR.TOP)
        yy += 1.38
    add_image_contain(slide, FIGURES / "feature_importance.png", 5.05, 1.84, 7.60, 4.98, card=True, pad=.08)

    # 14 Validation
    slide = new_slide(prs, 14, "VALIDATION", "综合验证结果达到工程快速筛查要求",
                      "等级准确率衡量四级判定，MAE / RMSE / R² 衡量连续 Dk；二者必须同时观察")
    metric(slide, 0.7, 1.78, 2.35, "95.82%", "五折等级准确率", C["green"])
    metric(slide, 3.22, 1.78, 2.35, "91.3%", "五折 Macro F1", C["cyan"])
    metric(slide, 5.74, 1.78, 2.35, "0.0133", "五折 MAE", C["blue"])
    metric(slide, 8.26, 1.78, 2.35, "0.0573", "五折 RMSE", C["amber"])
    metric(slide, 10.78, 1.78, 1.87, "0.9692", "五折 R²", C["purple"])
    add_image_contain(slide, FIGURES / "cv_predicted_vs_observed.png", 0.7, 3.22, 5.85, 3.48, card=True, pad=.08)
    add_image_contain(slide, FIGURES / "cv_confusion_matrix.png", 6.80, 3.22, 5.85, 3.48, card=True, pad=.08)
    add_text(slide, "固定独立测试：等级准确率 95.53%，MAE 0.0107。综合指标不等同于每个设施都达到同一精度。",
             0.85, 6.82, 11.55, .22, 9.2, C["muted"], True, PP_ALIGN.CENTER)

    # 15 Threshold maps
    slide = new_slide(prs, 15, "THRESHOLD ATLAS", "代理模型可批量形成热通量损伤阈值图谱",
                      "固定设施几何与资产条件，扫描方向、持续时间和热通量，识别首次跨越 Dk 阈值的位置")
    add_image_contain(slide, FIGURES / "threshold_grids" / "threshold_grid_Hangar.png", 0.7, 1.80, 8.35, 5.02, card=True, pad=.06)
    add_rect(slide, 9.30, 1.80, 3.35, 5.02, C["panel"], C["amber"])
    card_title(slide, "阈值能力", 9.62, 2.08, 2.72, C["amber"], "Q")
    stats = [
        ("36 / 36", "设施完成数值扫描"),
        ("100–20,000", "kW/m² 扫描范围"),
        ("81 点", "每条热通量扫描"),
        ("30 张", "按规则生成设施图"),
        ("324 行", "可审计阈值汇总"),
    ]
    yy = 2.78
    for value, label in stats:
        add_text(slide, value, 9.68, yy, 1.18, .34, 14, C["amber"], True)
        add_text(slide, label, 10.88, yy + .02, 1.35, .30, 9.5, C["white"], False, PP_ALIGN.RIGHT)
        yy += .58
    add_rect(slide, 9.62, 5.76, 2.72, .74, C["bg2"], C["line"])
    add_text(slide, "灰色斜线表示达到扫描上限仍未跨越，属于右删失，不等于阈值恰好为上限。",
             9.78, 5.86, 2.40, .52, 8.7, C["muted"], False, valign=MSO_ANCHOR.TOP)

    # 16 UI prediction
    slide = new_slide(prs, 16, "INTEGRATED PREDICTION", "代理模型已集成到程序交互链路",
                      "选择设施与规模、设置热源参数后，直接输出连续 Dk、损伤等级、统一验证准确率与模型预测用时")
    add_image_contain(slide, ASSETS / "program_prediction_dialog.png", 0.7, 2.00, 7.15, 3.90, card=True, pad=.14)
    add_rect(slide, 8.10, 1.85, 4.55, 4.95, C["panel"], C["green"])
    card_title(slide, "一次预测所完成的工作", 8.45, 2.12, 3.85, C["green"], "P")
    add_bullets(slide, [
        "将界面设施映射到训练设施身份与对应尺度",
        "生成与命名规则一致的临时 FDS 工况",
        "权威已观测条件优先直接返回真实 Dk",
        "未观测工况执行 ExtraTrees 快速推理",
        "同时显示 Dk、四级损伤、综合验证准确率",
        "未知 / 自定义设施明确拒绝，不静默外推",
    ], 8.48, 2.78, 3.60, 2.80, 12.5, C["white"], spacing=7)
    add_rect(slide, 8.46, 5.98, 3.80, .52, C["bg2"], C["line"])
    add_text(slide, "示例：aerospace_medium · Dk 0.1457 · 中等破坏", 8.60, 6.08, 3.50, .22, 9.2, C["amber"], True, PP_ALIGN.CENTER)

    # 17 Dual-track
    slide = new_slide(prs, 17, "ENGINEERING DECISION", "快速筛查与 FDS 复核构成双轨决策",
                      "代理模型提升覆盖效率，高保真计算用于等级边界、关键决策与超出适用域的工况")
    add_image_contain(slide, ASSETS / "surrogate_fds_dual_track.png", 0.7, 1.73, 11.95, 5.25, card=True, pad=.02)

    # 18 Summary
    slide = new_slide(prs, 18, "SUMMARY", "仿真程序总结：把建模能力沉淀为工程能力",
                      "当前系统已经形成“模型库—可视建模—FDS—代理预测—复核归档”的完整主链")
    themes = [
        ("更快", "模板 + 规模参数化减少重复建模；设施级场景一键生成。", C["blue"]),
        ("更准", "统一对象模型驱动 3D 与 FDS，降低界面、文件和计算口径不一致。", C["cyan"]),
        ("更可算", "自动生成网格、边界、材料、开口、设备和切片，直接进入 FDS。", C["green"]),
        ("更可用", "代理模型输出 Dk 与等级；关键工况可顺畅回到 FDS 复核。", C["amber"]),
    ]
    x = .7
    for i, (title, body, accent) in enumerate(themes):
        add_rect(slide, x, 1.95, 2.82, 2.55, C["panel"], accent)
        add_rect(slide, x + .23, 2.22, .55, .55, accent, accent)
        set_text(slide.shapes[-1], str(i + 1), 13, C["dark"], True, PP_ALIGN.CENTER)
        add_text(slide, title, x + .92, 2.22, 1.45, .45, 18, accent, True)
        add_text(slide, body, x + .27, 3.03, 2.27, .98, 12, C["white"], False, valign=MSO_ANCHOR.TOP)
        x += 3.06
    add_rect(slide, .7, 4.84, 11.95, 1.57, C["bg2"], C["purple"])
    add_text(slide, "下一步建议", .98, 5.08, 1.25, .38, 14, C["purple"], True)
    add_text(slide, "① 模板版本与质量看板   ② 代理模型置信度门控\n③ FDS 任务队列与进度监控   ④ 复核结果持续回流再训练",
             2.20, 4.98, 9.80, .82, 12.5, C["white"], True, valign=MSO_ANCHOR.TOP, line_spacing=0.95)
    add_text(slide, "目标：形成可扩展、可审计、可复现的设施热辐射损伤计算与快速预测平台。",
             1.0, 5.87, 11.30, .30, 12, C["muted"], False, PP_ALIGN.CENTER)

    # Core properties for easy identification.
    prs.core_properties.title = "设施火灾热辐射建模与损伤预测系统介绍"
    prs.core_properties.subject = "系统架构、快速建模、可视化交互、可计算等效模型、工程预测代理模型集成"
    prs.core_properties.author = "fdsBuilder 项目组"
    prs.core_properties.keywords = "FDS, 快速建模, 等效模型, 工程预测, ExtraTrees, Dk"
    prs.core_properties.comments = "数据口径采用 2026-07-15 生产快照；演示文稿生成于 2026-07-16。"

    path = OUT / "设施火灾热辐射建模与损伤预测系统介绍_20260909.pptx"
    prs.save(path)
    return path


if __name__ == "__main__":
    out = build_deck()
    print(out)
