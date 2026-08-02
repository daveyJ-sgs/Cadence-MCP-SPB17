# Driving Allegro / OrCAD PCB Designer 17.4 from SKILL — what actually bites

Findings from building the bridge in this repo and using it to lay out a real
four-layer board. Everything here was verified against a live database, not
inferred from documentation. Where the documentation is wrong, that is said.

Design specifics live with the design, not here. `board.json` (gitignored)
carries the net names, refdes and coordinates the tools need.

---

## 1. The failure mode you will hit first

**An active GUI command silently discards writes.**

```
axlDBCreateVia(...)        -> nil
axlDBCreateLine(...)       -> nil
axlSaveDesign(?noConfirm t)-> nil
```

Reads keep returning correct data throughout. No error, no dialog, no hang.
Any command counts — including modes that do not feel like commands, such as
etch edit. The board must be at *no* active command.

> **When a write returns `nil`, test `axlSaveDesign(?noConfirm t)` FIRST.** If
> that is also `nil`, stop debugging geometry and clear the command in the GUI.
> Two rounds of chasing coordinate precision were wasted before this was the
> obvious first check.

A related, worse state: if a bridge client is killed mid-exchange, the SKILL
relay can wedge. `--ping` still answers (the helper replies locally) while
every real evaluation hangs. Restarting Allegro is the reliable fix.

---

## 2. Allegro demands EXACT coordinates and says nothing when it does not get them

Three variants, all silent:

| what | requirement | what happens if you miss |
|---|---|---|
| cline to pin | endpoint must equal `pin->xy` | lands *inside* the pad, looks connected, net splits into two branches |
| via to cline | via centre must sit on the cline centreline | no bond |
| any coordinate | must be representable | `axlDBCreateLine` returns nil |

The first is the dangerous one. A trace ending 0.32 mil short of a DFN pin is
invisible on screen, passes DRC, and orphans the branch.

**Never route to a coordinate copied out of a document.** Read `pin->xy` at the
moment of routing. Fine-pitch package pins are rarely on round numbers — DFN
pitches of 17.72 and 19.69 mil put almost every pin on a fraction.

For a via that must land on a sloped cline, pick a parameter `t` that makes the
interpolated point a clean value rather than computing an arbitrary fraction.

---

## 3. Xnet inheritance applies the wrong constraint set to signal nets

A net continuing through a passive is treated as one **extended net**, and the
cset of the wider Xnet governs the whole thing. A signal net that reaches a
power net through a single resistor inherits the power width rules.

Symptom: every segment of a freshly routed signal net reports

```
Maximum Neck Length    actual <length>    expected <necklength_max>
```

because a normal signal width is a *neck* relative to the inherited
`width_min`. Editing `DEFAULT` does nothing — `DEFAULT` was never governing.

```skill
net->xnet->name            ; the net that actually owns the rules
```

Fix by scoping a cset to the affected nets:

```skill
axlCNSCreate('physical "AUDIO" "DEFAULT")
axlCNSSetPhysical("AUDIO" <layer> 'width_min 12.0)
axlDBAddProp(list(net) list(list("PHYSICAL_CONSTRAINT_SET" "AUDIO")))
```

⛔ **Cset names are not netclass names.** A netclass called `POWER_NETS` may use
a cset called `POWER`. `axlCNSGetPhysical` returns bare `nil` for a cset that
does not exist, indistinguishable from "unset". `netclass->physical` returns
`t`/`nil`, not a name. **`axlCnsList('physical)` is the only honest way to
learn what exists.**

> If a constraint result makes no sense, check `net->xnet` before touching any
> cset. Assign the cset BEFORE routing a new class of net, not after the DRCs.

---

## 4. Constraint changes do not re-trigger DRC

Adding copper updates DRC incrementally. **Editing a constraint does not.**

```skill
axlDRCUpdate(t)        ; takes an argument; axlDRCUpdate() errors
```

A DRC count read after a cset edit is stale in *either* direction — it can show
phantom violations against legal copper, or hide real ones.

---

## 5. Object model

```skill
net->branches            ; list of connected islands
branch->children         ; pins, vias, paths, shapes
path->segments           ; each has ->startEnd, ->width, ->layer
```

- Clines are objType **`"path"`**, not `"cline"`.
- `design->vias`, `design->clines`, `design->etch` **do not exist**.
- Fields that return `nil` for a non-existent attribute and so read as a
  meaningful answer: `isDynamic`, `dynType`, `shapeIsBoundary`. `readOnly`
  returns `t` on everything.
- `append` takes exactly two arguments, so `apply('append <list-of-lists>)`
  fails on a one-element list. Walk branches from the client instead.

### ⛔ Branch indices are not stable

`nth(0 net->branches)` is not "the" branch. A partly-routed net has one branch
per island and the order is not contractual — code that searches only branch 0
will miss things that are plainly there. Three separate bugs in this repo came
from that assumption.

Worse: **branches renumber on every delete.** Looping `for bi in range(n)` while
deleting inside the loop silently skips one. Re-scan from branch 0 after each
delete and repeat until a clean pass, with an iteration cap.

---

## 6. Dynamic shapes

- **Vias trigger the dynamic-shape update; clines do not.** Testing whether a
  pour is dynamic by drawing a cline gives a false negative — three evenings
  were lost to that.
- A **foreign-net** via punches an isolating void. A via on the shape's **own**
  net gets a thermal tie and costs the plane nothing. Measure the void count
  either side of a change; it is the cheapest confirmation available.
- ⛔ **`axlShapeChangeDynamicType` is actively harmful.** It does not convert
  the shape, and a shape passed to it can no longer be deleted from the bridge
  — `axlDeleteObject` returns `nil` forever, and it survives save and reload.
  Convert in the GUI: `Shape → Change Shape Type`, with
  `Options → Shape Fill → Type = "To dynamic copper"`. The Active Class must be
  the etch subclass or that dropdown stays greyed out.
- ⛔ **`axlDBCreateShape` does not close the polygon** despite the doc saying it
  does. Repeat the first vertex explicitly; an unclosed path returns bare `nil`
  with the reason printed only to the command window.

---

## 7. Creation and transformation

```skill
axlDBCreateLine( l_points [f_width] [t_layer] [t_netName] )
axlDBCreateVia( t_padstack l_point [t_netName] [?] [f_rotation] )
axlDBCreateSymbol( t_refdes l_anchor [g_mirror] [f_rotation] )
axlSaveDesign( ?noConfirm t )
```

Supply rotations as explicit floats.

### Padstacks

`make_axlPadStackPad` has **no drill fields** despite the doc; the drill
constructor is `make_axlPadStackDrill`. A CIRCLE pad needs both `figureSize`
dimensions.

### axlTransformObject

```skill
axlTransformObject( lo_dbid ?move l_delta ?mirror t/nil/'GEOMETRY
                    ?angle f_angle ?origin l_rotatePoint ?allOrNone t/nil )
```

- The keywords are **`?angle` and `?origin`** — not `?rotate`/`?rotatePoint`.
- **`?angle` is counter-clockwise.** Pass 270.0 for a 90° clockwise turn.
- Order is move, then mirror, then rotate. To rotate about a point and *then*
  translate, use two calls.
- The doc warns that an unsupported transform is **silently ignored**. Read the
  result back.
- Wrap in `axlDBCloak('...)`; it is more efficient for a group and its
  documented side effect is that held dbids go nil, so re-read positions from a
  fresh transaction rather than trusting them.

> **Pick the rotation pivot deliberately.** Rotating a two-pad part about its
> BODY CENTRE swaps the pads and moves nothing else — the part occupies the
> same area, so no clearance changes and no placement check can fail. Rotating
> the same part about its symbol origin (pin 1) swings the body by its own
> length. The first is free; the second made 21 DRCs.

---

## 8. Visibility

```skill
axlVisibleGet()            ; NO arguments; per CLASS, not per layer
axlVisibleLayer("CLASS/SUBCLASS" t/nil)
axlVisibleSet(saved)
axlVisibleUpdate(t)        ; t = redraw now
```

A record looks like:

```
(nil class "ETCH" visible t   subclassinfo nil)
(nil class "ETCH" visible -1  subclassinfo (("BOTTOM" t) ("PWR" nil) ...))
```

`visible` is `t` (all on), `nil` (all off), or **`-1` (mixed)**, and
`subclassinfo` is populated **only when mixed**. A class reading plain `t` with
an empty `subclassinfo` means every subclass is on — not "no information".

Visibility is stored in the `.brd`, so changing a view dirties the design.

---

## 9. Reading the board

⛔ **`design->symbols` and a symbol's `->xy`, `->rotation` and `->bBox` serve
stale values after the GUI has moved something**, with no error and no
indication. An empty transaction forces the refresh:

```skill
axlDBTransactionCommit(axlDBTransactionStart())
```

A checker reporting stale geometry is worse than no checker, because it reads
as confirmation.

Other traps:

- `sprintf` with `%s` on a non-string throws *"format spec. incompatible with
  data"*. `%L` is the safe default — but it returns quoted, and the helper
  escapes those quotes on the way back, so `\"NAME\"` needs the backslash
  stripped as well.
- A symbol's `->bBox` **includes its refdes text**, so it is useless as a body
  extent. Use `PACKAGE GEOMETRY/PLACE_BOUND_TOP`.
- `PLACE_BOUND_TOP` is not the pad extent either — package bounds extend past
  the copper.
- SMD pads exist on the TOP layer **only**. Through-hole pads exist on every
  layer. This is what makes a trace legal directly under a SOIC on an inner
  layer, and what makes a through-hole part an obstacle there.

---

## 10. Verification: what the obvious checks do NOT catch

`drcs` counts spacing violations. `net->unconnected` counts pins unreachable
from the rest of the net. **Both read 0 on a board with serious defects.**

| defect | DRC | unconnected | what does catch it |
|---|---|---|---|
| trace ending in mid-air | 0 | 0 | endpoint check (`dangle_check.py`) |
| trace 0.3 mil short of a pin | 0 | moves, but hides inside an existing backlog | endpoint check, near-miss class |
| duplicate coincident same-net copper | 0 | 0 | object count |
| orphan via adopted by a pour | 0 | 0 | branch with no pins |

Notes on each:

- **Copper going nowhere violates no spacing rule.** A stub that starts on a
  pin and ends in mid-air leaves that pin perfectly connected.
- **A non-zero `unconnected` on a partly-routed net hides new breakage inside
  old.** Record the expected count after every pass; a stale expectation is how
  a broken rail stayed hidden for a day.
- **Duplicate coincident copper is invisible.** Same net, same place — no
  spacing violation, no connectivity change, nothing on screen. The only
  symptom is the object count. Any script that creates copper needs an
  idempotence guard, or it must never be re-run.
- **Deleting a via's clines leaves the via behind**, and a through via sitting
  in a pour is adopted by that pour's net. It then causes DRCs against later
  routing on a net that has nothing to do with it.
- **`nBranches` should equal 1 on a fully routed net.** `unconnected 0` with
  `nBranches 2` means a piece of copper with no pin on it.

### Deleting

Delete by **dbid**, not by coordinate. Allegro splits a cline wherever another
tees into it, so "delete the path ending at (x,y)" can remove a trunk segment
that merely shares that vertex. A whole layer-3 supply trunk was lost that way.

---

## 11. Text, and the silkscreen nobody checks

```skill
axlDBGetAttachedText( o_object )                  ; symbol OR design
axlDBCreateText( t_text l_anchor r_orientation [t_layer] [o_attach] )
```

⛔ **`axlDBGetAttachedText` takes the DESIGN as well as a symbol.** Board-level
text — a title, a revision, a legend — is created with `o_attach` = nil and
hangs off the design. It appears in **no** `design->symbols` walk. A checker
built only on `->symbols` reports a clean board while ignoring every piece of
text a human actually authored.

**`axlDBCreateText` accepts embedded newlines**, and each one becomes a
*separate database object* with its own dbid; line spacing comes from the text
block. The lines run **downward** from the anchor, so anchoring near the bottom
edge puts line 2 off the board.

`axlDBTextBlockFindName` returns `nil` for the numeric block names that text
objects actually report (`tt->textBlock` → `"3"`). Read a working object's
block and reuse it rather than trying to look one up.

### A footprint carries far more text than belongs on silkscreen

Up to five classes — `REF DES`, `DEVICE TYPE`, `COMPONENT VALUE`,
`USER PART NUMBER`, `TOLERANCE` — each instantiable on SILKSCREEN, ASSEMBLY
**and** DISPLAY. Only `REF DES` belongs on silkscreen; the rest are drawing
data and belong on ASSEMBLY, which is not printed.

Measured on a 53-part board: ten parts carried four junk strings each, all
stacked at the same y on top of each other and the pads, the widest **2435 mil
— wider than the board**. Silkscreen is not copper, so this violates no
spacing rule and DRC reads 0 all the way to the fab.

> Keep `PACKAGE GEOMETRY` text when cleaning. The pin-1 marker lives there,
> usually as a bare `*`. Filtering by class rather than by content keeps a
> marker drawn as something else.

### `pin->bBox` is the true pad extent

Unlike `symbol->bBox`, which includes the refdes text and is useless as a body
extent (§9), a **pin's** `bBox` is the pad. Verified against a DD-10 DFN:
65 × 94 mil, matching the datasheet's 1.65 × 2.38 mm exposed pad.

### What a text checker still will not catch

Component body outlines are `path` children on
`PACKAGE GEOMETRY/SILKSCREEN_TOP` — not text and not pads. A check built on
text-vs-pad passes a board title that visibly clips a component outline. On
this board the clip was **4 mil**, caught by a human looking at the screen
after the tool said clean. `symbol->children` reaches the outlines; their
`bBox` overstates an L-shaped path, so treat the result as advisory.

Add to the §10 table:

| defect | DRC | unconnected | what does catch it |
|---|---|---|---|
| 2435-mil part-number string on silkscreen | 0 | 0 | text inventory by subclass |
| refdes text printed across a pad | 0 | 0 | text bBox vs `pin->bBox` |
| board title clipping a component outline | 0 | 0 | text bBox vs silk `path` children |

### Changing text: the attribute is a silent no-op

```skill
tt->textBlock = "3"                  ; returns, changes NOTHING
axlDBChangeText( o_dbid t_text [r_textOrientation | x_textBlock] )
```

Assigning `textBlock` on a text dbid fails silently — no error, and a read-back
still shows the old block. Use `axlDBChangeText(tt nil 3)`: `nil` for the text
keeps the string, and a bare integer changes only the block. Note the block
argument is an **integer**, while `tt->textBlock` reads back as a **string**.

Changing the block changes the text's extent, so any overlap result computed
before the change is void. Re-run the check afterwards.

### Rotating text in place

`axlTransformObject(tt ?angle 180.0 ?origin <centre of tt->bBox>)` flips text
with **zero** movement — verified by a bBox that was byte-identical before and
after. Rotating about the default origin swings it off its anchor instead.
This is the same pivot lesson as §7: choose the pivot, don't accept the
default.

Silk text should read from at most two orientations, 0° and 90°. A board
rotation applied to a part cluster takes its labels 0° → 270° as a side
effect, so a rotation audit is worth running after any group rotate.

### Pin-1 markers are not always text

A library can indicate pin 1 either way, and one library can do **both**:

```
U1..U4   text "*" on PACKAGE GEOMETRY/SILKSCREEN_TOP
U5, U6   a ~10 x 12 mil `path` dot beside pin 1, no text at all
```

Counting the text class alone reported the two DFNs as unmarked. They were
marked; the marker was geometry. Adding a redundant `*` then collided with a
neighbouring part's polarity mark — a defect introduced by trusting a
text-only count. **Check `symbol->children` for paths before concluding a part
has no marker.**

### The menu tree IS readable — from the menu file, not the API

§12.2 says the GUI menu tree is not inferable from the API. It is not
inferable, but it is not unknowable either: it is a plain text file.

```
<CDS_ROOT>/share/pcb/text/cuimenus/orcad.men      OrCAD PCB Designer
<CDS_ROOT>/share/pcb/text/cuimenus/allegro.men    Allegro
```

**The products do not share a menu tree.** `allegro.men` puts the Windows
submenu under `View`; `orcad.men` puts it under `Display`. Quoting the wrong
file at an OrCAD user is how one of the wrong guesses in this project
happened. Read the file the product actually loads.

```
Display -> Windows -> Find          "showhide find"
Display -> Windows -> Visibility    "showhide vis"
Edit    -> Move                     "move"
```

⛔ **The menu file does not describe panel behaviour.** The Find panel's
filter options stay **greyed out unless the tool is in General Edit mode** —
nothing in `orcad.men` says so, and no API call reports it. Reported by the
engineer after the documented path failed to work.

And a caution against sending a human to the GUI at all: with the Find filter
restricted to Text, `Edit -> Move` on a refdes still moved the **parent
symbol**. Whatever the correct interactive incantation is, moving attached
text from the bridge is deterministic and cannot touch the part:

```skill
axlTransformObject( <text dbid> ?move list(dx dy) )
```

Read the bBox back afterwards and it is exact. Prefer it.

### Minor, but it costs a round trip

`t` is a protected symbol and cannot be a loop variable —
`foreach(t list ...)` fails with *"Variable is protected and cannot be
assigned to"*.

---

## 12. Rules that generalise

1. **Look commands up; never guess.** `docs/allegro_skill_index.md` lists 861
   `axl*` functions. Journaling (`SetOptionBool Journaling TRUE` +
   `DisplayCommands TRUE`) shows what the tool itself issues, and solved in one
   attempt what hours of inference could not.
2. **The GUI menu tree is not inferable from the API** and is not in the
   function index. Ask or journal it rather than guessing — two confident
   guesses about menu locations were both wrong.
3. **A success return is not verification.** Read the state back, ideally in a
   session that reopened the file from disk.
4. **Measuring the intent is not measuring the result.** A distance between two
   pads is not the length of the copper between them.
5. **No loop against a live database without an iteration cap.** A repair loop
   that could only terminate on success ran away and issued several hundred
   deletes.
6. **Snapshot the board at milestones.** Allegro keeps no rolling `.brd`
   backup, and a binary that changes on every save does not belong in git.
