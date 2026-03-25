import os
import math
import uuid
from PIL import Image

def image_to_kicad(image_path, pos_x, pos_y, max_width, max_height, layer="F.SilkS", threshold=128, mirror_x=0):
    """mirror_x: if >0, mirror all X coordinates around this board width value."""
    if not os.path.exists(image_path):
        return []
    try:
        img = Image.open(image_path).convert("RGBA")
    except:
        return []
    w, h = img.size
    # Cap resolution so line width (=scale) stays >= MIN_LINE_W mm
    MIN_LINE_W = 0.02
    scale = min(max_width / w, max_height / h)
    if scale < MIN_LINE_W:
        factor = MIN_LINE_W / scale
        new_w, new_h = max(1, int(w / factor)), max(1, int(h / factor))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        w, h = img.size
        scale = min(max_width / w, max_height / h)
    res = []
    pixels = img.load()

    # Determine the bounding box of the actual drawn pixels to perfectly center and scale them visually
    drawn_x = []
    drawn_y = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            brightness = (r + g + b) / 3
            if a > threshold and brightness < 180:
                drawn_x.append(x)
                drawn_y.append(y)

    if not drawn_x:
        return []

    min_x, max_x = min(drawn_x), max(drawn_x)
    min_y, max_y = min(drawn_y), max(drawn_y)
    actual_w = max_x - min_x + 1
    actual_h = max_y - min_y + 1

    # Use the tightly cropped dimensions for scaling so the visual size maximizes the available space
    scale = min(max_width / actual_w, max_height / actual_h)

    # Offset vertically and horizontally relative to the target max bounding box
    offset_x = (max_width - actual_w * scale) / 2
    offset_y = (max_height - actual_h * scale) / 2

    def mx(xv):
        return (mirror_x - xv) if mirror_x > 0 else xv
    for y in range(min_y, max_y + 1):
        start_x = -1
        for x in range(w):
            r, g, b, a = pixels[x, y]
            brightness = (r + g + b) / 3
            is_drawn = (a > threshold and brightness < 180)
            if is_drawn:
                if start_x == -1:
                    start_x = x
            else:
                if start_x != -1:
                    x1 = pos_x + offset_x + (start_x - min_x) * scale
                    y1 = pos_y + offset_y + (y - min_y) * scale
                    x2 = pos_x + offset_x + (x - 1 - min_x) * scale + scale * 0.95
                    lx1, lx2 = mx(x1), mx(x2)
                    if lx1 > lx2: lx1, lx2 = lx2, lx1
                    res.append(f"  (gr_line (start {lx1:.4f} {y1:.4f}) (end {lx2:.4f} {y1:.4f}) (layer {layer}) (width {scale:.4f}))")
                    start_x = -1
        if start_x != -1:
            x1 = pos_x + offset_x + (start_x - min_x) * scale
            y1 = pos_y + offset_y + (y - min_y) * scale
            x2 = pos_x + offset_x + (w - 1 - min_x) * scale + scale * 0.95
            lx1, lx2 = mx(x1), mx(x2)
            if lx1 > lx2: lx1, lx2 = lx2, lx1
            res.append(f"  (gr_line (start {lx1:.4f} {y1:.4f}) (end {lx2:.4f} {y1:.4f}) (layer {layer}) (width {scale:.4f}))")
    return res


def make_power_terminal(abs_x, abs_y_top, abs_y_oval, label, is_left, net_id, pitch=2.54):
    """
    Power terminal:
    - 3-wide x 2-tall grid DIRECTLY ABOVE the oval pad, centered on abs_x
      Cols at -1, 0, +1 pitch offsets horizontally
      Rows 0 and 1 vertically (row 0 = top, row 1 = bottom)
    - 1 large oval pad below the grid
    - Ring of 8 microvias around oval
    - Traces connecting everything on both layers
    """
    dp = pitch
    y_oval_rel = abs_y_oval - abs_y_top

    inward_sign = 1 if is_left else -1

    # Grid: 3 cols wide (centered) x 2 rows tall, directly above the oval
    # Module origin is at (abs_x, abs_y_top)
    grid_holes = []  # (rel_x, rel_y)
    for col in [-1, 0, 1]:
        for row in range(2):
            rx = col * dp
            ry = row * dp
            grid_holes.append((rx, ry))

    # Module pads with net assignment
    pads_str = ""
    for gx, gy in grid_holes:
        pads_str += f"\n    (pad 1 thru_hole circle (at {gx:.4f} {gy:.4f}) (size 1.8 1.8) (drill 1.0) (layers *.Cu *.Mask) (net {net_id} \"{label}\"))"

    # Oval pad (wider: 10x12) with net assignment
    pads_str += f"\n    (pad 1 thru_hole oval (at 0 {y_oval_rel:.4f}) (size 10 12) (drill oval 2 5) (layers *.Cu *.Mask) (net {net_id} \"{label}\"))"

    # Label: right next to the oval, on the inward side, at same height as oval center
    lbl_x = inward_sign * 6.5

    # KiCad modules can only have one "value". We put it hidden on F.Fab.
    lbl = f"\n    (fp_text value \"{label}\" (at 0 0) (layer F.Fab) hide (effects (font (size 1 1) (thickness 0.15))))"

    # F.SilkS and B.SilkS labels. We omit horizontal justification so they are centered
    # vertically on the anchor point, ensuring VCC and GND are at the exact same height.
    lbl += f"\n    (fp_text user \"{label}\" (at {lbl_x:.1f} {y_oval_rel:.4f} 90) (layer F.SilkS) (effects (font (size 1.3 1.3) (thickness 0.2))))"
    lbl += f"\n    (fp_text user \"{label}\" (at {lbl_x:.1f} {y_oval_rel:.4f} 90) (layer B.SilkS) (effects (font (size 1.3 1.3) (thickness 0.2)) (justify mirror)))"

    mod = f"""  (module Power_{label} (layer F.Cu) (at {abs_x:.4f} {abs_y_top:.4f})
    (fp_text reference "REF" (at 0 -2) (layer F.SilkS) hide (effects (font (size 1 1) (thickness 0.15)))){lbl}{pads_str}
  )"""

    traces = []

    # Horizontal traces connecting 3 holes in each row
    for row in range(2):
        ry = row * dp
        row_holes = sorted([(gx, gy) for gx, gy in grid_holes if abs(gy - ry) < 0.1],
                           key=lambda h: h[0])
        for i in range(len(row_holes) - 1):
            x1 = abs_x + row_holes[i][0]
            x2 = abs_x + row_holes[i + 1][0]
            yy = abs_y_top + ry
            traces.append(f"  (segment (start {x1:.4f} {yy:.4f}) (end {x2:.4f} {yy:.4f}) (width 1.5) (layer F.Cu) (net {net_id}))")
            traces.append(f"  (segment (start {x1:.4f} {yy:.4f}) (end {x2:.4f} {yy:.4f}) (width 1.5) (layer B.Cu) (net {net_id}))")

    # Vertical traces connecting the 2 rows at each of the 3 columns
    for col in [-1, 0, 1]:
        rx = col * dp
        col_holes = sorted([gy for gx, gy in grid_holes if abs(gx - rx) < 0.1])
        if len(col_holes) >= 2:
            x = abs_x + rx
            traces.append(f"  (segment (start {x:.4f} {abs_y_top + col_holes[0]:.4f}) (end {x:.4f} {abs_y_top + col_holes[-1]:.4f}) (width 1.5) (layer F.Cu) (net {net_id}))")
            traces.append(f"  (segment (start {x:.4f} {abs_y_top + col_holes[0]:.4f}) (end {x:.4f} {abs_y_top + col_holes[-1]:.4f}) (width 1.5) (layer B.Cu) (net {net_id}))")

    # Center column (col 0) connects straight down to oval
    bottom_grid_y = abs_y_top + dp  # row 1 (bottom row)
    traces.append(f"  (segment (start {abs_x:.4f} {bottom_grid_y:.4f}) (end {abs_x:.4f} {abs_y_oval:.4f}) (width 2.0) (layer F.Cu) (net {net_id}))")
    traces.append(f"  (segment (start {abs_x:.4f} {bottom_grid_y:.4f}) (end {abs_x:.4f} {abs_y_oval:.4f}) (width 2.0) (layer B.Cu) (net {net_id}))")

    # Ring of 8 microvias around oval hole edge
    vias = []
    oval_cy = abs_y_oval
    via_radius = 3.8
    n_vias = 8
    for i in range(n_vias):
        angle = 2 * math.pi * i / n_vias
        vx = abs_x + via_radius * math.cos(angle)
        vy = oval_cy + via_radius * math.sin(angle)
        vias.append(f"  (via (at {vx:.4f} {vy:.4f}) (size 0.8) (drill 0.4) (layers F.Cu B.Cu) (net {net_id}))")

    # Star traces from oval center to each ring via
    for i in range(n_vias):
        angle = 2 * math.pi * i / n_vias
        vx = abs_x + via_radius * math.cos(angle)
        vy = oval_cy + via_radius * math.sin(angle)
        traces.append(f"  (segment (start {abs_x:.4f} {oval_cy:.4f}) (end {vx:.4f} {vy:.4f}) (width 0.5) (layer F.Cu) (net {net_id}))")
        traces.append(f"  (segment (start {abs_x:.4f} {oval_cy:.4f}) (end {vx:.4f} {vy:.4f}) (width 0.5) (layer B.Cu) (net {net_id}))")

    # Vias at each grid hole (offset slightly to sides)
    for gx, gy in grid_holes:
        hx = abs_x + gx
        hy = abs_y_top + gy
        vias.append(f"  (via (at {hx + 1.0:.4f} {hy:.4f}) (size 0.6) (drill 0.3) (layers F.Cu B.Cu) (net {net_id}))")
        vias.append(f"  (via (at {hx - 1.0:.4f} {hy:.4f}) (size 0.6) (drill 0.3) (layers F.Cu B.Cu) (net {net_id}))")
        traces.append(f"  (segment (start {hx:.4f} {hy:.4f}) (end {hx + 1.0:.4f} {hy:.4f}) (width 0.5) (layer F.Cu) (net {net_id}))")
        traces.append(f"  (segment (start {hx:.4f} {hy:.4f}) (end {hx - 1.0:.4f} {hy:.4f}) (width 0.5) (layer F.Cu) (net {net_id}))")
        traces.append(f"  (segment (start {hx:.4f} {hy:.4f}) (end {hx + 1.0:.4f} {hy:.4f}) (width 0.5) (layer B.Cu) (net {net_id}))")
        traces.append(f"  (segment (start {hx:.4f} {hy:.4f}) (end {hx - 1.0:.4f} {hy:.4f}) (width 0.5) (layer B.Cu) (net {net_id}))")

    return mod, traces, vias


def generate_pcb(filename, width_mm, height_mm, board_type="unconnected", pitch_mm=2.54):
    margin = 5.0
    cr = 4.0
    cols = int((width_mm - 2 * margin) / pitch_mm) + 1
    rows = int((height_mm - 2 * margin) / pitch_mm) + 1
    # Center the grid within the board (don't just pin to margin)
    grid_w = (cols - 1) * pitch_mm
    grid_h = (rows - 1) * pitch_mm
    offset_x = (width_mm - grid_w) / 2
    offset_y = (height_mm - grid_h) / 2

    # Board types with outer GND/VCC power-rail columns
    has_outer_rails = board_type in ("unconnected", "group_3")

    # group_3: precompute isolated hole indices so remainder holes land in center.
    # N_inner = inner hole count (col 1 .. col cols-2). Split full groups evenly
    # left/right; any remainder holes go in center as isolated.
    N_inner = cols - 2
    g3_r_rem   = N_inner % 3
    g3_left_cnt = (N_inner // 3) // 2 * 3   # nearest ≤ mid that is mult of 3
    g3_isolated = set(range(g3_left_cnt, g3_left_cnt + g3_r_rem))

    c_gnd = 1
    c_vcc = cols - 2

    cutout_rows = 6
    cutout_r_start = rows - cutout_rows

    y_oval_term = height_mm - 8.0
    # Place the 2x3 grid just above the oval pad top edge (oval is 12mm tall,
    # centered at y_oval_term, so top edge = y_oval_term - 6).
    # Bottom grid row at y_top_pads + pitch sits 0.5mm above the oval pad.
    oval_pad_top = y_oval_term - 6.0
    y_top_pads = oval_pad_top - pitch_mm - 0.5

    # Exclusion: ±3 cols around power columns (2x4 grid extends inward)
    pwr_xs_set = set()
    for r in range(cutout_r_start, rows):
        for dc in range(-3, 4):  # -3 to +3
            gc = c_gnd + dc
            vc = c_vcc + dc
            if 0 <= gc < cols:
                pwr_xs_set.add((r, gc))
            if 0 <= vc < cols:
                pwr_xs_set.add((r, vc))

    # Define net IDs for power rails
    gnd_net = 1
    vcc_net = 2

    grid = {}
    pads = []
    for r in range(rows):
        for c in range(cols):
            if r >= cutout_r_start and c_gnd < c < c_vcc:
                continue
            if (r, c) in pwr_xs_set:
                continue
            x = offset_x + c * pitch_mm
            y = offset_y + r * pitch_mm
            grid[(r, c)] = (x, y)

            # Determine net for outer rail columns
            net_str = ""
            if has_outer_rails and (c == 0 or c == cols - 1) and r < cutout_r_start:
                group = r // 2
                is_vcc = (group % 2 == 1)
                net_id = vcc_net if is_vcc else gnd_net
                net_name = "VCC" if is_vcc else "GND"
                net_str = f' (net {net_id} "{net_name}")'

            pads.append(f"""  (module Lochraster_Pad (layer F.Cu) (at {x:.4f} {y:.4f})
    (fp_text reference "P" (at 0 0) (layer F.SilkS) hide (effects (font (size 1 1) (thickness 0.15))))
    (fp_text value "P" (at 0 0) (layer F.Fab) hide (effects (font (size 1 1) (thickness 0.15))))
    (pad 1 thru_hole circle (at 0 0) (size 1.8 1.8) (drill 1.0) (layers *.Cu *.Mask){net_str})
  )""")

    segments = []
    def add_seg(r1, c1, r2, c2):
        if (r1, c1) in grid and (r2, c2) in grid:
            p1 = grid[(r1, c1)]
            p2 = grid[(r2, c2)]
            segments.append(f"  (segment (start {p1[0]:.4f} {p1[1]:.4f}) (end {p2[0]:.4f} {p2[1]:.4f}) (width 1.2) (layer B.Cu) (net 0))")

    for r in range(rows):
        for c in range(cols):
            if board_type == "stripboard":
                add_seg(r, c, r, c + 1)
            elif board_type == "group_3":
                # All inner holes in contiguous groups of 3.
                # Remainder holes (if N_inner%3 != 0) sit isolated at center.
                if 1 <= c < cols - 2:
                    inner_c = c - 1
                    if inner_c in g3_isolated or (inner_c + 1) in g3_isolated:
                        pass  # adjacent to isolated hole — no connection
                    elif inner_c < g3_left_cnt:
                        if inner_c % 3 != 2:
                            add_seg(r, c, r, c + 1)
                    else:
                        right_i = inner_c - g3_left_cnt - g3_r_rem
                        if right_i % 3 != 2:
                            add_seg(r, c, r, c + 1)
            elif board_type == "breadboard":
                if r in [0, 1, rows - 2, rows - 1]:
                    if c != cols // 2:
                        add_seg(r, c, r, c + 1)
                else:
                    if 3 <= r <= rows - 4 and (r - 3) % 6 != 5:
                        add_seg(r, c, r + 1, c)

    # Outer rail columns: alternating 2-pad groups, top=GND, alternating GND/VCC.
    # Connect within each 2-hole group (both F.Cu + B.Cu for solid thru-hole joints).
    # Then route each net to its terminal via two-layer buses:
    #   F.Cu bus at x_bus_l/r → GND (even groups) → GND terminal
    #   B.Cu bus at x_bus_l/r → VCC (odd  groups) → VCC terminal
    #   Both buses cross-connect left↔right above the first hole row.
    # For boards with power rails, we need net definitions and zones
    zones_str = ""

    if has_outer_rails:
        x_left  = offset_x
        x_right = offset_x + (cols - 1) * pitch_mm
        x_gnd_t = offset_x + c_gnd * pitch_mm        # GND terminal centre x
        x_vcc_t = offset_x + c_vcc * pitch_mm        # VCC terminal centre x
        y_bus_bot = y_top_pads                       # bottom of planes = terminal pad row

        # Zone boundaries - 4mm safety margin on ALL sides
        zone_margin = 3.5   # 3.5mm from PCB edge (0.5mm wider outward than before)
        zone_clearance = 0.5  # clearance from holes
        corner_radius = 4.0  # rounded corners for wide zones (top/bottom bars)

        # Left strip zone boundaries
        x_left_zone_min = zone_margin
        x_left_zone_max = offset_x - zone_clearance

        # Right strip zone boundaries
        x_right_zone_min = x_right + zone_clearance
        x_right_zone_max = width_mm - zone_margin

        # Vertical extent: 4mm from top and bottom
        y_zone_top = zone_margin
        y_zone_bot = height_mm - zone_margin

        def make_rounded_rect(x_min, y_min, x_max, y_max, radius, steps=8):
            """Create rounded rectangle points"""
            pts = []
            r = min(radius, (x_max - x_min) / 2, (y_max - y_min) / 2)

            # Top-left corner
            for i in range(steps + 1):
                angle = math.pi + (math.pi / 2) * i / steps
                pts.append((x_min + r + r * math.cos(angle), y_min + r + r * math.sin(angle)))

            # Top-right corner
            for i in range(steps + 1):
                angle = 3 * math.pi / 2 + (math.pi / 2) * i / steps
                pts.append((x_max - r + r * math.cos(angle), y_min + r + r * math.sin(angle)))

            # Bottom-right corner
            for i in range(steps + 1):
                angle = 0 + (math.pi / 2) * i / steps
                pts.append((x_max - r + r * math.cos(angle), y_max - r + r * math.sin(angle)))

            # Bottom-left corner
            for i in range(steps + 1):
                angle = math.pi / 2 + (math.pi / 2) * i / steps
                pts.append((x_min + r + r * math.cos(angle), y_max - r + r * math.sin(angle)))

            return pts

        # Side strips: use small corner radius so the narrow strips don't thin out
        strip_width_l = x_left_zone_max - x_left_zone_min
        strip_width_r = x_right_zone_max - x_right_zone_min
        strip_cr = 0.3  # small radius — just enough to avoid sharp DRC corners
        left_zone_pts = make_rounded_rect(x_left_zone_min, y_zone_top, x_left_zone_max, y_zone_bot, strip_cr)
        right_zone_pts = make_rounded_rect(x_right_zone_min, y_zone_top, x_right_zone_max, y_zone_bot, strip_cr)

        # Top connecting bar (from left zone to right zone) with rounded corners
        # Extends 1mm above zone_margin into the board edge margin for solid connection,
        # and overlaps into the first grid rows (zone fills around the pads).
        top_bar_top = max(1.0, y_zone_top - 1.0)
        top_bar_bot = y_zone_top + 3.0
        top_bar_pts = make_rounded_rect(x_left_zone_min, top_bar_top, x_right_zone_max, top_bar_bot, corner_radius)

        def make_zone(net_id, net_name, layer, pts, zone_id, priority=0):
            """Generate KiCad 8/9 format zone WITHOUT filled_polygon - KiCad will fill it"""
            pts_str = "\n".join([f"        (xy {x:.4f} {y:.4f})" for x, y in pts])
            return f"""  (zone (net {net_id}) (net_name "{net_name}") (layer "{layer}") (uuid "{zone_id}")
    (hatch edge 0.5)
    (priority {priority})
    (connect_pads (clearance 0.3))
    (min_thickness 0.2)
    (filled_areas_thickness no)
    (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.5))
    (polygon
      (pts
{pts_str}
      )
    )
  )
"""

        # GND zones on F.Cu - left strip, right strip, and top bar (priority 0)
        zones_str += make_zone(gnd_net, "GND", "F.Cu", left_zone_pts, str(uuid.uuid4()), 0)
        zones_str += make_zone(gnd_net, "GND", "F.Cu", right_zone_pts, str(uuid.uuid4()), 0)
        zones_str += make_zone(gnd_net, "GND", "F.Cu", top_bar_pts, str(uuid.uuid4()), 0)

        # Bottom connecting bar: passes ABOVE the power terminals through the
        # freed-up space, completing the circular GND/VCC connection.
        y_last_normal_row = offset_y + (cutout_r_start - 1) * pitch_mm
        y_bottom_bar_top = y_last_normal_row + 1.0
        y_bottom_bar_bot = y_top_pads - 1.0
        bottom_bar_pts = make_rounded_rect(x_left_zone_min, y_bottom_bar_top,
                                           x_right_zone_max, y_bottom_bar_bot,
                                           min(corner_radius, (y_bottom_bar_bot - y_bottom_bar_top) / 2))
        zones_str += make_zone(gnd_net, "GND", "F.Cu", bottom_bar_pts, str(uuid.uuid4()), 0)

        # VCC zones on B.Cu - left strip, right strip, top bar, and bottom bar (priority 1)
        zones_str += make_zone(vcc_net, "VCC", "B.Cu", left_zone_pts, str(uuid.uuid4()), 1)
        zones_str += make_zone(vcc_net, "VCC", "B.Cu", right_zone_pts, str(uuid.uuid4()), 1)
        zones_str += make_zone(vcc_net, "VCC", "B.Cu", top_bar_pts, str(uuid.uuid4()), 1)
        zones_str += make_zone(vcc_net, "VCC", "B.Cu", bottom_bar_pts, str(uuid.uuid4()), 1)

        # Rail hole pairs - connect to zones via stubs
        sw = 1.0  # stub trace width
        for r in range(0, cutout_r_start - 1, 2):   # step 2 → each pair start row
            y1 = offset_y + r * pitch_mm
            y2 = offset_y + (r + 1) * pitch_mm
            group = r // 2
            is_vcc = (group % 2 == 1)
            net_id = vcc_net if is_vcc else gnd_net
            lyr = 'B.Cu' if is_vcc else 'F.Cu'

            # Pair vertical connection on correct layer
            segments.append(f"  (segment (start {x_left:.4f} {y1:.4f}) (end {x_left:.4f} {y2:.4f}) (width 1.5) (layer {lyr}) (net {net_id}))")
            segments.append(f"  (segment (start {x_right:.4f} {y1:.4f}) (end {x_right:.4f} {y2:.4f}) (width 1.5) (layer {lyr}) (net {net_id}))")

            # Zones connect to pads directly via thermal relief — no stubs needed

        # Connect zones to terminals
        # GND zone → GND terminal (on F.Cu)
        segments.append(f"  (segment (start {x_left_zone_max:.4f} {y_bus_bot:.4f}) (end {x_gnd_t:.4f} {y_bus_bot:.4f}) (width 1.5) (layer F.Cu) (net {gnd_net}))")
        # VCC zone → VCC terminal (on B.Cu)
        segments.append(f"  (segment (start {x_right_zone_min:.4f} {y_bus_bot:.4f}) (end {x_vcc_t:.4f} {y_bus_bot:.4f}) (width 1.5) (layer B.Cu) (net {vcc_net}))")

    # Power terminals
    all_pwr_traces = []
    all_pwr_vias = []
    macros = []
    for col, label, is_left, net_id in [(c_gnd, "GND", True, gnd_net), (c_vcc, "VCC", False, vcc_net)]:
        ax = offset_x + col * pitch_mm
        mod, traces, vias = make_power_terminal(ax, y_top_pads, y_oval_term, label, is_left, net_id)
        macros.append(mod)
        all_pwr_traces.extend(traces)
        all_pwr_vias.extend(vias)

    # Branding: adaptive sizing based on board dimensions
    # Account for power label width (1.3mm font + margin)
    # GND label is at c_gnd + 6.5, extends ±0.65mm = up to c_gnd + 7.15
    # VCC label is at c_vcc - 6.5, extends ±0.65mm = down to c_vcc - 7.15
    # Add 1mm safety margin, so need spacing of at least 8.15/pitch = 3.2
    if width_mm <= 50:
        spacing = 3.5  # Extra room for smaller boards
    else:
        spacing = 3.3  # Minimum safe spacing for all boards
    brand_x_start = offset_x + (c_gnd + spacing) * pitch_mm
    brand_x_end = offset_x + (c_vcc - spacing) * pitch_mm
    brand_y_top = offset_y + cutout_r_start * pitch_mm - 1.0
    brand_y_bot = height_mm - 3.0
    brand_w = brand_x_end - brand_x_start
    brand_h = brand_y_bot - brand_y_top
    total_tracks = len(segments) + len(all_pwr_traces)
    header = f"""(kicad_pcb (version 20171130) (host pcbnew "(5.1.2-stable)")
  (general (thickness 1.6) (tracks {total_tracks}) (modules {len(pads) + 2}) (nets 1))
  (page USLetter)
  (layers
    (0 F.Cu signal) (31 B.Cu signal) (32 B.Adhes user) (33 F.Adhes user)
    (34 B.Paste user) (35 F.Paste user) (36 B.SilkS user) (37 F.SilkS user)
    (38 B.Mask user) (39 F.Mask user) (40 Dwgs.User user) (41 Cmts.User user)
    (42 Eco1.User user) (43 Eco2.User user) (44 Edge.Cuts user) (45 Margin user)
    (46 B.CrtYd user) (47 F.CrtYd user) (48 B.Fab user) (49 F.Fab user)
  )
  (setup (last_trace_width 0.25) (trace_clearance 0.2) (pad_size 1.8 1.8) (pad_drill 1.0)
    (via_size 0.8) (via_drill 0.4) (uvias_allowed yes) (uvia_size 0.6858) (uvia_drill 0.3302))
  (net 0 "")
  (net 1 "GND")
  (net 2 "VCC")
  (net_class Default ""
    (clearance 0.2)
    (trace_width 0.25)
    (via_dia 0.8)
    (via_drill 0.4)
    (uvia_dia 0.6858)
    (uvia_drill 0.3302)
    (add_net "GND")
    (add_net "VCC")
  )
"""

    with open(filename, 'w') as f:
        f.write(header)

        # Edge.Cuts rounded rect
        f.write(f"  (gr_line (start {cr} 0) (end {width_mm - cr} 0) (layer Edge.Cuts) (width 0.1))\n")
        f.write(f"  (gr_line (start {width_mm} {cr}) (end {width_mm} {height_mm - cr}) (layer Edge.Cuts) (width 0.1))\n")
        f.write(f"  (gr_line (start {width_mm - cr} {height_mm}) (end {cr} {height_mm}) (layer Edge.Cuts) (width 0.1))\n")
        f.write(f"  (gr_line (start 0 {height_mm - cr}) (end 0 {cr}) (layer Edge.Cuts) (width 0.1))\n")
        f.write(f"  (gr_arc (start {cr} {cr}) (end 0 {cr}) (angle 90) (layer Edge.Cuts) (width 0.1))\n")
        f.write(f"  (gr_arc (start {width_mm-cr} {cr}) (end {width_mm-cr} 0) (angle 90) (layer Edge.Cuts) (width 0.1))\n")
        f.write(f"  (gr_arc (start {width_mm-cr} {height_mm-cr}) (end {width_mm} {height_mm-cr}) (angle 90) (layer Edge.Cuts) (width 0.1))\n")
        f.write(f"  (gr_arc (start {cr} {height_mm-cr}) (end {cr} {height_mm}) (angle 90) (layer Edge.Cuts) (width 0.1))\n")

        # Branding on BOTH sides
        if brand_w > 5:
            desc = {
                "unconnected": "Unverbunden",
                "stripboard":  "Streifenraster",
                "group_3":     "3er-Gruppen",
                "breadboard":  "Steckbrett",
            }.get(board_type, board_type)

            font_main = min(1.0, brand_w / 20)
            font_sub = font_main * 0.8
            text_y = brand_y_top + 2.5
            text_y2 = text_y + font_main * 1.4
            logo_y = text_y2 + font_sub * 1.5
            logo_h_avail = brand_y_bot - logo_y

            # F.SilkS: normal orientation
            f.write(f"  (gr_text \"Lochraster 2.54mm\" (at {brand_x_start:.4f} {text_y:.4f} 0) (layer F.SilkS)"
                    f" (effects (font (size {font_main:.2f} {font_main:.2f}) (thickness {font_main*0.15:.3f})) (justify left bottom)))\n")
            f.write(f"  (gr_text \"Typ: {desc} | {width_mm:.0f}x{height_mm:.0f}mm\" (at {brand_x_start:.4f} {text_y2:.4f} 0) (layer F.SilkS)"
                    f" (effects (font (size {font_sub:.2f} {font_sub:.2f}) (thickness {font_sub*0.15:.3f})) (justify left bottom)))\n")

            # B.SilkS: To mirror the layout to the opposite side of the physical board (just like
            # the logos), the left anchor from the back view is at physical X coordinate `width_mm - brand_x_start`.
            # using 'justify left bottom mirror' makes it draw inwards towards the center.
            b_text_x = width_mm - brand_x_start
            f.write(f"  (gr_text \"Lochraster 2.54mm\" (at {b_text_x:.4f} {text_y:.4f} 0) (layer B.SilkS)"
                    f" (effects (font (size {font_main:.2f} {font_main:.2f}) (thickness {font_main*0.15:.3f})) (justify left bottom mirror)))\n")
            f.write(f"  (gr_text \"Typ: {desc} | {width_mm:.0f}x{height_mm:.0f}mm\" (at {b_text_x:.4f} {text_y2:.4f} 0) (layer B.SilkS)"
                    f" (effects (font (size {font_sub:.2f} {font_sub:.2f}) (thickness {font_sub*0.15:.3f})) (justify left bottom mirror)))\n")

            # Logos on F.SilkS (normal)
            if brand_w > 25 and logo_h_avail > 2:
                half_w = brand_w / 2 - 0.5
                for line in image_to_kicad("eth_logo_kurz_pos.png", brand_x_start, logo_y, half_w, logo_h_avail):
                    f.write(line + "\n")
                for line in image_to_kicad("Screenshot 2026-01-30 224012.png", brand_x_start + half_w + 1.0, logo_y, half_w, logo_h_avail):
                    f.write(line + "\n")
            elif logo_h_avail > 3:
                logo_each_h = logo_h_avail / 2 - 0.3
                for line in image_to_kicad("eth_logo_kurz_pos.png", brand_x_start, logo_y, brand_w, logo_each_h):
                    f.write(line + "\n")
                for line in image_to_kicad("Screenshot 2026-01-30 224012.png", brand_x_start, logo_y + logo_each_h + 0.5, brand_w, logo_each_h):
                    f.write(line + "\n")

            # Logos on B.SilkS (mirrored)
            # Always mirror around the center of the branding area to keep logos centered
            # and prevent overlap with power labels on the back side
            brand_center_x = brand_x_start + brand_w / 2
            m_x = 2 * brand_center_x

            if brand_w > 25 and logo_h_avail > 2:
                half_w = brand_w / 2 - 0.5
                for line in image_to_kicad("eth_logo_kurz_pos.png", brand_x_start, logo_y, half_w, logo_h_avail, layer="B.SilkS", mirror_x=m_x):
                    f.write(line + "\n")
                for line in image_to_kicad("Screenshot 2026-01-30 224012.png", brand_x_start + half_w + 1.0, logo_y, half_w, logo_h_avail, layer="B.SilkS", mirror_x=m_x):
                    f.write(line + "\n")
            elif logo_h_avail > 3:
                logo_each_h = logo_h_avail / 2 - 0.3
                for line in image_to_kicad("eth_logo_kurz_pos.png", brand_x_start, logo_y, brand_w, logo_each_h, layer="B.SilkS", mirror_x=m_x):
                    f.write(line + "\n")
                for line in image_to_kicad("Screenshot 2026-01-30 224012.png", brand_x_start, logo_y + logo_each_h + 0.5, brand_w, logo_each_h, layer="B.SilkS", mirror_x=m_x):
                    f.write(line + "\n")

        # Outer rail silkscreen: vertical separator line + per-group VCC/GND labels.
        # Both rails: top group = GND, then alternating GND/VCC every 2 holes.
        if has_outer_rails:
            x_left  = offset_x
            x_right = offset_x + (cols - 1) * pitch_mm
            # Separator lines between outer rail and inner grid
            x_sep_l = x_left  + pitch_mm / 2
            x_sep_r = x_right - pitch_mm / 2
            y_top_rail = offset_y
            y_bot_rail = offset_y + (cutout_r_start - 1) * pitch_mm
            lw = 0.15
            for x_f, x_b in [(x_sep_l, width_mm - x_sep_l),
                              (x_sep_r, width_mm - x_sep_r)]:
                f.write(f"  (gr_line (start {x_f:.4f} {y_top_rail:.4f}) (end {x_f:.4f} {y_bot_rail:.4f}) (layer F.SilkS) (width {lw}))\n")
                f.write(f"  (gr_line (start {x_b:.4f} {y_top_rail:.4f}) (end {x_b:.4f} {y_bot_rail:.4f}) (layer B.SilkS) (width {lw}))\n")
            # Per-group labels (0.7mm font, rotated 90°, outside the outer column)
            fs = 0.7
            ft = 0.10
            x_lbl_l = x_left  - 1.4    # left of left rail
            x_lbl_r = x_right + 1.4    # right of right rail
            for g in range(cutout_r_start // 2):
                lbl = "GND" if g % 2 == 0 else "VCC"
                lbl_y = offset_y + (g * 2 + 0.5) * pitch_mm
                # F.SilkS — left and right rails
                f.write(f"  (gr_text \"{lbl}\" (at {x_lbl_l:.4f} {lbl_y:.4f} 90) (layer F.SilkS)"
                        f" (effects (font (size {fs} {fs}) (thickness {ft}))))\n")
                f.write(f"  (gr_text \"{lbl}\" (at {x_lbl_r:.4f} {lbl_y:.4f} 90) (layer F.SilkS)"
                        f" (effects (font (size {fs} {fs}) (thickness {ft}))))\n")
                # B.SilkS — mirrored positions
                f.write(f"  (gr_text \"{lbl}\" (at {width_mm - x_lbl_l:.4f} {lbl_y:.4f} 90) (layer B.SilkS)"
                        f" (effects (font (size {fs} {fs}) (thickness {ft})) (justify mirror)))\n")
                f.write(f"  (gr_text \"{lbl}\" (at {width_mm - x_lbl_r:.4f} {lbl_y:.4f} 90) (layer B.SilkS)"
                        f" (effects (font (size {fs} {fs}) (thickness {ft})) (justify mirror)))\n")

        # B.SilkS trace visualization: thin lines showing where copper traces are
        if True:
            for s in segments:
                # Only visualize B.Cu segments (skip duplicate F.Cu ones)
                if "(layer B.Cu)" not in s:
                    continue
                vis = (s.replace("segment", "gr_line")
                         .replace("(width 1.2)", "(width 0.3)")
                         .replace("(width 1.5)", "(width 0.3)")
                         .replace("(layer B.Cu)", "(layer B.SilkS)")
                         .replace(" (net 0)", ""))
                f.write(vis + "\n")

        for p in pads:
            f.write(p + "\n")
        for m in macros:
            f.write(m + "\n")
        for t in all_pwr_traces:
            f.write(t + "\n")
        for v in all_pwr_vias:
            f.write(v + "\n")
        for s in segments:
            f.write(s + "\n")

        # Write zones for GND and VCC planes
        if zones_str:
            f.write(zones_str)

        f.write(")\n")


if __name__ == "__main__":
    for w, h in [(100, 160), (70, 100), (50, 70)]:
        for t in ["unconnected", "stripboard", "group_3", "breadboard"]:
            fn = f"proto_{w}x{h}_{t}.kicad_pcb"
            generate_pcb(fn, w, h, t)
            print(f"Generated {fn}")
