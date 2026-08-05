# Design release checklist

Run before sending a board to a vendor. Not a generic checklist — **every item
here exists because a check passed while the thing was broken.** The failure
mode is never "we forgot to look", it is "we looked at the wrong number."

## The three questions that catch most of it

1. **What is this number measured against?** A centroid file was self-consistent
   and referenced the symbol origin instead of the body centre. 35 of 40 SMT
   parts would have been placed half a body out.
2. **Am I checking what is present, or what is required?** A fab package
   verified feature counts across eleven films and had no opinion about a
   twelfth that was absent. The board outline shipped missing.
3. **Is this a live query or a cached value?** A DRC count read 75 on a clean
   board because the list had not refreshed.

---

## 1. Schematic and BOM

- [ ] **Both part-number properties written**, not just the one the BOM report
      reads. In Capture, `Part Number` feeds the BOM and CIS while `PART_NUMBER`
      feeds the netlist and therefore the board. They drift silently.
- [ ] **Values agree with part numbers.** A resistor whose value string still
      says the old resistance passes every check that only tests for non-blank.
- [ ] **Verified by reading back from a REOPENED file.** A property write can
      return OK, the save can return OK, the file timestamp can advance, and
      the value can still be lost. Close the project, answer *Save All* at the
      prompt, reopen, then re-read.
- [ ] **The board's copy matches the schematic's.** The board keeps its own
      part numbers from the last netlist import; the fab BOM exports from the
      board, not from the schematic.
- [ ] Every unconnected pin is intentional and known (an EDA tool may assign
      unconnected pins internal unique nets, so a naive "is it connected" test
      reports zero problems).

## 2. Sourcing — check before layout freezes, not after

- [ ] **Every part number resolves at a distributor as typed.** Missing hyphens,
      absent `/NOPB`-style suffixes, and `#` characters that break CSV upload
      are all silent until an order fails.
- [ ] **Lifecycle status on every line**, not just the expensive ones. Whole
      families go obsolete at once — check the siblings before assuming a
      suffix change rescues you.
- [ ] ⛔ **"In stock: 3000" may be a factory MINIMUM, not shelf stock.** Read
      the minimum order quantity and the lead time, not the number next to the
      part.
- [ ] ⛔ **A distributor's SUBSTITUTE list matches electrical parameters and
      ignores footprint.** Check lead pitch yourself, every time. Seven
      suggested replacements for one obsolete part were all the wrong pitch.
- [ ] **Second source exists** for anything single-sourced, or the risk is
      accepted deliberately.
- [ ] Attrition is the **assembler's** requirement. Do not carry spares of
      expensive through-hole parts into a build you are assembling yourself.

## 3. Layout and copper

- [ ] **DRC from a live query**, not a cached collection, and understood
      violation by violation. Intentional ones are documented for the vendor.
- [ ] **Every net single-branch** with zero unconnected. `nBranches > 1` with
      `unconnected 0` means copper with no pin on it.
- [ ] **No dangling copper.** A stub that starts on a pin and ends in mid-air
      violates no spacing rule and leaves the pin connected.
- [ ] **No duplicate coincident same-net copper.** Invisible to DRC,
      connectivity and the screen; only the object count shows it.
- [ ] **No orphan vias.** Deleting a via's traces leaves the via, and a pour
      will adopt it.
- [ ] **Every conductor layer carries what it should.** Count features per
      layer. A layer that exists and is empty is a layer you paid for.
- [ ] **Poured planes are dynamic, filled, and not out-of-date**, with a void
      count that makes sense.
- [ ] **Copper balance** across layers — a near-empty inner layer against a
      solid one is a lamination warp risk a fab will query.
- [ ] **High-voltage / mains clearance enforced by a constraint class**, not by
      where parts happen to sit. A measured distance is not an enforced rule.
- [ ] **Mounting holes**: plated or not by intent, and net assignment
      deliberate.

## 4. Silkscreen — invisible to DRC

Silkscreen is not copper and violates no spacing rule. A board can be DRC-clean
with unusable silkscreen.

- [ ] Text does not sit over pads.
- [ ] Text does not clip **component outlines** (a pad-only check misses this).
- [ ] Text does not overlap other text.
- [ ] No refdes upside down or mirrored.
- [ ] Font sizes consistent — new parts from an ECO arrive with library
      defaults.
- [ ] Every part is labelled.
- [ ] Pin-1 markers present, and **not duplicated** — a library may mark pin 1
      with geometry where you assumed text, so adding one creates two.
- [ ] Polarity marks on every polarized part.
- [ ] Non-printable clutter removed.

## 5. Fab output

- [ ] ⛔ **Every REQUIRED film exists.** Keep an explicit list and check
      membership before checking content. Counting features in the films that
      exist will never report one that is absent.
- [ ] **Board outline / profile film present**, closed, correct finished size,
      and the README states whether to route to the centreline.
- [ ] **Features per layer are non-trivial.** A uniform count across layers —
      1, 1, 1, 1 — is broken, not tidy.
- [ ] **Every poured layer has fill regions** in the artwork, not just in the
      database.
- [ ] **Drill count reconciles against the tool's own log.** Beware format
      compression: Excellon repeat codes and Gerber's omission of repeated
      coordinates both make a naive count wrong.
- [ ] **Image polarity of every film stated** (positive vs negative), especially
      internal planes.
- [ ] **Undefined line width is non-zero** on every film, or zero-width objects
      like stroke text get no aperture and vanish.
- [ ] **Output domains passed explicitly** where the API allows them to default
      — a film in no domain is silently excluded from every export.
- [ ] **Deliverable contains no CAD database, no duplicate archives, no build
      logs.** Diff the file list rather than judging by archive size.
- [ ] **Archive integrity checked** and the package opens.

## 6. Assembly data

- [ ] ⛔ **Centroid file uses the BODY CENTRE, not the symbol origin.** Measure
      the delta per part and print it. One library placed the origin on pin 1 —
      42 mil on an 0805, which is more than half the body length. ICs were
      correct, so a spot check passed.
- [ ] **Rotation convention stated explicitly.** IPC-7351 puts pin 1 upper-left
      for multi-pin packages and on the left for two-terminal polarized parts;
      IEC since 2009 puts it lower-left — **180° apart.** Verify per package
      type and say which standard the file follows.
- [ ] **SMT / through-hole split correct**, and leadless packages (QFN, DFN,
      BGA) declared. Understating them buys a quote that changes at DFM.
- [ ] **BOM line count checked against vendor quickturn limits** — eligibility
      is often set by line-item count, not board complexity.
- [ ] **Fiducials** present, or their absence raised with the vendor.
- [ ] Coordinates referenced to a stated datum (usually the outline's
      lower-left), in stated units.

## 7. What the vendor is told

- [ ] Layer map, one line per file.
- [ ] Image polarity, and that planes are positive if they are.
- [ ] Board outline convention and finished size.
- [ ] Rotation convention (IPC vs IEC).
- [ ] Any hazardous voltage on the board and the clearance that must not be
      reduced.
- [ ] **Intentional DRC violations named**, so they are not "corrected".
- [ ] Any known-stale metadata that is not authoritative.
- [ ] Parts consigned or turnkey, stated explicitly.
- [ ] **Package revision stamped in the README and the filename**, with what
      changed and what it supersedes. Multiple packages will go out.

## 8. Process discipline

- [ ] **Snapshot before any destructive or hard-to-reverse change.** The CAD
      tool keeps no rolling backup and a binary that changes every save does
      not belong in version control.
- [ ] **A success return is not verification.** Read the state back.
- [ ] **When a rule is discovered through one route, test whether it is wider
      than that route.** Blaming one function for a behaviour that belongs to a
      whole object class makes the workaround look safe when it is not.
- [ ] **Read the file format before believing a grep.** Compressed coordinates
      and repeat codes produce confident false reports.
- [ ] **A new revision goes to everyone already quoting**, not just the vendor
      who found the problem.
