#!/usr/bin/env python3
"""
Generate preview PNG images for all Lochraster boards.
Exports SVG via kicad-cli, injects a JLCPCB-violet board background,
and converts to PNG via cairosvg.
"""
import os, re, subprocess, sys, glob

KICAD_CLI = r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"
LAYERS = "F.Cu,F.SilkS,Edge.Cuts"
JLCPCB_VIOLET = "#2d1b4e"   # dark purple / JLCPCB violet
PNG_WIDTH = 600              # pixels wide

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "Projekt", "images")
TEMP = os.environ.get("TEMP", "/tmp")


def export_svg(pcb_path, svg_path):
    """Export PCB to single-file SVG via kicad-cli."""
    subprocess.run([
        KICAD_CLI, "pcb", "export", "svg",
        "--layers", LAYERS,
        "--mode-single",
        "--exclude-drawing-sheet",
        "--page-size-mode", "2",
        "--drill-shape-opt", "2",
        "-o", svg_path,
        pcb_path
    ], check=True, capture_output=True)


def inject_board_bg(svg_path, board_w_mm, board_h_mm, corner_r=4.0):
    """Insert a violet rounded-rect board background as the first visible element."""
    svg = open(svg_path, encoding="utf-8").read()

    # Find the viewBox to get coordinate offsets
    vb = re.search(r'viewBox="([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"', svg)
    if not vb:
        return
    vb_x, vb_y, vb_w, vb_h = float(vb.group(1)), float(vb.group(2)), float(vb.group(3)), float(vb.group(4))

    # Board rectangle centred in viewbox (small margin from edge cuts)
    margin = (vb_w - board_w_mm) / 2
    bx = vb_x + margin
    by = vb_y + (vb_h - board_h_mm) / 2

    # Build the background rect
    bg_rect = (
        f'<rect x="{bx:.4f}" y="{by:.4f}" '
        f'width="{board_w_mm:.4f}" height="{board_h_mm:.4f}" '
        f'rx="{corner_r}" ry="{corner_r}" '
        f'fill="{JLCPCB_VIOLET}" />\n'
    )

    # Insert right after the opening <g ...></g> (the default empty group)
    # Find first </g> and insert after it
    insertion = svg.find("</g>")
    if insertion < 0:
        return
    insertion += len("</g>") + 1
    svg = svg[:insertion] + bg_rect + svg[insertion:]

    open(svg_path, "w", encoding="utf-8").write(svg)


def svg_to_png(svg_path, png_path, width=PNG_WIDTH):
    """Convert SVG to PNG using cairosvg."""
    import cairosvg
    cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=width)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pcb_files = sorted(glob.glob(os.path.join(SCRIPT_DIR, "proto_*.kicad_pcb")))

    if not pcb_files:
        print("No proto_*.kicad_pcb files found.")
        return 1

    for pcb_path in pcb_files:
        fname = os.path.basename(pcb_path)
        m = re.match(r'proto_(\d+)x(\d+)_(\w+)\.kicad_pcb$', fname)
        if not m:
            continue
        bw, bh = int(m.group(1)), int(m.group(2))
        name = fname.replace(".kicad_pcb", "")

        svg_path = os.path.join(TEMP, f"{name}.svg")
        png_path = os.path.join(OUT_DIR, f"{name}.png")

        print(f"  {fname} -> {name}.png ...", end=" ", flush=True)

        # Export SVG
        export_svg(pcb_path, svg_path)

        # Inject violet board background
        inject_board_bg(svg_path, bw, bh)

        # Convert to PNG
        svg_to_png(svg_path, png_path)

        print("OK")

    # Also generate overview grid
    print("\n  Generating overview grid ...", end=" ", flush=True)
    try:
        from PIL import Image
        sizes = [(50, 70), (70, 100), (100, 160)]
        types = ["unconnected", "stripboard", "group_3", "breadboard"]
        thumb_w = 600
        cols = len(types)
        rows = len(sizes)

        # Load all images and compute layout
        imgs = {}
        max_h_per_row = [0] * rows
        for ri, (sw, sh) in enumerate(sizes):
            for ci, tp in enumerate(types):
                p = os.path.join(OUT_DIR, f"proto_{sw}x{sh}_{tp}.png")
                if os.path.exists(p):
                    img = Image.open(p)
                    imgs[(ri, ci)] = img
                    if img.height > max_h_per_row[ri]:
                        max_h_per_row[ri] = img.height

        total_w = thumb_w * cols
        total_h = sum(max_h_per_row)
        overview = Image.new("RGB", (total_w, total_h), (45, 27, 78))  # violet bg

        y_off = 0
        for ri in range(rows):
            for ci in range(cols):
                img = imgs.get((ri, ci))
                if img:
                    # Centre vertically in row
                    x = ci * thumb_w + (thumb_w - img.width) // 2
                    y = y_off + (max_h_per_row[ri] - img.height) // 2
                    overview.paste(img, (x, y))
            y_off += max_h_per_row[ri]

        overview.save(os.path.join(OUT_DIR, "overview_all_boards.png"))
        print("OK")
    except Exception as e:
        print(f"SKIP ({e})")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
