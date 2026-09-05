"""Offline renderer: Allegro 3D Canvas OBJ export + STEP models instanced from a placement dump.

    python render3d/render_board.py test                 # one 1280x720 frame to check the scene
    python render3d/render_board.py stills               # standard views at 3840x2160
    python render3d/render_board.py turntable [frames]   # 360-degree orbit, 1080p frames
    python render3d/render_board.py reveal [frames]      # eased move from a closeup into the hero view

Inputs come from board.json ("render3d" section, see board.example.json) or from flags:
    --obj EXPORT.obj       File > Export > OBJ from the 3D Canvas (design units, e.g. mils)
    --placement P.json     bridge/allegro/step_mapping.py dump
    --step-dir DIR         the .step files named in the placement dump
    --out DIR              where renders/ and video/ go

WHY NOT RENDER IN THE CANVAS
    The 3D Canvas has no camera API: Shift+middle drag rotates about SCREEN axes with a
    trackball state that presets do not reset, so a turntable cannot be scripted. Its OBJ
    export keeps the board (copper, plating, mask with Tf transparency, silk, dielectric)
    with colours, but merges every STEP model into ONE material with no Kd, and exports
    mechanical-symbol extents as grey boxes. So the board comes from the OBJ and the
    components are re-instanced here from the STEP files, colours intact.

TRANSFORM (verified against the canvas): model mm -> Rz(rz) Ry(ry) Rx(rx) -> + offset (design
units -> mm) -> Rz(instance rotation, CCW) -> + instance xy, z = top of TOP copper.
"""
from __future__ import annotations
import sys, json, math, pathlib, time, argparse
import numpy as np
import pyvista as pv

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

UNIT_MM = {"mils": 0.0254, "inch": 25.4, "inches": 25.4, "millimeter": 1.0, "millimeters": 1.0, "mm": 1.0,
           "centimeter": 10.0, "micron": 0.001, "microns": 0.001}
BG_BOTTOM, BG_TOP = "#14161b", "#3b3f4a"
FX = {"ssao": False, "shadows": False}     # shadows break depth-peeled transparency; SSAO adds little
CFG = {}


# ----------------------------------------------------------------------------- config
def load_config(args):
    cfg = {}
    try:
        from bridge.allegro import board_profile
        cfg = dict(board_profile.load().get("render3d", {}))
    except Exception:
        pass
    for k in ("obj", "placement", "step_dir", "out"):
        v = getattr(args, k.replace("_", "_"), None)
        if v:
            cfg[k] = v
    missing = [k for k in ("obj", "placement", "step_dir") if not cfg.get(k)]
    if missing:
        raise SystemExit(f"need {missing}: pass flags or fill the render3d section of board.json")
    cfg.setdefault("out", str(pathlib.Path(cfg["obj"]).parent.parent))
    cfg["obj"] = pathlib.Path(cfg["obj"]); cfg["placement"] = pathlib.Path(cfg["placement"])
    cfg["step_dir"] = pathlib.Path(cfg["step_dir"]); cfg["out"] = pathlib.Path(cfg["out"])
    cfg["tess"] = cfg["obj"].parent / "tess"
    cfg["renders"] = cfg["out"] / "renders"; cfg["video"] = cfg["out"] / "video"
    return cfg


def placement():
    return json.load(open(CFG["placement"]))


def unit_mm():
    return UNIT_MM.get(placement().get("units", "mils").lower(), 0.0254)


def outline_mm():
    """((x0 y0) (x1 y1)) in design units -> (center xyz, size xy) in mm."""
    import re
    nums = [float(x) for x in re.findall(r"[-\d.]+", placement()["outline"])]
    u = unit_mm()
    x0, y0, x1, y1 = (n * u for n in nums[:4])
    return np.array([(x0 + x1) / 2, (y0 + y1) / 2, 0.8]), (x1 - x0, y1 - y0)


# ----------------------------------------------------------------------------- board (OBJ)
def load_obj_cached():
    cache = CFG["obj"].with_suffix(".npz")
    if cache.exists() and cache.stat().st_mtime > CFG["obj"].stat().st_mtime:
        d = np.load(cache, allow_pickle=True)
        n = len(d["mats"])
        return d["mats"].tolist(), d["kd"], d["opacity"], d["haskd"], [d[f"pts_{i}"] for i in range(n)], [d[f"faces_{i}"] for i in range(n)]
    mtl, cur = {}, None
    for line in open(CFG["obj"].with_suffix(".mtl")):
        p = line.split()
        if not p:
            continue
        if p[0] == "newmtl":
            cur = p[1]; mtl[cur] = {}
        elif cur:
            mtl[cur][p[0]] = [float(x) for x in p[1:]] if p[0] in ("Kd", "Ks", "Tf") else p[1:]
    verts, per, cur = [], {}, "?"
    for line in open(CFG["obj"]):
        if line.startswith("v "):
            verts.append(tuple(float(x) for x in line.split()[1:4]))
        elif line.startswith("usemtl"):
            cur = line.split()[1]
        elif line.startswith("f "):
            idx = []
            for t in line.split()[1:]:
                i = int(t.split("/")[0]); idx.append(i - 1 if i > 0 else len(verts) + i)   # HOOPS writes negative (relative) indices
            per.setdefault(cur, []).append(idx)
    V = np.array(verts, np.float64) * unit_mm()
    mats, kd, opac, haskd, pts, faces = [], [], [], [], [], []
    for m, polys in per.items():
        used = sorted({i for poly in polys for i in poly})
        remap = {i: k for k, i in enumerate(used)}
        conn = []
        for poly in polys:
            conn.append(len(poly)); conn.extend(remap[i] for i in poly)
        mats.append(m)
        haskd.append("Kd" in mtl.get(m, {}))
        kd.append(mtl.get(m, {}).get("Kd", [0.5, 0.5, 0.5]))
        tf = mtl.get(m, {}).get("Tf")
        opac.append(1.0 - float(np.mean(tf)) if tf else 1.0)
        pts.append(V[used].astype(np.float32)); faces.append(np.array(conn, np.int64))
    np.savez_compressed(cache, mats=np.array(mats, dtype=object), kd=np.array(kd, np.float32),
                        opacity=np.array(opac, np.float32), haskd=np.array(haskd),
                        **{f"pts_{i}": pts[i] for i in range(len(mats))}, **{f"faces_{i}": faces[i] for i in range(len(mats))})
    return mats, np.array(kd, np.float32), np.array(opac, np.float32), np.array(haskd), pts, faces


def classify(kd, opacity, haskd):
    """What an Allegro-exported material is. Colours are the canvas Black theme's defaults."""
    r, g, b = kd
    if not haskd:
        return "step_lump"                       # every STEP model, uncoloured: skipped, re-instanced below
    if abs(r - 0.2667) < 0.01 and abs(g - 0.2667) < 0.01 and abs(b - 0.2667) < 0.01:
        return "extrusion"                       # place-bound / mech extents box: skipped
    if opacity < 0.99:
        return "mask"
    if r > 0.9 and g > 0.9 and b > 0.9:
        return "silk"
    if abs(r - 0.918) < 0.02 and abs(g - 0.741) < 0.02:
        return "plating"
    if abs(r - 0.722) < 0.02 and abs(g - 0.451) < 0.02:
        return "copper"
    if r > 0.9 and b > 0.7:
        return "dielectric"
    return "other"


STYLE = {
    "copper":     dict(color=(0.80, 0.50, 0.24), specular=0.55, specular_power=40, ambient=0.18, diffuse=0.85),
    "plating":    dict(color=(0.93, 0.78, 0.30), specular=0.8, specular_power=60, ambient=0.2, diffuse=0.8),
    "mask":       dict(color=(0.07, 0.07, 0.085), specular=0.5, specular_power=25, ambient=0.4, diffuse=0.8, opacity=0.82),
    "silk":       dict(color=(0.96, 0.96, 0.94), specular=0.05, specular_power=5, ambient=0.35, diffuse=0.75),
    "dielectric": dict(color=(0.86, 0.87, 0.70), specular=0.1, specular_power=8, ambient=0.25, diffuse=0.8),
    "other":      dict(color=(0.5, 0.5, 0.5)),
}


def add_board(pl):
    mats, kd, opac, haskd, pts, faces = load_obj_cached()
    z_top = 0.0
    for m, c, o, h, p, f in zip(mats, kd, opac, haskd, pts, faces):
        kind = classify(c, o, h)
        if kind in ("step_lump", "extrusion"):
            continue
        if kind in ("copper", "plating"):
            z_top = max(z_top, float(p[:, 2].max()))
        mesh = pv.PolyData(p, f).triangulate()
        mesh = mesh.compute_normals(cell_normals=True, point_normals=False, auto_orient_normals=False)
        pl.add_mesh(mesh, smooth_shading=False, name=f"board_{m}", **STYLE[kind])
    return z_top


# ----------------------------------------------------------------------------- components
def rot(axis, deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def build_cache(force=False):
    from step_tess import tessellate
    CFG["tess"].mkdir(parents=True, exist_ok=True)
    for sd, m in placement()["mappings"].items():
        if not m:
            continue
        dst = CFG["tess"] / (pathlib.Path(m["file"]).stem + ".npz")
        src = CFG["step_dir"] / m["file"]
        if dst.exists() and not force and dst.stat().st_mtime > src.stat().st_mtime:
            continue
        t0 = time.time()
        out = tessellate(str(src))
        np.savez_compressed(dst, **out)
        print(f"  {m['file']:50s} {len(out['colors'])} colours  {time.time() - t0:5.1f}s")


def load_tess(file):
    d = np.load(CFG["tess"] / (pathlib.Path(file).stem + ".npz"))
    return [(tuple(float(x) for x in col), d[f"verts_{k}"].astype(np.float64), d[f"faces_{k}"].astype(np.int64))
            for k, col in enumerate(d["colors"])]


def material_for(col):
    r, g, b = col
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    sat = max(col) - min(col)
    if sat < 0.08 and lum > 0.5:      # silver / tin / nickel
        return dict(specular=0.9, specular_power=45, ambient=0.15, diffuse=0.75, smooth_shading=True)
    if sat > 0.15 and r > 0.5 and g > 0.4 and b < 0.35:   # gold / brass
        return dict(specular=0.85, specular_power=50, ambient=0.18, diffuse=0.8, smooth_shading=True)
    if lum < 0.12:                    # black plastic / epoxy
        return dict(specular=0.6, specular_power=28, ambient=0.45, diffuse=0.9, smooth_shading=True)
    return dict(specular=0.3, specular_power=15, ambient=0.25, diffuse=0.85, smooth_shading=True)


def add_components(pl, z_top):
    place = placement(); maps = place["mappings"]; u = unit_mm()
    by_color = {}
    for s in place["symbols"]:
        m = maps.get(s["symdef"])
        if not m:
            continue
        R_map = rot("z", m["rotation_z"]) @ rot("y", m["rotation_y"]) @ rot("x", m["rotation_x"])
        off = np.array([m["offset_x"], m["offset_y"], m["offset_z"]]) * u
        R_inst = rot("z", s["rot"])
        pos = np.array([s["x"] * u, s["y"] * u, z_top])
        for col, V, F in load_tess(m["file"]):
            P = (V @ R_map.T) + off
            if s.get("mirror"):
                P = P * np.array([1, -1, -1]) @ np.eye(3)      # bottom-side part: flip through the board (unverified)
                P[:, 2] += 0.0
            P = (P @ R_inst.T) + pos
            key = tuple(round(c, 3) for c in col)
            g = by_color.setdefault(key, [[], [], 0])
            g[0].append(P); g[1].append(F + g[2]); g[2] += len(P)
    for col, (Vs, Fs, _) in by_color.items():
        V = np.vstack(Vs); F = np.vstack(Fs)
        faces = np.hstack([np.full((len(F), 1), 3), F]).ravel()
        mesh = pv.PolyData(V, faces).clean().compute_normals(split_vertices=True, feature_angle=35, auto_orient_normals=False)
        shown = col
        if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] < 0.12:
            shown = tuple(0.17 + 0.3 * c for c in col)      # near-black: lift to charcoal or it renders as a hole
        pl.add_mesh(mesh, color=shown, name=f"comp_{col}", **material_for(col))


# ----------------------------------------------------------------------------- scene / camera
def make_plotter(w, h):
    pl = pv.Plotter(off_screen=True, window_size=(w, h), lighting="none")
    pl.set_background(BG_BOTTOM, top=BG_TOP)
    z_top = add_board(pl)
    add_components(pl, z_top)
    c, (sx, sy) = outline_mm()
    L = max(sx, sy)
    lights = [
        pv.Light(position=(c[0] - 1.3 * L, c[1] - 1.6 * L, 2.0 * L), focal_point=c, color=(1.0, 0.96, 0.90), intensity=1.05),
        pv.Light(position=(c[0] + 2.0 * L, c[1] - 0.6 * L, 1.3 * L), focal_point=c, color=(0.82, 0.88, 1.0), intensity=0.45),
        pv.Light(position=(c[0] + 0.3 * L, c[1] + 2.0 * L, 1.5 * L), focal_point=c, color=(1.0, 1.0, 1.0), intensity=0.55),
        pv.Light(position=(c[0], c[1], 4.5 * L), focal_point=c, color=(1, 1, 1), intensity=0.35),
        pv.Light(position=(c[0] - 0.7 * L, c[1] - 1.2 * L, -2.5 * L), focal_point=c, color=(0.9, 0.93, 1.0), intensity=2.2),
    ]
    for Lt in lights:
        Lt.positional = False
        pl.add_light(Lt)
    pl.enable_depth_peeling(number_of_peels=6, occlusion_ratio=0.0)
    pl.enable_anti_aliasing("ssaa")
    if FX["ssao"]:
        pl.enable_ssao(radius=L / 30, bias=0.5, kernel_size=64, blur=True)
    if FX["shadows"]:
        pl.enable_shadows()
    return pl


def set_camera(pl, az_deg, el_deg, dist, focal=None, view_angle=28.0):
    f = outline_mm()[0] if focal is None else np.asarray(focal, float)
    az, el = math.radians(az_deg), math.radians(el_deg)
    eye = f + dist * np.array([math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)])
    pl.camera_position = [tuple(eye), tuple(f), (0, 0, 1)]
    pl.camera.view_angle = view_angle


def render(pl, path):
    pl.render()                 # without this an off-screen plotter returns the PREVIOUS frame
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(path), transparent_background=False)


# ----------------------------------------------------------------------------- views
def standard_views():
    """Distances scale with the long side of the outline (tuned on a 203 mm board at 275 mm)."""
    _, (sx, sy) = outline_mm(); L = max(sx, sy)
    k = L / 203.0
    return [
        ("iso_front_right",  35, 32, 275 * k, None, 28),
        ("iso_front_left",  -35, 32, 275 * k, None, 28),
        ("iso_back_right",  145, 32, 275 * k, None, 28),
        ("iso_back_left",  -145, 32, 275 * k, None, 28),
        ("top",               0, 89.9, 265 * k, None, 28),
        ("bottom",            0, -89.9, 265 * k, None, 28),
        ("front_low",         0, 12, 280 * k, None, 24),
        ("back_low",        180, 12, 280 * k, None, 24),
        ("left_end",        -90, 20, 230 * k, None, 26),
        ("right_end",        90, 20, 230 * k, None, 26),
    ] + [(c["name"], c["az"], c["el"], c["dist"], c.get("focal"), c.get("view_angle", 30))
         for c in CFG.get("closeups", [])]


def cmd_test():
    pl = make_plotter(1280, 720)
    v = standard_views()[0]
    set_camera(pl, v[1], v[2], v[3], v[4], v[5]); render(pl, CFG["renders"] / "test_iso.png")
    print("wrote", CFG["renders"] / "test_iso.png")


def cmd_stills(w=3840, h=2160):
    pl = make_plotter(w, h)
    for name, az, el, dist, focal, va in standard_views():
        set_camera(pl, az, el, dist, focal, va)
        t0 = time.time(); render(pl, CFG["renders"] / f"{name}.png"); print(f"  {name:18s} {time.time() - t0:4.1f}s")


def smoothstep(t):
    return t * t * (3 - 2 * t)


def cmd_turntable(frames=360, w=1920, h=1080):
    d = CFG["video"] / "frames_turntable"; d.mkdir(parents=True, exist_ok=True)
    pl = make_plotter(w, h); dist = standard_views()[0][3] * 1.04
    for i in range(frames):
        set_camera(pl, 35 + 360.0 * i / frames, 32, dist)
        render(pl, d / f"f_{i:04d}.png")
        if i % 30 == 0:
            print(f"  frame {i}/{frames}")


def cmd_reveal(frames=240, w=1920, h=1080):
    """From the first closeup in board.json (or a low front view) into the hero isometric."""
    d = CFG["video"] / "frames_reveal"; d.mkdir(parents=True, exist_ok=True)
    pl = make_plotter(w, h)
    hero = standard_views()[0]; c = outline_mm()[0]
    cl = (CFG.get("closeups") or [dict(az=0, el=10, dist=hero[3] * 0.55, focal=None)])[0]
    a0 = (cl["az"], cl["el"], cl["dist"], np.asarray(cl.get("focal") or c, float))
    a1 = (hero[1], hero[2], hero[3] * 1.04, c)
    for i in range(frames):
        t = smoothstep(i / (frames - 1))
        set_camera(pl, a0[0] + (a1[0] - a0[0]) * t, a0[1] + (a1[1] - a0[1]) * t,
                   a0[2] + (a1[2] - a0[2]) * t, a0[3] * (1 - t) + a1[3] * t)
        render(pl, d / f"f_{i:04d}.png")
        if i % 30 == 0:
            print(f"  frame {i}/{frames}")


def main(argv):
    ap = argparse.ArgumentParser(description="Offline board renderer (see module docstring)")
    ap.add_argument("cmd", choices=["build", "test", "stills", "turntable", "reveal"])
    ap.add_argument("n", nargs="?", type=int)
    ap.add_argument("--obj"); ap.add_argument("--placement"); ap.add_argument("--step-dir", dest="step_dir"); ap.add_argument("--out")
    ap.add_argument("--ssao", action="store_true"); ap.add_argument("--shadows", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    CFG.update(load_config(a)); FX["ssao"] = a.ssao; FX["shadows"] = a.shadows
    build_cache(a.force)
    if a.cmd == "test": cmd_test()
    elif a.cmd == "stills": cmd_stills()
    elif a.cmd == "turntable": cmd_turntable(a.n or 360)
    elif a.cmd == "reveal": cmd_reveal(a.n or 240)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
