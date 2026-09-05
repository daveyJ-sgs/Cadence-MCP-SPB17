"""Tessellate a STEP file into colour-grouped triangle meshes using OpenCascade (OCP).

    python step_tess.py model.step [out.npz]

Walks the XCAF assembly tree so per-component locations and per-face / per-solid
colours survive (plain cadquery importStep drops colours). Output groups:
    colors  (G,3) float32      verts_i (Ni,3) float32 mm      faces_i (Mi,3) int32
"""
from __future__ import annotations
import sys, pathlib, numpy as np
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorSurf, XCAFDoc_ColorGen
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.Quantity import Quantity_Color
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Trsf
from OCP.IFSelect import IFSelect_RetDone

DEFAULT = (0.55, 0.55, 0.58)


def load(path: str):
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    rd = STEPCAFControl_Reader()
    rd.SetColorMode(True); rd.SetNameMode(True); rd.SetLayerMode(True)
    if rd.ReadFile(path) != IFSelect_RetDone:
        raise RuntimeError(f"cannot read {path}")
    rd.Transfer(doc)
    return doc


def color_of(ct, shape, label=None):
    c = Quantity_Color()
    for typ in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
        if ct.GetColor(shape, typ, c):
            return (c.Red(), c.Green(), c.Blue())
    if label is not None:
        for typ in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
            if ct.GetColor_s(label, typ, c):
                return (c.Red(), c.Green(), c.Blue())
    return None


def tessellate(path: str, lin=0.04, ang=0.35):
    doc = load(path)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    groups: dict[tuple, list] = {}

    def add_face(face, trsf, col):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            return
        t = loc.Transformation().Multiplied(trsf) if False else trsf.Multiplied(loc.Transformation())
        n = tri.NbNodes(); m = tri.NbTriangles()
        V = np.empty((n, 3), np.float64)
        for i in range(1, n + 1):
            p = tri.Node(i).Transformed(t)
            V[i - 1] = (p.X(), p.Y(), p.Z())
        F = np.empty((m, 3), np.int64)
        rev = face.Orientation() == TopAbs_REVERSED
        for i in range(1, m + 1):
            a, b, c = tri.Triangle(i).Get()
            F[i - 1] = (a - 1, c - 1, b - 1) if rev else (a - 1, b - 1, c - 1)
        g = groups.setdefault(tuple(round(x, 3) for x in col), [[], [], 0])
        g[0].append(V); g[1].append(F + g[2]); g[2] += n

    def leaf(label, trsf):
        shape = st.GetShape_s(label)
        BRepMesh_IncrementalMesh(shape, lin, False, ang, True)
        shape_col = color_of(ct, shape, label)
        # solids may carry their own colour
        ex = TopExp_Explorer(shape, TopAbs_SOLID)
        solids = []
        while ex.More():
            solids.append(TopoDS.Solid_s(ex.Current())); ex.Next()
        if not solids:
            solids = [shape]
        for sol in solids:
            scol = color_of(ct, sol) or shape_col
            fx = TopExp_Explorer(sol, TopAbs_FACE)
            while fx.More():
                face = TopoDS.Face_s(fx.Current())
                col = color_of(ct, face) or scol or DEFAULT
                add_face(face, trsf, col)
                fx.Next()

    def walk(label, trsf):
        if st.IsAssembly_s(label):
            comps = TDF_LabelSequence(); st.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                c = comps.Value(i)
                loc = st.GetLocation_s(c)
                ref = TDF_Label()
                if st.GetReferredShape_s(c, ref):
                    walk(ref, trsf.Multiplied(loc.Transformation()))
        elif st.IsReference_s(label):
            ref = TDF_Label(); st.GetReferredShape_s(label, ref)
            walk(ref, trsf.Multiplied(st.GetLocation_s(label).Transformation()))
        else:
            leaf(label, trsf)

    free = TDF_LabelSequence(); st.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), gp_Trsf())

    out = {"colors": np.array(list(groups.keys()), np.float32)}
    for k, (col, (Vs, Fs, _)) in enumerate(groups.items()):
        out[f"verts_{k}"] = np.vstack(Vs).astype(np.float32)
        out[f"faces_{k}"] = np.vstack(Fs).astype(np.int32)
    return out


def main(argv):
    src = argv[0]; dst = argv[1] if len(argv) > 1 else str(pathlib.Path(src).with_suffix(".npz"))
    out = tessellate(src)
    np.savez_compressed(dst, **out)
    nv = sum(out[k].shape[0] for k in out if k.startswith("verts_")); nf = sum(out[k].shape[0] for k in out if k.startswith("faces_"))
    allv = np.vstack([out[k] for k in out if k.startswith("verts_")])
    print(f"{pathlib.Path(src).name}: {len(out['colors'])} colours, {nv} verts, {nf} tris, bbox min {allv.min(0).round(2)} max {allv.max(0).round(2)}")
    for c in out["colors"]: print("   colour", c.round(2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
