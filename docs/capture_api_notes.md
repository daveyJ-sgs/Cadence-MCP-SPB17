# OrCAD Capture `Dbo*` API — field notes

Hard-won behaviour of Capture's TCL/SWIG database layer, driven over the
bridge. Companion to `allegro_api_notes.md`.

Every item here was verified live. Several correct earlier claims in this
repo that were wrong — each of those was wrong for the same reason, which is
the first section.

---

## 1. ⛔ Enumerate. Never sample.

**`$obj ZZZ_NOT_A_METHOD` does NOT list inherited methods.** It returns only
the immediate class's vocabulary. This repo recommended it as "the fastest way
to map an unfamiliar object", and it silently under-reports.

Consequences that actually shipped as documented conclusions:

| claim | reality |
|---|---|
| "`DboDesign` has no creation method" | `NewSchematic` existed; the probe output was truncated for display |
| "`DboPage` has no Add/Create" | `DboPage_New*` has **45** constructors |
| "no database-level alternative to `PlaceWire`" | `DboPage_NewWireScalar` |
| "`SetEffectivePropStringValue` is not a method on `DboPartInst`" | inherited from `DboBaseObject` |

**Use the flat command namespace instead — it is per-class and complete:**

```tcl
info commands Dbo*                  ;# ~4163 commands, ~290 classes
info commands DboPage_New*          ;# every constructor on one class
info commands DboPortInst_*HotSpot* ;# find accessors by concept
```

⭐ A method may exist on an object while the flat command does not, and vice
versa. Check **both** before concluding anything is absent.

## 2. Safe probing — which shapes crash

| call shape | wrong args | safe? |
|---|---|---|
| flat global, zero args — `DboPage_GetName` | argc checked first, clean usage string | ✅ |
| flat global, overloaded | dispatcher type-checks, clean rejection | ✅ |
| object method, **bogus name** — `$obj ZZZ` | returns method list (see §1 caveat) | ✅ |
| object method, **wrong-typed pointer** | dereferenced in C++ | ⛔ **kills Capture** |

`catch` protects against Tcl errors, **not** native crashes. Zero-arg probing of
a flat command yields the signature for free:

```
DboWire_SetPoint  ->  Wrong number of arguments :DboWire_SetPoint self position location
```

Overloaded functions yield no signature this way — resolve those by trying real
typed objects, which the dispatcher rejects cleanly rather than dereferencing.

## 3. ⛔ In-session reads are not evidence for anything structural

**The single most expensive rule in this file.** Capture caches and derives
aggressively. A read straight after a write reflects memory, not the database.

* **Flattened net tables are cached.** After creating a wire, the net list was
  unchanged — same net count, same pin counts. It took a close-and-reopen for
  the rebuild to show the wire had merged two nets. *Two separate "the wire
  carries no connectivity" conclusions came from reading that stale table.*
* **Page-level `DboNet` objects are derived and transient.** `$pin GetNet`
  returned `NULL` for a pin that was demonstrably connected, immediately after
  an unrelated page edit. Not damage — a rebuilt object graph.
* **Property readbacks reflect memory.** A write + readback + save can all
  report success with nothing on disk (§5).

**Only a close-and-reopen tells the truth.** Any verifier that reads the live
session is a smoke test, not a durability check.

## 4. ✅ Creating wires from the database layer

`PlaceWire` (the interactive command) spins a modal loop and kills the app from
a socket. The database constructor does not:

```tcl
# page, status, start point, end point.  Also valid: ($page $status) alone.
set w [DboPage_NewWireScalar $page $status \
         [DboTclHelper_sMakeCPoint $x1 $y1] [DboTclHelper_sMakeCPoint $x2 $y2]]

# read back
set it [DboPage_NewWiresIter $page $st]
set w  [$it NextWire $st]          ;# NOTE: NextWire takes a status arg
```

**Pin coordinates** come from the pin's hotspot, not from the part's location —
`DboPortInst` has no `GetLocation`:

```tcl
set p  [$partInst GetPinByPinNumber [DboTclHelper_sMakeCString "7"] $st]
set x  [DboPortInst_sGetHotSpotX $p $st]     ;# obj AND status
set y  [DboPortInst_sGetHotSpotY $p $st]
```

Units are database units = 1/100 inch, so standard 0.1" pin pitch reads as 10.

**Verified:** wires created this way survive a save/reopen **and carry real
connectivity** — after a rebuild, a supply net absorbed an adjacent net and its
pin count rose accordingly. Geometry *and* electrical, from a socket.

⚠ **A pin flagged no-connect will not join a net**, and the wire drawn to it
still renders as if connected — the X marker is simply occluded. Check first:

```tcl
$pin GetIsNoConnect $st      ;# 1 = will not connect
```

## 5. ⛔ Property edits do not persist without a human GUI save

`DboSession_SaveDesign` writes the `.DSN` (with `.DBK` rotation) and reports
`Succeeded=1`, `Code=0`. Property edits made over the bridge are **still lost**
on reopen.

Proven by writing a unique marker, saving via `SaveDesign`, copying the `.DSN`
aside, then opening that copy directly — it loads the *previous* value. Diffing
the bridge-saved file against a GUI-saved one from identical memory state:

```
855 of 122880 bytes differ, in ~33 small clusters near the file head
the property record itself is BYTE-IDENTICAL in both files
```

So `SaveDesign` writes the property **data** and not the **index** that binds
it. The record is present and unreferenced.

Approaches tried, all lost on reopen: `SaveDesign` alone; `MarkModified` on
every page; `$design SaveSchematic` per schematic; `SetUserPropStringValue`
(stored rather than effective); wrapping the write in
`StartDBBatchUpdate` / `EndDBBatchUpdate`. Only **File → Close → Save** survives.

⛔ **Never grep the `.DSN` to verify a property.** Strings are interned, so the
value appears in the file whether or not anything references it — that is
exactly what makes this failure look like a success.

**Working procedure:**

```
1. write the property over the bridge   (write EVERY spelling — see §6)
2. human: File -> Close, Save
3. reopen, then read back to confirm
```

## 6. Two spellings of the same property

Capture carries both `PART_NUMBER` and `Part Number`, and different consumers
read different ones. Writing one and checking that one passes while the netlist
still disagrees. **Write and assert both.**

## 7. Returned `DboState` carries the real status

Many calls return a `DboState` rather than raising. A wrapper that treats "no
Tcl error" as success will report OK for a no-op:

```tcl
$state Succeeded    ;# 1 / 0
$state Failed
$state Code
```

Note `Succeeded=1` means *the call* succeeded, which is not the same as the
intended effect being durable — see §5.

## 8. Object identity: a design can be live and invisible

`DboSession` holds designs that have **no GUI window**. The bridge reads and
writes them identically, so it is possible to modify and "save" a design that
is not on screen and that the user has no way to notice.

Always confirm identity before writing:

```tcl
set it [$session NewDesignsIter $st]
set d  [$it NextDesign $st]
set nm [DboTclHelper_sMakeCString {}] ; $d GetName $nm
DboTclHelper_sGetConstCharPtr $nm      ;# full path
```

⛔ `DboSession_RemoveDesign` **crashes Capture** — it returns success and the
process disappears. There is no verified programmatic close.
