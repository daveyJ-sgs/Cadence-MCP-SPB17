# render3d — stills and turntables of a mapped board

Allegro 17.4's 3D Canvas will show you a STEP-populated board but will not give you a
camera you can script, and its OBJ export drops every STEP model's colour. This folder
turns what the canvas *does* export into publication renders and video, offline, with an
exact camera.

```
3D Canvas  ──File > Export > OBJ──▶  board.obj (+ .mtl)      copper, plating, mask, silk, dielectric, coloured
SKILL bridge ──step_mapping.py dump─▶ placement.json         every symbol: symdef, xy, rotation + every STEP mapping
allegro/step/*.step ──step_tess.py──▶ tess/*.npz             colour-grouped triangles per model (OCP / XCAF)
                                        │
render_board.py  ──────────────────────┴──▶ renders/*.png  video/frames_*/f_0000.png
make_video.py    ──────────────────────────▶ *_turntable_1080p.mp4  square  gif  reveal  combo
```

## Setup

```
pip install --user pyvista cadquery imageio imageio-ffmpeg     # cp314 wheels exist for all of them
```

Fill the `render3d` section of `board.json` (see `board.example.json`): the OBJ, the placement
dump, the STEP folder, an output root, and optional close-up cameras.

## Run

```
python bridge/allegro/step_mapping.py dump  C:/proj/3d/export/placement.json   # Allegro open, bridge up
python render3d/render_board.py test            # one 720p frame: check placement before spending time
python render3d/render_board.py stills          # 4 isometrics, top, bottom, front/back low, both ends, closeups, 3840x2160
python render3d/render_board.py turntable 360   # 12 s at 30 fps
python render3d/render_board.py reveal 240      # eased move from the first closeup into the hero view
python render3d/make_video.py turntable         # mp4 + 1:1 crop + gif
python render3d/make_video.py reveal
python render3d/make_video.py combo             # reveal crossfading into the spin
```

Roughly 3 s per 1080p frame, 20 s scene build, on a laptop GPU.

## What the scripts know that took a day to learn

- **Board first, components second.** The OBJ's materials map cleanly onto layers (the mask
  carries `Tf`, which becomes opacity), but every STEP model lands in one material with no
  `Kd`, and mechanical-symbol extents come out as grey boxes. `render_board.py` skips both
  and re-instances the components from the STEP files with the mapping transform:
  model mm → rotate X, Y, Z → + offset → instance rotation → instance position, z = top of
  the TOP copper found in the OBJ. Verified against the canvas on a 57-part board.
- **Colours need XCAF.** `cadquery.importers.importStep` discards them; `step_tess.py` walks
  the assembly with `STEPCAFControl_Reader` and reads per-face colours (`GetColor` on shapes,
  the static `GetColor_s` on labels). KiCad packages3D and cadquery `Assembly` exports both
  carry colour; a bare vendor STEP often does not, and then everything renders grey.
- **PyVista traps.** Call `plotter.render()` before `screenshot()` on an off-screen plotter or
  you get the previous frame back. `enable_shadows()` breaks depth-peeled transparency (the
  mask goes opaque cream). SSAO changes nothing visible here. Near-black plastics need a
  colour floor or they render as holes; a light from below is needed for the bottom view.
- **Camera math is trivial once you own it:** azimuth/elevation/distance about the outline
  centre, distances scaled from the board's long side. That is the whole reason to leave the
  canvas.
