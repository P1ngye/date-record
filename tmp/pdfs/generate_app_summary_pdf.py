from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "pdf"
TMP_DIR = ROOT / "tmp" / "pdfs"
PDF_PATH = OUTPUT_DIR / "date_record_app_summary.pdf"
PNG_PATH = TMP_DIR / "date_record_app_summary.png"

PAGE_W = 1654
PAGE_H = 2339
MARGIN = 90
CARD_X0 = 70
CARD_Y0 = 60
CARD_X1 = PAGE_W - 70
CARD_Y1 = PAGE_H - 60


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts") / name,
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


FONT_TITLE = load_font("arialbd.ttf", 54)
FONT_SECTION = load_font("arialbd.ttf", 26)
FONT_BODY = load_font("arial.ttf", 22)
FONT_BODY_BOLD = load_font("arialbd.ttf", 22)
FONT_SMALL = load_font("arial.ttf", 18)
FONT_FOOT = load_font("arial.ttf", 16)


def section_header(draw: ImageDraw.ImageDraw, y: int, text: str) -> int:
    draw.rounded_rectangle((MARGIN, y, PAGE_W - MARGIN, y + 42), radius=18, fill="#EAF1FF")
    draw.text((MARGIN + 16, y + 7), text, font=FONT_SECTION, fill="#1B2B46")
    return y + 58


def wrapped_text(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 8,
) -> int:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y = bbox[3] + line_gap
    return y


def bullet_list(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    items: list[str],
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    bullet_fill: str = "#2F6DF6",
) -> int:
    bullet_x = x
    text_x = x + 26
    for item in items:
        draw.ellipse((bullet_x, y + 8, bullet_x + 10, y + 18), fill=bullet_fill)
        y = wrapped_text(draw, text_x, y, item, font, fill, max_width - 26, line_gap=6) + 6
    return y


def draw_flow_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    lines: list[str],
    fill: str,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=22, fill=fill, outline="#D8E4FA", width=2)
    draw.text((x0 + 18, y0 + 16), title, font=FONT_BODY_BOLD, fill="#18314D")
    cur_y = y0 + 52
    for line in lines:
        cur_y = wrapped_text(draw, x0 + 18, cur_y, line, FONT_SMALL, "#304A68", x1 - x0 - 36, line_gap=4)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (PAGE_W, PAGE_H), "#EEF4FF")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((CARD_X0, CARD_Y0, CARD_X1, CARD_Y1), radius=34, fill="#FFFFFF", outline="#DDE7F7", width=3)
    draw.rounded_rectangle((CARD_X0 + 24, CARD_Y0 + 24, CARD_X1 - 24, CARD_Y0 + 190), radius=30, fill="#F7FAFF")
    draw.text((MARGIN, 110), "Date Record App Summary", font=FONT_TITLE, fill="#10233D")
    draw.text(
        (MARGIN, 170),
        "Repo-based overview of the NT profile review toolkit",
        font=FONT_BODY,
        fill="#51647E",
    )

    y = 250
    y = section_header(draw, y, "What It Is")
    y = wrapped_text(
        draw,
        MARGIN,
        y,
        "A local, browser-based toolkit for recording, reviewing, and QA-checking Negative Triangularity (NT) experimental profile data from papers. "
        "The repo centers on Excel metadata, per-profile CSV point files, and two HTML tools for review and overlay validation.",
        FONT_BODY,
        "#21364F",
        PAGE_W - 2 * MARGIN,
    )

    y += 8
    y = section_header(draw, y, "Who It's For")
    y = wrapped_text(
        draw,
        MARGIN,
        y,
        "Primary user: a researcher or data curator maintaining NT experimental temperature/density profiles and logging QA results during manual review.",
        FONT_BODY,
        "#21364F",
        PAGE_W - 2 * MARGIN,
    )

    y += 8
    y = section_header(draw, y, "What It Does")
    feature_items = [
        "Imports a main workbook and expects sheets `01_PAPERS`, `02_CASES`, `03_PROFILES`, and `04_QA_LOG`.",
        "Browses data in a `paper -> case -> profile` hierarchy with search and variable/QA filters.",
        "Shows record summaries plus ID-rule and coordinate explanations to support manual review.",
        "Captures QA drafts and exports a standalone QA check-table Excel file.",
        "Launches `overlay_studio_bundle.html` directly from the main review workbench.",
        "Overlays one or more CSV curves on a figure image using 5-point axis calibration for digitize checks.",
        "Exports overlay results as PNG and stores/restores workspace state with browser local storage.",
    ]
    y = bullet_list(draw, MARGIN, y, feature_items, FONT_BODY, "#21364F", PAGE_W - 2 * MARGIN)

    y += 4
    y = section_header(draw, y, "How It Works")
    flow_y0 = y
    flow_y1 = flow_y0 + 245
    col_gap = 18
    col_w = (PAGE_W - 2 * MARGIN - 2 * col_gap) // 3
    box1 = (MARGIN, flow_y0, MARGIN + col_w, flow_y1)
    box2 = (MARGIN + col_w + col_gap, flow_y0, MARGIN + 2 * col_w + col_gap, flow_y1)
    box3 = (MARGIN + 2 * (col_w + col_gap), flow_y0, PAGE_W - MARGIN, flow_y1)

    draw_flow_box(
        draw,
        box1,
        "Inputs",
        [
            "Excel main table plus per-profile CSV files under `data/<paper_id>/...`.",
            "README requires profile CSVs with at least `x,y` columns.",
        ],
        "#F8FBFF",
    )
    draw_flow_box(
        draw,
        box2,
        "Review Layer",
        [
            "`tools_for_check/profile_review_workbench.html` loads SheetJS from a CDN, parses workbook sheets, stores workspace state in `localStorage`, and opens the overlay tool.",
        ],
        "#F6FAF8",
    )
    draw_flow_box(
        draw,
        box3,
        "Validation + Outputs",
        [
            "`overlay_studio_bundle.html` is canvas-based, loads image + CSV layers, builds axis mapping from 5 picked points, and saves sessions to JSON/local storage.",
            "Outputs found in repo evidence: QA Excel export and overlay PNG export. Backend/API service: Not found in repo.",
        ],
        "#FFF9F2",
    )

    arrow_y = flow_y0 + 102
    for start_x in (box1[2] + 8, box2[2] + 8):
        draw.line((start_x, arrow_y, start_x + 34, arrow_y), fill="#7D94BA", width=4)
        draw.polygon(
            [(start_x + 34, arrow_y), (start_x + 22, arrow_y - 8), (start_x + 22, arrow_y + 8)],
            fill="#7D94BA",
        )

    y = flow_y1 + 18
    y = section_header(draw, y, "How To Run")
    run_items = [
        "Keep `profile_review_workbench.html` and `overlay_studio_bundle.html` in the same folder.",
        "Open `tools_for_check/profile_review_workbench.html` in a browser. Internet access may be needed because SheetJS is loaded from a CDN.",
        "Import the main `.xlsx`, review a target profile, use `Open Overlay` for figure-vs-CSV validation, then export the QA Excel file.",
        "Install/build steps or a packaged app launcher: Not found in repo.",
    ]
    y = bullet_list(draw, MARGIN, y, run_items, FONT_BODY, "#21364F", PAGE_W - 2 * MARGIN)

    footer_text = "Source basis: README_DataRecording.md, tools_for_check/README_nt_review_tools.md, and the HTML files in tools_for_check/."
    wrapped_text(draw, MARGIN, PAGE_H - 112, footer_text, FONT_FOOT, "#6A7C94", PAGE_W - 2 * MARGIN, line_gap=4)

    img.save(PNG_PATH)
    rgb = img.convert("RGB")
    rgb.save(PDF_PATH, "PDF", resolution=150.0)
    print(PDF_PATH)
    print(PNG_PATH)


if __name__ == "__main__":
    main()
