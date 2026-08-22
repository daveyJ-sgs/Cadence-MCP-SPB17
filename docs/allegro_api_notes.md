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

### ⛔ NEVER conclude a capability is absent from failed name guesses

Ten guessed `axl3D*` names all returned `nil`, and that was reported as "Allegro
has no scriptable 3D API". **It has 50 of them, under the `v3D*` prefix.** The
nils proved the guesses were wrong, nothing more.

Enumerate instead. Both of these were available the whole time:

```skill
listFunctions("3D")            ; substring match over every bound function
arglist('v3DBatch)             ; => (objList fileName @optional writeFileOnly ...)
getd('v3DBatch)                ; => funobj:v3DBatch
obj->?                         ; field names of any defstruct instance
```

`arglist` is the safe way to map an unknown API: it returns the exact signature
**without calling anything**, so nothing fires a modal dialog at the user or
takes a license. Probing arity by calling with zero arguments is NOT safe — a
zero-argument function will simply run.

`docs/allegro_skill_index.md` in this repo already listed `axlStepGet` /
`axlStepSet` and was never checked. Check the index before claiming absence.

### Do not use `axlDBGetDesign()->name` to test whether a board is open

It reads `nil` **whether or not a design is loaded**, so a nil tells you
nothing. Reading it as "no board is open" produced a wrong conclusion and
deferred a verification step for a day.

```skill
axlDBGetDesign()->name              ; nil even with a board open — useless
length(axlDBGetDesign()->symbols)   ; nil = closed, a count = open
```

⭐ **Probe for something that must be present, and read a count.** A result
that is falsy for two different reasons cannot distinguish them — the same
shape as §5's `"not nil" is not a success test`. `ping` answering is a
statement about the helper, not about Allegro; `->name` is a statement about
nothing at all.

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

### ⛔ `design->drcs` is a cached LIST, and it goes stale too

Converting shapes to dynamic in the GUI left `length(design->drcs)` reporting
**75** on a board that was clean. The list is not refreshed by work done
outside the bridge:

```skill
length(axlDBGetDesign()->drcs)                       ; 75  <- stale
axlDRCUpdate(t)                                      ;  4  <- authoritative
axlDRCGetCount()                                     ;  4
axlDBTransactionCommit(axlDBTransactionStart())      ; flush
length(axlDBGetDesign()->drcs)                       ;  4  <- now agrees
```

**Use `axlDRCGetCount()` for the number**, and flush the transaction before
walking `->drcs` for detail. Counting the length of that list is the obvious
thing to do and it is wrong often enough to matter — every DRC figure in this
repo's earlier notes came from it.

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

### Finding things: three signatures that look right and return nil

```skill
setof(x axlDBGetDesign()->nets x->name == "VCC")    ; nil -- == is not string compare
setof(x axlDBGetDesign()->nets equal(x->name "VCC"))  ; works
```

- **`==` does not compare strings.** It returns nil silently, so a lookup that
  finds nothing looks like "no such object" rather than "wrong operator".
- **A net has no `->pins`.** Its attributes are `(parentGroups branches name
  nBranches objType readOnly prop pinpair ratT ratsnest ... )`. Walk
  `net->branches` then `branch->children` and filter on `objType`.
- **`design->components` exists but carries no `refdes`** — `design->symbols`
  does. A component is reachable as `sym->component`.
- Print an object's attribute names with `obj->?` when a guess fails. It is one
  call and it ends the guessing; `obj->??` returns name/value pairs as a flat
  list, so `mapcar(car ...)` over it errors.

### ⛔ Properties: where they live, and two silent failures

Component properties live on the **component definition**, not the symbol and
not the component:

```skill
sym->component->compdef->prop     ; (VALUE PART_NUMBER PART_NAME)
```

That means **one write per unique part, not per refdes** — and a compdef is
*shared* by every refdes using it, so writing per-refdes will give them all
whichever value went last. Detect that collision before writing.

**Trap 1 — a dbid does not survive a round trip.** Read back over a bridge it
prints as `dbid:000001685B681118`. Sending that text back to SKILL is a parse
error, not a reference to the object. Look the object up again into a SKILL
variable. Code that captured dbids client-side and interpolated them reported
success on every write and changed nothing.

**Trap 2 — `axlDBAddProp` reads back stale.** The write succeeds and the old
value is still there until the transaction is flushed:

```skill
axlDBAddProp(list(cd) list(list("PART_NUMBER" "NEWVALUE")))
  ; => ((dbid:...) nil)          <- this is what success looks like
cd->prop->PART_NUMBER            ; still the OLD value
axlDBTransactionCommit(axlDBTransactionStart())
cd->prop->PART_NUMBER            ; NEWVALUE
```

Two things about that return: **"not nil" is not a success test** — an error
string is also not nil, which is exactly how a broken write passed its own
check. Test that the return is a list headed by a dbid. And note
`compdef->readOnly` is `t` while the write works anyway; that flag is not a
permission check on anything.

### Attributes that only a netlist import can change

`compdef->deviceType` is a composite string built at import time from
footprint, class, value and part number:

```
C_SMC0805_DISCRETE_100N_<partnumber>
```

It is a read-only attribute with no corresponding property, so editing
`PART_NUMBER` leaves it stating the superseded part. It appears in IPC-2581 as
a `DEVICE_TYPE` textual characteristic. **The BOM section is authoritative;
`DEVICE_TYPE` is a label.** Expect it to drift, and say so in a fab README
rather than running an ECO through a finished board to correct cosmetics.

---

## 6. Dynamic shapes

- **Vias trigger the dynamic-shape update; clines do not.** Testing whether a
  pour is dynamic by drawing a cline gives a false negative — three evenings
  were lost to that.
- A **foreign-net** via punches an isolating void. A via on the shape's **own**
  net gets a thermal tie and costs the plane nothing. Measure the void count
  either side of a change; it is the cheapest confirmation available.
- ⛔ **`axlShapeChangeDynamicType` does not convert the shape.** Convert in the
  GUI: `Shape → Change Shape Type`, with
  `Options → Shape Fill → Type = "To dynamic copper"`. The Active Class must be
  the etch subclass or that dropdown stays greyed out.
- ⛔ **A DYNAMIC SHAPE CANNOT BE DELETED FROM THE BRIDGE — however it was made
  dynamic.** This was first recorded as damage done by
  `axlShapeChangeDynamicType`; that was too narrow. A shape converted through
  the GUI resists deletion identically, and so does the documented `'ripup`
  mode:

  ```skill
  axlDeleteObject(axlDBGetShapes("ETCH/PWR"))            ; nil, shapes remain
  axlDeleteObject(axlDBGetShapes("ETCH/PWR") 'ripup)     ; nil, shapes remain
  ```

  It survives save and reload. **Deleting a pour is a GUI action** — plan any
  re-pour around one manual step, and get the geometry right before asking for
  the conversion rather than after.
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

### ⛔ Verifying fab output: count features per layer, not layers

An IPC-2581 export was declared good three separate times — components, BOM
items, nets and layer stackup all correct — and had **one geometry Set per
copper layer**. The board's entire artwork was missing. The tell was in every
one of those checks and never read: `TOP: 1 Set`.

```
                       broken export        real export
TOP                        1 Set              359 Sets
GND                        1                  147
BOTTOM                     1                  155
soldermask              absent                155 / 37
```

**Name the per-item quantity that would be non-zero if the artifact were real,
and measure that.** Features per layer, not layers. A count that is suspiciously
uniform across items — 1, 1, 1, 1 — is broken, not tidy. Cross-check the two
formats against each other: IPC `Polygon` count and Gerber `G36` region count
per layer should tell the same story, and a poured layer with zero of either
has no copper on it.

### ⛔ Both fab formats compress, and a naive grep reports false problems

- **Excellon repeat codes.** `R03X00800` means "three more holes, stepping X".
  A file with 95 coordinate lines can hold 106 holes. Counting coordinate lines
  undercounts — and the drill log states the true total, so reconcile against
  it.

  ⛔ **The step distance depends on the FORMAT declared in the header, and this
  note originally got it wrong by 100x.** With `FORMAT 2.3` (2 integer, 3
  decimal, inches) `X00800` is **0.800 in**, not 0.008 in. The wrong reading
  survived review because 0.008 in "looked like a plausible small number" —
  and it is not plausible at all: an 8 mil step with a 10 mil drill would be
  overlapping holes. **Sanity-check a decoded coordinate against physical
  reality before trusting your decode**, and read `FORMAT` from the log rather
  than assuming the common 2.4.
- **Gerber omits repeated coordinates.** `Y380000D03*` inherits X from the line
  above. Grepping for a full `X…Y…` pair finds some flashes and silently misses
  others, which reads as missing geometry.

Both of these produced a confident "this is broken" report about output that
was correct. **Read the format before believing a grep.**

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

---

## 12. Padstacks — and the one change the API will not make

A vendor rejected a fab package for having no board outline. Auditing the rest
of it found something worse: **14 connector pads with copper, a drilled hole,
and `NULL` soldermask on both sides.** The board's entire audio I/O and its
mains input would have arrived sealed under mask. The defect was in four
padstacks that came from a vendor footprint model.

### Where the defect lives, and how to see it

```skill
sym->component->compdef        ; padstacks are shared by every pin that uses them
padstack->pads                 ; one entry per layer per pad TYPE
pad->layer                     ; "ETCH/TOP", "PIN/SOLDERMASK_TOP", ...
pad->figureName                ; NULL means nothing is plotted on that layer
```

⛔ **Counting mask layers is not checking them.** Every padstack on that board
reported `mask=2 paste=2` — the layer entries all existed. Four of them had
`figureName` = `NULL`, which produces no opening at all. **Read the figure, not
the layer count.**

`TVIA10A`-style tented vias legitimately have NULL mask, so this cannot be a
blanket rule — compare against the padstack's own copper: **copper present with
mask NULL is the defect.**

### ⛔ `axlPadstackEdit` cannot fix it

> "Currently only global padstack settings are supported. We currently do not
> allow editing pad layer characteristics."

Which is precisely the thing that has to change. It edits usage, drill, hole
type — not what is on a layer.

### ⛔ `axlReplacePadstack` is the wrong tool too

Its first argument is a list of **pin/via dbids**, not a padstack name — pass a
name and it returns `nil` with no error, because "nothing in the list was a pin
or a via". Worse, the doc warns:

> "Will not change symbol definition pins."
> "Changing the padstack on a pin ... will result in an exploded pin."

So for pins that come from a footprint it is both ineffective and messy.

### ✅ The route that works: create, dump, refresh

The doc's own performance hint points at it — *"if you want to change all
instances of a particular padstack it will be faster to change the padstack
itself"*:

```skill
; 1. build a corrected padstack. Mask layers ARE supported here.
padList = list(
    make_axlPadStackPad(?layer "TOP"            ?type 'REGULAR ?figure 'CIRCLE ?figureSize 166.54:166.54)
    make_axlPadStackPad(?layer "SOLDERMASK_TOP" ?type 'REGULAR ?figure 'CIRCLE ?figureSize 166.54:166.54))
drl = make_axlPadStackDrill(?usage "Through" ?holeType 'CIRCLE_DRILL
                            ?plating 'PLATED ?drillDiameter 111.02)
axlDBCreatePadStack("MYPAD_SM" drl padList t)      ; => dbid

; 2. write it over the library original
axlPadstackToDisk("MYPAD_SM" "MYPAD")             ; => t

; 3. GUI: Tools -> Padstack -> Refresh...   (takes a .lst of names)
```

Notes that cost time:

* ⛔ **A created padstack does not appear in `design->padstacks` until the
  transaction is flushed.** `axlDBCreatePadStack` returns a dbid, the object
  exists, and a lookup by name finds nothing — 25 before the flush, 26 after.
  Same shape as `axlDBAddProp`. Flush, then verify.
* **`axlDBCreatePadStack` returns `nil` on a duplicate name**, so a re-run
  after a partial pass looks like a failure. Make the script idempotent.
* **`axlPadstackToDisk` writes to the current working directory.** `padpath`
  starts with `.`, so the new file shadows the library original — convenient,
  but check where it landed.
* ⛔ **`axlRefreshSymbol` does NOT refresh padstacks.** It returns a dbid,
  looks like it worked, and the pad layers are unchanged. Its own doc says the
  padstack options are "done at the padstack level not the symbol level".
* **`axlLoadPadstack` will not reload from disk either** — it returns the
  existing database copy and only falls back to the library if the name is
  absent.
* **Refresh only what you intend.** "Refresh all" re-reads every padstack from
  the library, and any padstack built in-session has no file to read. Use a
  `.lst` of names — plain text, one per line.
* **`axlPurgePadstacks('padstacks nil)`** removes the unused originals
  afterwards. It needs both arguments; called bare it errors.

### Paste on a through-hole pad, and 1 mil apertures

The same audit found paste apertures equal to the copper pad on eight
through-hole padstacks — the stencil printed paste into 30 drilled holes,
including a mains screw terminal and a laminated transformer, neither of which
can go through reflow. **Correct paste for a through-hole pin is none**; omit
the PASTEMASK layers when building the replacement.

And both leadless thermal pads carried a **1.0 x 1.0 mil** paste aperture
against a 65 x 94 mil pad — 0.02% of the area. A padstack holds one figure per
layer, so a true window-pane needs a shape or flash symbol; a single aperture
at ~50% of pad area is the practical fix and is inside normal guidance.

---

## 13. Two more traps found the same day

### ⛔ `t` is a reserved SKILL variable name

```skill
setof(t design->text ...)                 ; *Error* t is reserved
mapcar(lambda((t) t->text) ...)           ; same
```

The error is clear when you read it, but it arrives inside a long expression
and reads as "the query is wrong" rather than "the loop variable is illegal".
Use any other name.

### ⛔ Batch NC output silently falls back to defaults

`nctape` reads `nc_param.txt` found via `NCDPATH`, which is `. ..` — relative
to **where the tool runs**, not to the design. A build script that copies the
board somewhere else and runs there gets defaults, and says so only in the log:

```
WARNING(SPMHMF-325): No NC Parameters file found ... using defaults
```

The defaults produced a drill file with **no `M48` header, no units, and no
tool codes** — 106 bare coordinates that a standard parser reads as a single
tool. It shipped to a vendor. Copy `nc_param.txt` alongside the board, and
fail loudly if it is missing rather than letting the warning scroll past.

The file is plain text and Allegro writes it from **Export → NC Parameters**.
`ENHANCED_EXCELLON YES` gets the `M48`/`INCH`/`%`/`M30` wrapper; **`TOOL-SELECT
YES` is what emits the `T` codes** and is not exposed in that dialog — edit the
file.

---

## 14. Screenshots, colour, and four ways to kill the bridge

A morning spent getting one clean board image produced more traps than the
image was worth. Most of them are not about images at all.

### NEVER: `arglist` and `boundp` need a QUOTED symbol

SKILL keeps function and variable bindings in **separate namespaces**. These
look like proof that a function does not exist, and are not:

```skill
arglist(axlShell)     ; *Error* eval: unbound variable - axlShell
boundp('axlShell)     ; nil    -- checks the VARIABLE binding
axlShell("...")       ; works fine, it was always there
```

Correct form:

```skill
arglist('axlShell)    ; (t_string "t")
getd('axlShell)       ; lambda:axlShell  -- nil means NOT LOADED
```

A dozen functions were written off as "unbound" from the first spelling.

### Autoload stubs: named but not loaded

`listFunctions` reports names the session has never loaded. For those,
`getd('name)` is `nil` while `arglist('name)` still returns the **arity** --
with the argument names stripped if the code is compiled:

```skill
arglist('SOME_COMPILED_Run)   ; (arg arg arg arg)  -- four args, no names
```

Arity without names is not enough to call something safely. Four positional
arguments of unknown type and order is a guess, not an API.

### NEVER: `listFunctions` takes a REGEX, and it needs a literal first character

```skill
listFunctions("*Plot*")          ; *Error* rexMatchList: Empty closure
listFunctions("axl.*[Pp]lot.*")  ; works
```

A leading `*` is not a wildcard here, it is invalid regex.

### NEVER: `axlShell` returns `t` for a command that does not exist

```skill
axlShell("tbx svgexport")   ; => t
```

`t` means *the string was accepted*, not *the command ran*. The journal is the
record:

```
allegro.jrl:  (00:25:07) Command not found: tbx svgexport
```

**Check `allegro.jrl` after any `axlShell`.** Same family as `axlDBAddProp`
returning a non-nil error string, and as the `->color` write below.

### NEVER: a modal dialog freezes the bridge completely

The SKILL side receives data through an `ipcBeginProcess` data handler, and
those callbacks **only fire when Allegro is idle**. Any modal dialog -- a file
save box, a form -- stalls the relay until it is dismissed. The helper then
reports `__TIMEOUT__ no response from SKILL`.

Diagnosis without the bridge, typed at the `Command:` prompt:

```
skill abStatus()      ; child=ipc:1 port=9030 alive=t
```

If that answers, SKILL is healthy and only the relay is stalled.

### NEVER: one line per exchange -- a large response desyncs the channel for good

Enumerating the whole symbol table letter by letter returns **thousands of
names on a single line** (~13,800 symbols total). It succeeded once and timed
out on the second attempt, and every call after that was dead -- a
half-consumed response leaves the framing out of step permanently.

Recovery, one line at a time at the `Command:` prompt:

```
skill abStop()
skill abStart()
```

Filter in SKILL and return a count or a short list. Do not stream the symbol
table across a line-framed channel.

---

### Getting an image out: three routes, and which one is licensed

| Command | Availability | What it produces |
|---|---|---|
| `tbx svgexport` | GATED behind `_allegro_option_prodtoolbox` / `_orcad_option_prodtoolbox` | vector SVG, fully profile-driven |
| `pdf out` | available | **film-based** -- one page per artwork film, not the canvas |
| `capture image` | available | canvas grab, full colour, honours the current view |

`capture image` is the one to use for a picture of the board. `pdf out` looks
right until you read `pdf_out.form` and see it is driven by an *Available
Films* tree.

The SVG exporter's profile format is worth knowing about even though it is
gated -- `share/pcb/toolbox/config/svgexport/*.profile` defines image size,
background, per-group layer sets, colours and opacity. The code itself lives
compiled in `share/pcb/etc/context/64bit/toolbox.cxt`.

### Form field names are on disk

```
<CDS_ROOT>/share/pcb/text/forms/*.form
```

and menu entries show the syntax for driving a form without a human:

```
done;place manual;setwindow form.plc_manual;FORM plc_manual library YES
```

NEVER assume this covers every dialog. It works for Allegro FORMs. A native
Windows file-save dialog is **not** a FORM and has no field names --
`capture image` ends in one, so it cannot be fully scripted this way.

### NEVER: the file extension is not the format

`capture image` wrote a **BMP** with PNG selected in the Files-of-type
dropdown; the format appears to follow a typed extension, not the filter.
Verify with something that reads the header rather than the name.

---

### Colour: the palette is writable, the layer's index is not

```skill
axlLayerGet("ETCH/TOP")->color        ; => palette INDEX, e.g. 57
axlColorGet(57)                       ; => (38 255 38)   INDEX in, RGB out
axlColorSet(57 list(240 170 60))      ; writes the PALETTE ENTRY
axlColorSave("f.color") / axlColorLoad("f.color")
```

NEVER pass a layer name to `axlColorGet`. It takes an **index**.
`axlColorGet("ETCH/TOP")` returns `nil`, which reads like "no colour" and
means "wrong argument type".

NEVER trust a `->color` assignment. **The per-layer colour index is
read-only.** The assignment returns the value you assigned, which looks
exactly like success:

```skill
axlLayerGet(lay)->color        ; 24
axlLayerGet(lay)->color = 100  ; => 100
axlLayerGet(lay)->color        ; still 24
```

NEVER edit a palette entry without checking who else uses it. **Layers share
indices.** On a stock 4-layer setup one index was shared by the bottom etch
layer, the design outline, and both silkscreen classes -- so those four cannot
be given different colours from SKILL at all. Map the indices first and look
for collisions before writing anything.

`axlColorSave` writes only the 192-entry palette -- it does **not** record
which layer uses which index, so it is a restore path for colours and nothing
more. There is no transparency API.

### Layer priority controls draw order

```skill
axlLayerPriorityGet("ETCH/TOP")      ; 0 on a design that has never set one
axlLayerPrioritySet("ETCH/TOP" 5)    ; higher number draws on top
```

Default is `0` for everything, which means opaque plane pours paint over the
routing. This is display state in the `.brd`, same as visibility.

### Enumerating subclasses properly

```skill
axlSubclasses("ETCH")            ; ("TOP" "GND" "PWR" "BOTTOM")
axlColorOnGet("CLASS/SUBCLASS")  ; t / nil, per subclass
```

Use these when a class-level `visible` reading is doing the deciding. Section
8 is right that `t` means all-on, but a class summary read at the wrong moment
is still a summary -- enumerate the subclasses and ask each one.

### Framing a view

```skill
axlDBGetDesign()->bBox                  ; the DRAWING extent -- not the board
axlDBGetDesign()->designOutline->bBox   ; the board outline
axlZoomBbox(bbox)                       ; returns the view it actually used
```

NEVER frame to `design->bBox`. It is the drawing sheet, typically a large
round number that has nothing to do with the board. Also note **symbols can
overhang the board outline** (edge-mounted connectors routinely do), so fit to
the union of the outline and every symbol `->bBox`, not to the outline alone.

`axlZoomFit` needs a bBox argument; there is no zero-argument form.

### Inventory of a footprint's geometry

```skill
mapcar(lambda((c) sprintf(nil "%s@%s" c->objType c->layer)) sym->children)
;; => ("text@REF DES/SILKSCREEN_TOP" "shape@PACKAGE GEOMETRY/PLACE_BOUND_TOP"
;;     "polygon@PACKAGE GEOMETRY/SILKSCREEN_TOP" ...)
```

NEVER write `c->layer->name`. `c->layer` is **already a string**, and the
chained form errors with `get/getq: first arg must be either symbol, list,
defstruct or user type`.

This answers "is there more detail available for this part, or is the outline
all there is" as a fact rather than an opinion -- and it also explains
connector bodies that look broken on screen: some footprints draw the body as
several **open paths** rather than a closed polygon, and the gaps are in the
footprint, not the renderer.

---

## 15. Rules that generalise

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
7. **When a rule is discovered through one route, test whether it is wider
   than that route.** "`axlShapeChangeDynamicType` makes a shape undeletable"
   sat here for days. The real rule is that *any* dynamic shape is undeletable
   from the bridge — the function was incidental, and blaming it meant the
   workaround (convert in the GUI) looked safe when it was not.
8. **A cached list is not a live query.** `design->drcs` and any other
   collection read off the design can lag work done in the GUI. Prefer a
   function that computes (`axlDRCGetCount()`), or flush a transaction first.
9. **A smaller artifact is not automatically a worse one.** Diff the file list
   before believing a size change. A fab package that shrank 7x had gained
   copper and lost only two copies of the design database.
10. **An error that names a symbol may be about how you asked, not whether it
   exists.** `arglist(foo)` reports *unbound variable* for a function that
   works perfectly, because functions and variables are different namespaces
   and it wanted `arglist('foo)`. Several APIs were declared missing this way
   before the quote was tried. Distinguish "absent" from "asked wrong".
11. **Ask a channel for less than it can carry.** A line-framed relay does not
   fail loudly on an oversized response; it desynchronises and every later
   call dies. Filter on the SKILL side and return a count or a short list.

---
