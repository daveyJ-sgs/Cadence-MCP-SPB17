;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; pcbDrcAudit.il
;;
;; Read-only DRC audit for the active Allegro PCB Editor design.
;; Makes NO changes to the board.
;;
;; Load:  load("<repo>/skill/pcbDrcAudit.il")   at the Skill> prompt
;;        (or deploy skill/allegro.ilinit to load it automatically)
;; Run :  pcbDrcAudit()            at the Skill> prompt
;;   or:  pcbdrcaudit              at the native Command: prompt (registered below)
;;
;; DESIGN NOTES / why this differs from the first draft:
;;   * design->drcs is the list of NON-WAIVED DRCs only.
;;     design->waived is a SEPARATE list of waived DRCs.
;;     (Confirmed: doc/algroskill/02dbdesc.html, Table 2-5 design attributes.)
;;     The draft counted drc->waived inside design->drcs, which is always nil
;;     there -- so "unwaived" would have always equalled the total.
;;   * No printf width/flag specifiers (%-3d, %-25s). Zero of the 121 SKILL
;;     example files shipped in share/pcb/examples/skill use them; treating
;;     them as unsupported until proven otherwise.
;;   * No add1(). Also unused in every shipped example. Using n = n + 1.
;;   * %L (not %s) for every value read from the database, because %s on a nil
;;     field raises a format/argument mismatch error. %L prints any type
;;     safely and distinguishes "" from nil, which is useful in an audit.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

;; String membership using equal (value compare), not eq (identity).
procedure( _pcbStrMember( s lst )
    let( (found)
        found = nil
        foreach( x lst
            when( equal(x s) found = t )
        )
        found
    )
)

;; Ordered list of the distinct values of one field across a DRC list.
procedure( _pcbDistinct( drcList field )
    let( (vals v)
        vals = nil
        foreach( drc drcList
            v = get(drc field)
            unless( _pcbStrMember(v vals) vals = cons(v vals) )
        )
        reverse(vals)
    )
)

;; How many DRCs in drcList have <field> == val.
procedure( _pcbCountWhere( drcList field val )
    let( (n)
        n = 0
        foreach( drc drcList
            when( equal(get(drc field) val) n = n + 1 )
        )
        n
    )
)

;; Print a "count  value" histogram of one DRC field.
procedure( _pcbHistogram( drcList field title )
    printf("\n-- %s --\n" title)
    foreach( v _pcbDistinct(drcList field)
        printf("  %4d   %L\n" _pcbCountWhere(drcList field v) v)
    )
    t
)

procedure( pcbDrcAudit( @optional (detail t) )
    let( (design active waived nActive nWaived i)

        design = axlDBGetDesign()
        unless( design
            printf("\npcbDrcAudit: no active design.\n")
            return(nil)
        )

        active = design->drcs      ; non-waived DRCs
        waived = design->waived    ; waived DRCs
        nActive = length(active)
        nWaived = length(waived)

        printf("\n======================================================\n")
        printf("  PCB DRC AUDIT\n")
        printf("======================================================\n")
        printf("  Active (non-waived) DRCs : %d\n" nActive)
        printf("  Waived DRCs              : %d\n" nWaived)

        when( nActive > 0
            _pcbHistogram(active 'type "BY DOMAIN (drc->type)")
            _pcbHistogram(active 'name "BY CONSTRAINT (drc->name)")
            _pcbHistogram(active 'layer "BY LAYER (drc->layer)")

            when( detail
                printf("\n-- DETAIL (active DRCs) --\n")
                i = 0
                foreach( drc active
                    i = i + 1
                    printf("%d) %L / %L\n" i drc->type drc->name)
                    printf("     layer    %L\n" drc->layer)
                    printf("     expected %L   actual %L\n" drc->expected drc->actual)
                    printf("     source   %L   at %L\n" drc->source drc->xy)
                )
            )
        )

        printf("\n------------------------------------------------------\n")
        printf("  Total DRC records: %d  (active %d / waived %d)\n"
               nActive + nWaived nActive nWaived)
        printf("------------------------------------------------------\n")
        t
    )
)

;; Summary only -- no per-violation detail. Useful once the board gets noisy.
procedure( pcbDrcSummary()
    pcbDrcAudit(nil)
)

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; ROOT-CAUSE PROBE
;;
;; 71 of 97 violations are "Line to SMD Pin Spacing" with actual = 0 MIL,
;; distributed one-per-part across a regular 12 x 3 array. That is one
;; systemic condition, not 71 routing mistakes. Hypothesis: the board was
;; converted (see the "converted" folder in allegro.ini) and pad net
;; associations were lost, so every trace landing on its own pad reads as
;; a foreign-net contact at zero clearance.
;;
;; drc->violations holds the offending figures (max 2). If their ->net is
;; nil, or the two figures sit on different nets, the hypothesis is proven.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

;; Describe one figure: what it is, and what net it believes it is on.
procedure( _pcbDescribeFig( fig )
    let( (net)
        unless( fig
            printf("       <nil figure>\n")
            return(nil)
        )
        net = fig->net
        printf("       objType %L  layer %L\n" fig->objType fig->layer)
        if( net
            then printf("       net     %L\n" net->name)
            else printf("       net     *** nil -- no net association ***\n")
        )
        t
    )
)

;; Dump the participating figures for the first n DRCs matching constraint
;; name cname (nil = any). Read-only.
procedure( pcbDrcInspect( @optional (cname nil) (n 5) )
    let( (design active i)
        design = axlDBGetDesign()
        unless( design printf("\npcbDrcInspect: no active design.\n") return(nil) )
        active = design->drcs

        printf("\n=== DRC FIGURE INSPECTION ===\n")
        when( cname printf("filter: constraint name = %L\n" cname) )
        i = 0
        foreach( drc active
            when( (n > i) && (!cname || equal(drc->name cname))
                i = i + 1
                printf("\n%d) %L\n" i drc->name)
                printf("     expected %L   actual %L   at %L\n"
                       drc->expected drc->actual drc->xy)
                printf("     participating figures (%d):\n" length(drc->violations))
                foreach( fig drc->violations
                    _pcbDescribeFig(fig)
                )
            )
        )
        when( i == 0 printf("\nNo matching DRCs.\n") )
        printf("\n=== end ===\n")
        t
    )
)

;; Same constraint name AND same marker location -> the same physical problem
;; reported once per participating figure.
procedure( _pcbSameSpot( a b )
    equal(a->name b->name) &&
    (car(a->xy) == car(b->xy)) &&
    (cadr(a->xy) == cadr(b->xy))
)

;; Collapse double-reported markers, then bucket by signal vs noise.
procedure( pcbDrcTriage()
    let( (design active uniq dup contact config rounding other)
        design = axlDBGetDesign()
        unless( design printf("\npcbDrcTriage: no active design.\n") return(nil) )
        active = design->drcs

        uniq = nil
        dup = 0
        foreach( drc active
            if( exists( u uniq _pcbSameSpot(drc u) )
                then dup = dup + 1
                else uniq = cons(drc uniq)
            )
        )
        uniq = reverse(uniq)

        contact  = 0   ; actual 0 clearance -- copper touching. Real.
        config   = 0   ; expected 0 -- constraint not meaningfully set.
        rounding = 0   ; actual differs from expected by a hair. Artifact.
        other    = 0
        foreach( drc uniq
            cond(
                ( equal(drc->expected "0 MIL")  config   = config   + 1 )
                ( equal(drc->actual   "0 MIL")  contact  = contact  + 1 )
                ( equal(drc->expected "11.81 MIL") && equal(drc->actual "11.8 MIL")
                                                rounding = rounding + 1 )
                ( t                             other    = other    + 1 )
            )
        )

        printf("\n======================================================\n")
        printf("  PCB DRC TRIAGE\n")
        printf("======================================================\n")
        printf("  Raw records          : %d\n" length(active))
        printf("  Duplicate markers    : %d  (same constraint, same xy)\n" dup)
        printf("  Distinct problems    : %d\n" length(uniq))
        printf("\n  Of the distinct problems:\n")
        printf("    zero-clearance contact : %d   <- investigate, likely systemic\n" contact)
        printf("    unset constraint (0)   : %d   <- config noise\n" config)
        printf("    sub-micron rounding    : %d   <- artifact, 0.01 MIL = 0.25 um\n" rounding)
        printf("    other                  : %d\n" other)
        printf("------------------------------------------------------\n")
        t
    )
)

;; Zero-argument wrapper for the net probe.
;;
;; pcbDrcInspect takes arguments, so it cannot be a registered command --
;; axlCmdRegister passes every argument as a STRING, so the numeric count
;; would arrive as "3". This wrapper takes none, so it registers cleanly and
;; runs from the native Command: prompt with no quoting to mangle.
procedure( pcbDrcNets()
    pcbDrcInspect("Line to SMD Pin Spacing" 3)
)

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Registration -- must tolerate re-loading.
;;
;; Re-running axlCmdRegister for an already-registered command can error, and
;; because registration sits at the end of the file, an unguarded error aborts
;; the load: new procs never get registered and the banner never prints, so
;; the file looks like it silently did nothing. errset() contains that, which
;; makes the file safe to load repeatedly during development.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

procedure( _pcbRegister( cmdName fn )
    if( errset( axlCmdRegister(cmdName fn ?cmdType "general") )
        then t
        else
            printf("  note: '%s' not re-registered (already present?) -- still callable from Skill>\n"
                   cmdName)
            nil
    )
)

_pcbRegister("pcbdrcaudit"   'pcbDrcAudit)
_pcbRegister("pcbdrcsummary" 'pcbDrcSummary)
_pcbRegister("pcbdrctriage"  'pcbDrcTriage)
_pcbRegister("pcbdrcnets"    'pcbDrcNets)

printf("\n=== pcbDrcAudit.il LOADED (v2) ===\n")
printf("  Command: prompt ->  pcbdrcaudit   pcbdrcsummary   pcbdrctriage   pcbdrcnets\n")
printf("  Skill>   prompt ->  pcbDrcInspect(\"<constraint name>\" <count>)\n\n")

