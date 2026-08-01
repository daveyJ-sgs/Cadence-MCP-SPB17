"""Switch the open board between a clean placement view and everything-on.

Why this exists: a freshly netrev'd board turns on every component-text class
on every subclass, top and bottom -- REF DES, DEVICE TYPE, COMPONENT VALUE,
TOLERANCE and USER PART NUMBER each drawn on SILKSCREEN, ASSEMBLY and DISPLAY,
for both sides. That is up to 30 pieces of text per part. On a dense board
bodies disappear underneath strings like "LM4562MAXNOPB_OL..." and you cannot
see what you are placing.

    python bridge/allegro/text_view.py place    # refdes only, top side
    python bridge/allegro/text_view.py value    # refdes + value, top side
    python bridge/allegro/text_view.py all      # everything back on

Visibility lives in the .brd file, so this dirties the design -- Allegro will
prompt to save. That is harmless and it is how you make the view stick.

`place` also stashes the pre-change visibility in the SKILL global
`ppVisSave`, so within the same Allegro session

    axlVisibleSet(ppVisSave)  axlVisibleUpdate(t)

restores exactly what was there before. That global does not survive closing
Allegro; `all` is the durable way back.
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from bridge.allegro.allegro_client import AllegroBridge  # noqa: E402

# Component text classes. Each one exists on SILKSCREEN/ASSEMBLY/DISPLAY x
# TOP/BOTTOM; passing the bare class name hits every subclass at once
# (axlVisibleLayer: "If given just class name, sets entire layer").
TEXT_CLASSES = [
    "REF DES",
    "DEVICE TYPE",
    "COMPONENT VALUE",
    "TOLERANCE",
    "USER PART NUMBER",
]

# Non-text clutter, hidden by the same views.
#
# MANUFACTURING/NO_PROBE_TOP draws a big square around each tall part -- on
# C10 it is 447 mil across, sized to the UFG can's 11 mm HEIGHT rather than
# its 5 mm diameter, so U6 and R22 sit inside it and it reads as a collision.
# It is not one: it is advisory in-circuit-test data telling a fixture house
# where a probe cannot reach, and DRC does not enforce it against components.
# Verified 2026-07-31 as the ONLY MANUFACTURING subclass in use, owned by
# C8-C11 and U1-U6, so hiding it hides nothing else. Do not DELETE it -- if
# the board is ever ICT'd, the fixture house wants it.
EXTRA_CLASSES = ["MANUFACTURING/NO_PROBE_TOP"]

# What each view turns back on after the blanket off.
VIEWS = {
    "place": ["REF DES/SILKSCREEN_TOP"],
    "value": ["REF DES/SILKSCREEN_TOP", "COMPONENT VALUE/SILKSCREEN_TOP"],
}


def apply(br: AllegroBridge, view: str) -> None:
    if view == "all":
        for cls in TEXT_CLASSES + EXTRA_CLASSES:
            r = br.send(f'axlVisibleLayer("{cls}" t)')
            print(f"  on   {cls:30} -> {r}")
    else:
        # Stash first, so axlVisibleSet(ppVisSave) is an in-session undo.
        print("  saved prior visibility to SKILL global ppVisSave:",
              br.send("ppVisSave = axlVisibleGet() t"))
        for cls in TEXT_CLASSES + EXTRA_CLASSES:
            r = br.send(f'axlVisibleLayer("{cls}" nil)')
            print(f"  off  {cls:30} -> {r}")
        for layer in VIEWS[view]:
            r = br.send(f'axlVisibleLayer("{layer}" t)')
            print(f"  on   {layer:20} -> {r}")
    # t = redraw now rather than deferring to the next user interaction.
    print("  update:", br.send("axlVisibleUpdate(t)"))


def main(argv: list[str]) -> int:
    view = argv[0] if argv else "place"
    if view not in VIEWS and view != "all":
        print(f"unknown view {view!r}; use: place | value | all", file=sys.stderr)
        return 2
    with AllegroBridge() as br:
        print("ping:", br.ping())
        print(f"view: {view}")
        apply(br, view)
    print("\nDone. Allegro will now consider the design modified -- save it if "
          "you want the view to persist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
