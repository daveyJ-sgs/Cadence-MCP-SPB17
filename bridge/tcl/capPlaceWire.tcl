# Place a wire between two pins of one part, at database level.
# Uses DboPage_NewWireScalar {page status startCPoint endCPoint} -- proven
# 2026-08-17 to create real wires that the page's own iterator reports.
# placeWireBetweenPins {refdes pinA pinB}
proc ::capBridge::placeWireBetweenPins { pList } {
    set refdes [lindex $pList 0]
    set pa     [lindex $pList 1]
    set pb     [lindex $pList 2]
    set st [DboState]
    set inst [::capBridge::_findPart $refdes $st]
    if { $inst eq "" } { return [::capBridge::_err "no part '$refdes'"] }

    set na [DboTclHelper_sMakeCString $pa]
    set nb [DboTclHelper_sMakeCString $pb]
    set A [$inst GetPinByPinNumber $na $st]
    set B [$inst GetPinByPinNumber $nb $st]
    if { $A eq "NULL" || $B eq "NULL" } { return [::capBridge::_err "pin not found"] }
    set ax [DboPortInst_sGetHotSpotX $A $st]; set ay [DboPortInst_sGetHotSpotY $A $st]
    set bx [DboPortInst_sGetHotSpotX $B $st]; set by [DboPortInst_sGetHotSpotY $B $st]

    # locate the page that owns this part
    set d [::pcbWorkflows::_getActiveDesign]
    set target NULL
    set vIter [$d NewViewsIter $st $::IterDefs_SCHEMATICS]
    set v [$vIter NextView $st]
    while { $v ne "NULL" && $target eq "NULL" } {
        set sch [DboViewToDboSchematic $v]
        set pIter [$sch NewPagesIter $st]
        set pg [$pIter NextPage $st]
        while { $pg ne "NULL" } {
            set iIter [$pg NewPartInstsIter $st]
            set i [$iIter NextPartInst $st]
            while { $i ne "NULL" } {
                if { [::pcbWorkflows::_getRefDes $i] eq $refdes } { set target $pg }
                set i [$iIter NextPartInst $st]
            }
            ::pcbWorkflows::_deleteIter $iIter
            if { $target ne "NULL" } { break }
            set pg [$pIter NextPage $st]
        }
        ::pcbWorkflows::_deleteIter $pIter
        set v [$vIter NextView $st]
    }
    ::pcbWorkflows::_deleteIter $vIter
    if { $target eq "NULL" } { return [::capBridge::_err "page for '$refdes' not found"] }

    set w [DboPage_NewWireScalar $target $st \
             [DboTclHelper_sMakeCPoint $ax $ay] [DboTclHelper_sMakeCPoint $bx $by]]
    return [list OK wire $w from "$ax,$ay" to "$bx,$by"]
}
