;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; allegroQuery.il — structured, READ-ONLY board queries for the bridge.
;;
;; Counterpart to capBridgeQuery.tcl on the Capture side. Everything here
;; RETURNS data; nothing prints, and nothing modifies the board.
;;
;; Load over the bridge:
;;   python bridge/allegro/allegro_client.py "load(\"<repo>/bridge/allegro/allegroQuery.il\")"
;;
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; OUTPUT FORMAT
;;
;; Responses must be a SINGLE LINE (the helper does one readline per
;; exchange). SKILL's %L rendering of nested lists is also awkward to parse
;; on the Python side, so records use explicit delimiters instead:
;;
;;     field separator  ^
;;     record separator |
;;
;; Neither character appears in Allegro constraint names, layer names or
;; refdes, so no escaping is needed. Empty result -> "".
;;
;; pcbDrcAudit.il (the earlier SKILL tool) prints a human report to the
;; command window. This file is the machine-readable path; both can coexist.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

aqFS = "^"
aqRS = "|"

;; Render any value as a plain string, nil-safe.
procedure( aqStr( v )
    cond(
        ( (v == nil)      "" )
        ( stringp(v)      v )
        ( t               let( (r) r = errset(sprintf(nil "%L" v))
                              if( r car(r) "?" ) ) )
    )
)

procedure( aqJoin( fields )
    buildString(foreach(mapcar f fields aqStr(f)) aqFS)
)

;; Board-level summary.
;; -> name^activeDrcs^waivedDrcs^symbols^symdefs^padstacks^nets
procedure( aqBoard()
    let( (d)
        d = axlDBGetDesign()
        unless( d return("ERROR^no active design") )
        aqJoin(list(
            axlGetVariable("module")
            length(d->drcs)
            length(d->waived)
            length(d->symbols)
            length(d->symdefs)
            length(d->padstacks)
            length(d->nets)))
    )
)

;; All active (non-waived) DRCs.
;; -> type^name^layer^expected^actual^x^y | ...
procedure( aqDrcs()
    let( (d recs)
        d = axlDBGetDesign()
        unless( d return("ERROR^no active design") )
        recs = foreach( mapcar drc d->drcs
            aqJoin(list(drc->type drc->name drc->layer
                        drc->expected drc->actual
                        car(drc->xy) cadr(drc->xy)))
        )
        buildString(recs aqRS)
    )
)

;; Placed symbols (footprint instances).
;; -> refdes^symbolName^x^y^layer^mirrored | ...
procedure( aqSymbols()
    let( (d recs)
        d = axlDBGetDesign()
        unless( d return("ERROR^no active design") )
        recs = foreach( mapcar s d->symbols
            aqJoin(list(s->refdes s->name
                        car(s->xy) cadr(s->xy)
                        s->layer s->mirrored))
        )
        buildString(recs aqRS)
    )
)

;; Nets with their pin counts.
;; -> netName^pinCount | ...
procedure( aqNets()
    let( (d recs)
        d = axlDBGetDesign()
        unless( d return("ERROR^no active design") )
        recs = foreach( mapcar n d->nets
            aqJoin(list(n->name length(n->pins)))
        )
        buildString(recs aqRS)
    )
)

;; Padstacks in use.
;; -> name | ...
procedure( aqPadstacks()
    let( (d)
        d = axlDBGetDesign()
        unless( d return("ERROR^no active design") )
        buildString(foreach(mapcar p d->padstacks aqStr(p->name)) aqRS)
    )
)

printf("allegroQuery.il loaded: aqBoard aqDrcs aqSymbols aqNets aqPadstacks\n")
"allegroQuery-loaded"
