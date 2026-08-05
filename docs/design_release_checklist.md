# Design release checklist

Two documents in one, deliberately:

- **Part 1 — the release gate.** What must be true and what must exist before a
  board goes to a vendor. Ordinary, and none of it is optional.
- **Part 2 — the traps.** Checks that *passed while the thing was broken* on a
  real board. These are not general practice; they are specific false negatives
  and each one shipped.

⛔ **Part 2 is not a substitute for Part 1.** An earlier version of this file
contained only the traps, and you could tick every line and still ship a board
with no stackup, no paste apertures on an exposed pad, and creepage never
computed. Ticking Part 2 alone means "the failures we already know about did
not recur", nothing more.

## Three questions that generate most of the list

1. **What is this number measured against?** The datum question. Covers
   centroid origin vs body centre, rotation zero *and sign*, drilled vs
   finished hole size, clearance vs creepage.
2. **Am I checking what is present, or what is required?** Membership before
   content. Counting features in the files that exist will never report a file
   that is absent.
3. **Who else has to agree with this number?** Every number in a release exists
   in at least two places — the fab, the assembler, the enclosure, the
   schematic — and the failure mode is disagreement.

## How to use it

Record the **observed value**, not a tick. "106 holes, agrees with ncdrill.log"
is evidence; a checkmark is not. Anything that cannot be expressed as an
observed value is not yet a check — fix the wording or drop the line.

---

# PART 1 — RELEASE GATE

## 1.1 Documents that must exist

Films and a drill file are not a release package.

- [ ] **Stackup drawing** — layer order, dielectric thicknesses, copper weight
      inner and outer, core/prepreg construction, material and Tg, finished
      thickness and tolerance. A fab that has to guess will guess.
- [ ] **Controlled impedance specified, or explicitly waived**, and whether the
      fab may adjust trace widths to hit it.
- [ ] **Fab drawing** — hole table (plated/non-plated, **finished** vs drilled
      size, tolerance), board outline with dimensions, material and finish
      notes, IPC-6012 class.
- [ ] **Assembly drawing** — refdes, polarity and pin-1 marks, side, any
      hand-assembly or DNP notes.
- [ ] **IPC-6012 / IPC-A-610 class stated (2 vs 3).** Changes price and the
      definition of "acceptable".
- [ ] **Bare-board test netlist** (IPC-D-356) supplied, and E-test confirmed as
      in the quote. An inner-layer open is invisible until assembly.
- [ ] **Schematic PDF**, frozen at this board revision.
- [ ] **README** with the layer map and every convention below.
- [ ] **Revision stamped in the README and the filename**, with what changed
      and what it supersedes. ⛔ **Once a package is sent it is immutable** —
      issue a new revision, never edit in place. A new revision goes to
      *everyone* already quoting, not only the vendor who found the problem.

## 1.2 Fabrication data

- [ ] **Board outline / profile film present**, closed, correct finished size,
      route-to-centreline stated. Cutouts and slots present or their absence
      stated.
- [ ] **Copper-to-edge pullback** on every layer, planes included.
- [ ] **Annular ring, drill-to-copper, hole-to-hole** meet the fab's class.
- [ ] **Aspect ratio** (board thickness ÷ smallest drill) inside the fab's
      capability.
- [ ] **Drilled vs finished hole size** — plating shrinks a plated hole by
      roughly 4 mil. Mechanical clearance holes are specified as *finished*.
- [ ] **Solder mask**: expansion value, NSMD vs SMD pads, **sliver check** (webs
      below the fab's minimum are removed, joining two openings — invisible to
      DRC, bridges fine pitch), mask pull-back from the edge, colour.
- [ ] **Via treatment decided and stated** — tented, plugged, open, or
      filled-and-capped.
- [ ] **Paste layer**: apertures present only where parts are, and **exposed
      thermal pads window-paned** to roughly 50–70% area. A solid aperture on a
      large pad floats the part and opens the peripheral joints.
- [ ] **Image polarity of every film** stated, planes especially.
- [ ] **Bottom-side films emitted with correct mirroring.**
- [ ] **Format and units headers correct** on Gerber and Excellon.
- [ ] **Panelisation**: V-score vs tab-route, rails, tooling holes, minimum
      board size, part-to-edge keepout, who depanels. Many assemblers require
      rails — and rail fiducials — when the board itself has none.
- [ ] **Acid traps, copper slivers and acute angles** checked; default
      constraint sets do not catch them.
- [ ] **Surface finish** stated (ENIG / HASL / OSP). Matters for leadless
      coplanarity and shelf life.
- [ ] ⛔ **Open the released files in an independent viewer and look at them.**
      Every other item here is a count. A human eye caught a 4 mil silkscreen
      clip on this project after the tooling reported clean.

## 1.3 Assembly data

- [ ] **Centroid uses the component BODY CENTRE.** See trap 2.1.
- [ ] **Rotation convention fully stated**: zero orientation, **sign — is
      positive CW or CCW**, datum corner, units. Naming a standard is not
      enough and is not what the machine needs.
- [ ] **Counts reconcile**: BOM populated quantity ↔ centroid rows ↔ assembly
      drawing refdes. **DNP parts handled explicitly** in all three.
- [ ] **Leadless packages declared** (QFN/DFN/BGA). Understating them buys a
      quote that changes at DFM.
- [ ] **Fiducials**: three global, non-collinear, mask-opened on bare copper,
      plus local fiducials for fine-pitch and leadless — or their absence
      raised with the assembler.
- [ ] **BOM line count against the vendor's quickturn limits** — eligibility is
      often set by line-item count, not board complexity.
- [ ] **Consigned or turnkey stated.** If consigned: cut tape with adequate
      leader, ESD packaging, MSL dry-pack intact, floor life and bake
      requirements understood.

## 1.4 Electrical and physical design

- [ ] **Return path**: no trace crosses a plane split or runs over a gap in its
      reference plane. Highest-value EMC check and the cheapest to automate.
- [ ] **Current density / trace width** per IPC-2152, and via current.
- [ ] **Power dissipation and junction temperatures** for regulators and
      drivers.
- [ ] **Thermal relief on plane-connected through-hole pins.** A direct plane
      tie is effectively unsolderable by hand and hard even for wave.
- [ ] **Decoupling** present at every supply pin that needs it, with a short
      return.
- [ ] **Mechanical fit**: mounting holes vs enclosure, copper and component
      keep-out for screw heads and standoffs, connector positions against the
      panel, tallest-component clearance.
- [ ] **Board revision marked on the board itself** in silk or copper, so a
      bare board can be identified in hand.

## 1.5 Safety — where any hazardous voltage is present

The only category that can injure someone. One spacing rule does not cover it.

- [ ] **Working voltage, pollution degree, material group / CTI, and the
      standard the numbers come from**, all written down.
- [ ] **Creepage and clearance treated separately.** A copper-to-copper spacing
      constraint enforces neither correctly.
- [ ] **Isolation barrier** covers the connector body and the transformer
      primary-to-secondary, not just traces — and no inner-layer plane passes
      under the barrier.
- [ ] **Slots** where creepage cannot otherwise be met.
- [ ] **Fusing** on the hazardous side.
- [ ] **Barrier marked on the silkscreen** so nobody probes across it.

## 1.6 Sourcing — do this before layout freezes, not after

- [ ] **Every part number resolves at a distributor as typed.** Missing hyphens,
      absent lead-free suffixes and `#` characters that break CSV upload are
      silent until an order fails.
- [ ] **Lifecycle status on every line**, and on the siblings — whole families
      go obsolete together, so a suffix change may not rescue you.
- [ ] ⛔ **"In stock: 3000" may be a factory MINIMUM.** Read the MOQ and the
      lead time, not the number beside the part.
- [ ] **Second source exists, or the risk is accepted and recorded where the
      next person will see it.**
- [ ] **Attrition is the ASSEMBLER's requirement.** Do not carry spares of
      expensive through-hole parts into a build you assemble yourself.
- [ ] **RoHS / REACH** declaration if the board will ever be sold.
- [ ] **ESD protection** at externally exposed connectors.

---

# PART 2 — TRAPS

Each of these passed a check while broken.

## 2.1 The centroid measured against the wrong origin

⛔ **Use the body centre, not the symbol origin, and print the delta per part.**
One library placed footprint origins on pin 1 — 42 mil on an 0805, more than
half the body length. The ICs were correct, so a spot check passed. 35 of 40
SMT parts would have been placed half a body out.

## 2.2 Checking what is present instead of what is required

⛔ **Keep an explicit list of required films and check membership BEFORE
content.** A verifier counted features across eleven films, passed, and had no
opinion about a twelfth that was absent — the board outline. A vendor found it.

Generalise it: the same question applies to the document list in §1.1.

## 2.3 A layer that exists and is empty

⛔ **Count features per layer.** A four-layer board shipped twice with one
conductor layer carrying eight trace segments and no pour. Component, BOM, net
and stackup counts were all correct. The tell was `1 Set` per layer, present in
every report and never read. **A count that is uniform across items — 1, 1, 1,
1 — is broken, not tidy.**

## 2.4 A success return that did nothing

⛔ **Read the state back from a file reopened from disk.** A property write
returned OK, the save returned OK, the timestamp advanced, and the values were
lost. Also: an API "success" that is merely *not nil* is not a success test —
an error string is also not nil.

## 2.5 Two properties where you assumed one

⛔ In this CAD pair, the BOM report and the netlist read **different**
part-number properties, and the board keeps its own copy from the last netlist
import. Three places, drifting silently. The fab BOM exports from the board.

## 2.6 Believing a grep instead of the file format

⛔ **Decode per the format declared in the header, then sanity-check the result
against physical reality.** Excellon repeat codes and Gerber's omission of
repeated coordinates both make naive counting wrong — and a decode error here
was itself missed because the wrong answer looked like a plausible small
number. It was not plausible: it implied overlapping holes.

## 2.7 Silkscreen, which DRC cannot see at all

Not copper, violates no spacing rule. A board can be DRC-clean with unusable
silkscreen.

- [ ] Text not over pads.
- [ ] Text not clipping **component outlines** — a pad-only check misses this.
- [ ] Text not overlapping other text.
- [ ] No refdes upside down or mirrored.
- [ ] Font sizes consistent; ECO parts arrive with library defaults.
- [ ] Every part labelled.
- [ ] Pin-1 markers present and **not duplicated** — a library may mark pin 1
      with geometry where you assumed text.
- [ ] Polarity marks on every polarized part.

## 2.8 Copper that connectivity checks cannot see

- [ ] **No dangling copper.** A stub from a pin to mid-air leaves the pin
      connected and violates nothing.
- [ ] **No duplicate coincident same-net copper.** Invisible to DRC,
      connectivity and the screen; only the object count shows it.
- [ ] **No orphan vias.** Deleting a via's traces leaves the via, and a pour
      adopts it.
- [ ] **Every net single-branch, zero unconnected** — *with a stated exception
      list*: single-pin nets, deliberate no-connects, mounting-hole nets, and
      pins the tool assigned internal unique nets. Without the exceptions this
      fires falsely and then gets ignored.

## 2.9 Substitute lists that ignore the dimension you care about

⛔ A distributor's substitute list matches catalogue package codes but **does
not pin down dimensional detail within a package family** — radial lead pitch,
can diameter and height, connector mating geometry, TO-220 isolated or not.
Seven suggested replacements for one obsolete radial were all the wrong lead
pitch. **Measure the footprint and check the pitch yourself, every time.**

## 2.10 Tool-specific traps that are easy to restate wrongly

- [ ] **Artwork matches the database.** (Stated this way, not as "the pour is
      dynamic" — that is an implementation detail; a correctly filled and
      voided static shape ships fine.)
- [ ] **Undefined line width set below your smallest intentional line width**,
      and never zero — zero-width objects such as stroke text get no aperture
      and vanish. Do not copy a number from another project.
- [ ] **Output domains passed explicitly** where an API lets them default: a
      film belonging to no domain is silently excluded from every export.
- [ ] **A cached collection is not a live query.** Prefer a function that
      computes over a list read off the design.
- [ ] **When a rule is found by one route, test whether it is wider.** Blaming
      one function for behaviour belonging to a whole object class makes the
      workaround look safe when it is not.

---

# PART 3 — Which tool answers which line

Scripts in this repo and the board's automation directory:

| tool | covers |
|---|---|
| `verify_bom.py` | §1.6 part numbers, 2.4 durability, 2.5 both properties |
| `board_partnums.py` | 2.5 — board copy vs schematic |
| `place_check.py` | §1.4 mechanical fit, keepin margins, part overlap, mains distance, channel symmetry |
| `dangle_check.py` | 2.8 dangling copper, orphan vias |
| `silk_check.py` | 2.7 entire section |
| `pour_pwr.py --coverage` | plane coverage scoring before pouring |
| `make_cpl.py` | 2.1 centroid, and prints the origin-to-centroid delta |
| `build_fab.py` | 2.2 required films, 2.3 features per layer, drill reconciliation |
| `snapshot.py` | milestone copies before destructive change |
| `layer_view.py`, `text_view.py` | visual inspection per layer |

**Nothing here answers §1.1, §1.2's mask/paste/panel items, §1.4's return-path
and thermal work, or §1.5 at all.** Those are manual or unbuilt — which is
exactly why they are the items most likely to be skipped.
