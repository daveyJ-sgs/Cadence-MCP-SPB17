#############################################################################
# capBridgeQuery.tcl
#
# Read-only design queries for OrCAD Capture 17.4, written to be called over
# the Communication Server socket by an external process.
#
# Load remotely:
#     CaptureBridge().source_file("<repo>/bridge/tcl/capBridgeQuery.tcl")
#
# DESIGN RULES for anything callable over the socket -- all learned the hard
# way, see the handoff document section 4.9:
#
#   1. Every proc takes EXACTLY ONE argument. The dispatcher always calls
#      `$procName $arguments`, so a zero-arg proc fails on arity. Unused
#      argument is named pList by Cadence convention.
#
#   2. RETURN data, never `puts` it. The server does `puts $sock $value` and
#      the client does a single `gets`, so one embedded newline desynchronizes
#      every subsequent reply. Returning a TCL list keeps the response on one
#      line and gives the caller something parseable instead of prose.
#
#   3. Catch internally and return a structured error. The server collapses
#      any uncaught failure to the bare string "Server method failed" with no
#      detail whatsoever.
#
#   4. Never `return` from inside a `catch` body -- TCL intercepts it as
#      TCL_RETURN and the value surfaces as an error. Set a default before the
#      catch, assign inside it, return after. This already bit this project
#      once (handoff 3.3).
#
# Reuses the confirmed-working traversal helpers from the deployed
# pcbWorkflows package rather than re-deriving them: several documented
# Capture API calls do not work in 17.4 and the working equivalents are
# already proven there.
#############################################################################

package require pcbWorkflows

namespace eval ::capBridge {
    variable version 1.0
}

# Standard structured error. Callers test for the leading ERROR token.
proc ::capBridge::_err { msg } {
    return [list ERROR $msg]
}

#---------------------------------------------------------------------------
# _refDes -- reference designator of a part instance.
#
# DO NOT use ::pcbWorkflows::_getRefDes. It is broken, and silently so:
#
#     DboPartInst_sGetReference $pInst              ;# WRONG -- 1 argument
#
# The real signature takes TWO arguments and returns a CString POINTER, not
# a TCL string:
#
#     DboPartInst_sGetReference obj status  ->  _p_CString
#
# The one-argument call raises "Wrong number of arguments", the surrounding
# catch swallows it, and the helper returns its "?" default. Every part then
# looks unannotated, which is exactly the false positive that made this
# design appear to have 44 unannotated refdes when in fact it is fully
# annotated (first part verified as J2 / PHONEJACK).
#
# Discovered over the bridge on 2026-07-27. The deployed
# pcbWorkflows.tcl still carries the bug -- see handoff section 3.5.
#---------------------------------------------------------------------------
proc ::capBridge::_refDes { pInst pStatus } {
    set val "?"
    set rc [catch {
        set cs  [DboPartInst_sGetReference $pInst $pStatus]
        set val [DboTclHelper_sGetConstCharPtr $cs]
    }]
    if { $val eq "" } { set val "?" }
    return $val
}

#---------------------------------------------------------------------------
# ping -- liveness check that also proves the package is loaded.
#---------------------------------------------------------------------------
proc ::capBridge::ping { pList } {
    variable version
    return [list OK capBridgeQuery $version]
}

#---------------------------------------------------------------------------
# designInfo -- name and top-level counts for the active design.
# Returns: {OK <designName> <schematicCount> <pageCount> <partCount>}
#---------------------------------------------------------------------------
proc ::capBridge::designInfo { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set name    [::pcbWorkflows::_getDesignName $d]
    set schCnt  0
    set pageCnt 0
    set partCnt 0

    set rc [catch {
        set lStatus  [DboState]
        set NULLOBJ  NULL
        set vIter    [$d NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
        set v        [$vIter NextView $lStatus]
        while { $v != $NULLOBJ } {
            incr schCnt
            set sch   [DboViewToDboSchematic $v]
            set pIter [$sch NewPagesIter $lStatus]
            set pg    [$pIter NextPage $lStatus]
            while { $pg != $NULLOBJ } {
                incr pageCnt
                set iIter [$pg NewPartInstsIter $lStatus]
                set inst  [$iIter NextPartInst $lStatus]
                while { $inst != $NULLOBJ } {
                    incr partCnt
                    set inst [$iIter NextPartInst $lStatus]
                }
                ::pcbWorkflows::_deleteIter $iIter
                set pg [$pIter NextPage $lStatus]
            }
            ::pcbWorkflows::_deleteIter $pIter
            set v [$vIter NextView $lStatus]
        }
        ::pcbWorkflows::_deleteIter $vIter
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "designInfo: $failed"] }
    return [list OK $name $schCnt $pageCnt $partCnt]
}

#---------------------------------------------------------------------------
# parts -- every placed part instance in the design.
# Returns: {OK {refdes schematic page value footprint partnumber} ...}
#---------------------------------------------------------------------------
proc ::capBridge::parts { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set rows   [list]

    set rc [catch {
        set lStatus [DboState]
        set NULLOBJ NULL
        set vIter   [$d NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
        set v       [$vIter NextView $lStatus]
        while { $v != $NULLOBJ } {
            set sch [DboViewToDboSchematic $v]
            set cs  [DboTclHelper_sMakeCString]
            $sch GetName $cs
            set schName [DboTclHelper_sGetConstCharPtr $cs]

            set pIter [$sch NewPagesIter $lStatus]
            set pg    [$pIter NextPage $lStatus]
            while { $pg != $NULLOBJ } {
                set pgName [::pcbWorkflows::_getPageLocation $pg]
                set iIter  [$pg NewPartInstsIter $lStatus]
                set inst   [$iIter NextPartInst $lStatus]
                while { $inst != $NULLOBJ } {
                    lappend rows [list \
                        [::capBridge::_refDes $inst $lStatus] \
                        $schName \
                        $pgName \
                        [::pcbWorkflows::_getProp $inst "Value"] \
                        [::pcbWorkflows::_getProp $inst "PCB Footprint"] \
                        [::pcbWorkflows::_getProp $inst "Part Number"]]
                    set inst [$iIter NextPartInst $lStatus]
                }
                ::pcbWorkflows::_deleteIter $iIter
                set pg [$pIter NextPage $lStatus]
            }
            ::pcbWorkflows::_deleteIter $pIter
            set v [$vIter NextView $lStatus]
        }
        ::pcbWorkflows::_deleteIter $vIter
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "parts: $failed"] }
    return [concat [list OK] $rows]
}

#---------------------------------------------------------------------------
# bomAudit -- every BOM-bearing property in ONE round-trip.
#
# Exists because Capture carries TWO part-number properties and they drift:
#
#   "Part Number"   what Capture's BOM report and CIS read
#   PART_NUMBER     what the netlist transfers to the board -- it is the one
#                   listed in <CDS_ROOT>/tools/capture/allegro.cfg under
#                   [ComponentDefinitionProps]. "Part Number" is NOT there.
#
# A checker that reads only one of them passes while the board silently gets
# a stale or missing part number. That happened here: T1 kept the superseded
# 164H36 in PART_NUMBER, and 34 parts had no PART_NUMBER at all, while
# "Part Number" was correct on all 47.
#
# Returns: {OK {refdes value footprint partNumber PART_NUMBER manufacturer} ...}
#---------------------------------------------------------------------------
proc ::capBridge::bomAudit { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set rows [list]

    set rc [catch {
        set lStatus [DboState]
        set NULLOBJ NULL
        set vIter   [$d NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
        set v       [$vIter NextView $lStatus]
        while { $v != $NULLOBJ } {
            set sch   [DboViewToDboSchematic $v]
            set pIter [$sch NewPagesIter $lStatus]
            set pg    [$pIter NextPage $lStatus]
            while { $pg != $NULLOBJ } {
                set iIter [$pg NewPartInstsIter $lStatus]
                set inst  [$iIter NextPartInst $lStatus]
                while { $inst != $NULLOBJ } {
                    lappend rows [list \
                        [::capBridge::_refDes $inst $lStatus] \
                        [::pcbWorkflows::_getProp $inst "Value"] \
                        [::pcbWorkflows::_getProp $inst "PCB Footprint"] \
                        [::pcbWorkflows::_getProp $inst "Part Number"] \
                        [::pcbWorkflows::_getProp $inst "PART_NUMBER"] \
                        [::pcbWorkflows::_getProp $inst "Manufacturer"]]
                    set inst [$iIter NextPartInst $lStatus]
                }
                ::pcbWorkflows::_deleteIter $iIter
                set pg [$pIter NextPage $lStatus]
            }
            ::pcbWorkflows::_deleteIter $pIter
            set v [$vIter NextView $lStatus]
        }
        ::pcbWorkflows::_deleteIter $vIter
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "bomAudit: $failed"] }
    return [concat [list OK] $rows]
}

#---------------------------------------------------------------------------
# pages -- schematic/page structure only. Cheap; useful for orientation.
# Returns: {OK {schematic page partCount} ...}
#---------------------------------------------------------------------------
proc ::capBridge::pages { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set rows   [list]

    set rc [catch {
        set lStatus [DboState]
        set NULLOBJ NULL
        set vIter   [$d NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
        set v       [$vIter NextView $lStatus]
        while { $v != $NULLOBJ } {
            set sch [DboViewToDboSchematic $v]
            set cs  [DboTclHelper_sMakeCString]
            $sch GetName $cs
            set schName [DboTclHelper_sGetConstCharPtr $cs]

            set pIter [$sch NewPagesIter $lStatus]
            set pg    [$pIter NextPage $lStatus]
            while { $pg != $NULLOBJ } {
                set n     0
                set iIter [$pg NewPartInstsIter $lStatus]
                set inst  [$iIter NextPartInst $lStatus]
                while { $inst != $NULLOBJ } {
                    incr n
                    set inst [$iIter NextPartInst $lStatus]
                }
                ::pcbWorkflows::_deleteIter $iIter
                lappend rows [list $schName [::pcbWorkflows::_getPageLocation $pg] $n]
                set pg [$pIter NextPage $lStatus]
            }
            ::pcbWorkflows::_deleteIter $pIter
            set v [$vIter NextView $lStatus]
        }
        ::pcbWorkflows::_deleteIter $vIter
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "pages: $failed"] }
    return [concat [list OK] $rows]
}

#---------------------------------------------------------------------------
# partProps -- every effective property on the first part instance found,
# or on the part whose refdes matches the single argument.
#
# Ground-truth tool: Capture property names are easy to get subtly wrong
# (space vs underscore), and _getProp returns "" for a name that does not
# exist -- indistinguishable from a property that exists but is empty.
#
# Returns: {OK {name value} {name value} ...}
#---------------------------------------------------------------------------
proc ::capBridge::partProps { pList } {
    set want [string trim [lindex $pList 0]]
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set rows  [list]
    set found 0
    set rc [catch {
        set lStatus [DboState]
        set NULLOBJ NULL
        set vIter   [$d NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
        set v       [$vIter NextView $lStatus]
        while { $v != $NULLOBJ && !$found } {
            set sch   [DboViewToDboSchematic $v]
            set pIter [$sch NewPagesIter $lStatus]
            set pg    [$pIter NextPage $lStatus]
            while { $pg != $NULLOBJ && !$found } {
                set iIter [$pg NewPartInstsIter $lStatus]
                set inst  [$iIter NextPartInst $lStatus]
                while { $inst != $NULLOBJ && !$found } {
                    set rd [::capBridge::_refDes $inst $lStatus]
                    if { $want eq "" || $rd eq $want } {
                        set found 1
                        set pi [$inst NewEffectivePropsIter $lStatus]
                        set nm [DboTclHelper_sMakeCString]
                        set vl [DboTclHelper_sMakeCString]
                        set ty [DboTclHelper_sMakeDboValueType]
                        set ed [DboTclHelper_sMakeInt]
                        set st [$pi NextEffectiveProp $nm $vl $ty $ed]
                        while { [$st OK] == 1 } {
                            lappend rows [list \
                                [DboTclHelper_sGetConstCharPtr $nm] \
                                [DboTclHelper_sGetConstCharPtr $vl]]
                            set st [$pi NextEffectiveProp $nm $vl $ty $ed]
                        }
                        ::pcbWorkflows::_deleteIter $pi
                        set rows [linsert $rows 0 [list _REFDES_ $rd]]
                    }
                    set inst [$iIter NextPartInst $lStatus]
                }
                ::pcbWorkflows::_deleteIter $iIter
                set pg [$pIter NextPage $lStatus]
            }
            ::pcbWorkflows::_deleteIter $pIter
            set v [$vIter NextView $lStatus]
        }
        ::pcbWorkflows::_deleteIter $vIter
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "partProps: $failed"] }
    if { !$found } { return [::capBridge::_err "no part matching '$want'"] }
    return [concat [list OK] $rows]
}

#############################################################################
# OUTPUT CAPTURE
#
# The four workflows write human-readable reports with `puts`, which lands in
# Capture's Command Window -- visible to a human sitting at Capture, but
# invisible to an external caller.
#
# Rather than rewrite the workflows, exploit TCL command resolution: a command
# is looked up in the CURRENT namespace before the global one. Defining
# ::pcbWorkflows::puts therefore intercepts every puts issued by any proc in
# that namespace, while the global ::puts is left completely untouched. No
# edits to pcbWorkflows.tcl, and nothing else in Capture is affected.
#
# Note this catches _logSection and _logSummary too, which call puts directly
# rather than going through _log -- wrapping _log alone would silently drop
# the section headers and the summary block.
#
# Captured lines are returned as a TCL LIST, one element per line, which keeps
# the socket response on a single physical line as the protocol requires.
#############################################################################

namespace eval ::capBridge {
    variable logBuf [list]
    variable capturing 0
}

proc ::capBridge::captureOn { pList } {
    variable logBuf
    variable capturing
    set logBuf [list]
    if { !$capturing } {
        proc ::pcbWorkflows::puts { args } {
            # Forms: puts str | puts -nonewline str | puts chan str
            lappend ::capBridge::logBuf [lindex $args end]
            uplevel 1 [linsert $args 0 ::puts]
        }
        set capturing 1
    }
    return [list OK capturing]
}

proc ::capBridge::captureOff { pList } {
    variable capturing
    if { $capturing } {
        catch { rename ::pcbWorkflows::puts {} }
        set capturing 0
    }
    return [list OK stopped]
}

proc ::capBridge::getCapture { pList } {
    variable logBuf
    return [concat [list OK] $logBuf]
}

# Run one of the four workflows and return everything it printed.
# Whitelisted: this executes a proc by name on behalf of a remote caller.
proc ::capBridge::runWorkflow { pList } {
    variable logBuf
    set name [string trim [lindex $pList 0]]
    set allowed { preNetlistCheck bomScrubber hsNetAudit netNamingAudit }
    if { [lsearch -exact $allowed $name] < 0 } {
        return [::capBridge::_err "unknown workflow '$name'; allowed: $allowed"]
    }
    ::capBridge::captureOn {}
    set rc [catch { ::pcbWorkflows::$name } failed]
    ::capBridge::captureOff {}
    if { $rc != 0 } { return [::capBridge::_err "runWorkflow $name: $failed"] }
    return [concat [list OK] $logBuf]
}

#############################################################################
# CONNECTIVITY
#
# Traversal chain, every step confirmed live before use (a wrong method name
# on a SWIG object HANGS Capture's event loop rather than raising, so nothing
# here is guessed):
#
#   design  NewFlatNetsIter / NextFlatNet      -> DboFlatNet
#   net     GetName <cstring>                  -> net name
#   net     NewPortOccurrencesIter             -> DboFlatNetPortOccurrencesIter
#   iter    NextPortOccurrence                 -> DboPortOccurrence
#   portOcc GetPortInst <status>               -> DboPortInst
#   portInst GetOwner                          -> DboPartInst   (no status arg)
#   partInst -> _refDes
#############################################################################

# nets -- every flat net with its pin count.
# Returns: {OK {netName pinCount} ...}
proc ::capBridge::nets { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set rows [list]
    set rc [catch {
        set lStatus [DboState]
        set NULLOBJ NULL
        set nIter [$d NewFlatNetsIter $lStatus]
        if { $nIter != $NULLOBJ } {
            set net [$nIter NextFlatNet $lStatus]
            while { $net != $NULLOBJ } {
                set cs [DboTclHelper_sMakeCString]
                $net GetName $cs
                set nm [DboTclHelper_sGetConstCharPtr $cs]

                set cnt 0
                set pIter [$net NewPortOccurrencesIter $lStatus]
                set po [$pIter NextPortOccurrence $lStatus]
                while { $po != $NULLOBJ } {
                    incr cnt
                    set po [$pIter NextPortOccurrence $lStatus]
                }
                ::pcbWorkflows::_deleteIter $pIter

                lappend rows [list $nm $cnt]
                set net [$nIter NextFlatNet $lStatus]
            }
            ::pcbWorkflows::_deleteIter $nIter
        }
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "nets: $failed"] }
    return [concat [list OK] $rows]
}

# connectivity -- every flat net with the refdes it connects.
# Returns: {OK {netName pinCount {refdes refdes ...}} ...}
# This is the netlist as an agent would want to reason about it.
proc ::capBridge::connectivity { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set rows [list]
    set rc [catch {
        set lStatus [DboState]
        set NULLOBJ NULL
        set nIter [$d NewFlatNetsIter $lStatus]
        if { $nIter != $NULLOBJ } {
            set net [$nIter NextFlatNet $lStatus]
            while { $net != $NULLOBJ } {
                set cs [DboTclHelper_sMakeCString]
                $net GetName $cs
                set nm [DboTclHelper_sGetConstCharPtr $cs]

                set refs [list]
                set cnt 0
                set pIter [$net NewPortOccurrencesIter $lStatus]
                set po [$pIter NextPortOccurrence $lStatus]
                while { $po != $NULLOBJ } {
                    incr cnt
                    # Any single link in this chain can be null on odd
                    # objects (off-page connectors, ports); skip rather than
                    # abort the whole traversal.
                    catch {
                        set pi [$po GetPortInst $lStatus]
                        if { $pi != $NULLOBJ } {
                            set owner [$pi GetOwner]
                            if { $owner != $NULLOBJ } {
                                lappend refs [::capBridge::_refDes $owner $lStatus]
                            }
                        }
                    }
                    set po [$pIter NextPortOccurrence $lStatus]
                }
                ::pcbWorkflows::_deleteIter $pIter

                lappend rows [list $nm $cnt $refs]
                set net [$nIter NextFlatNet $lStatus]
            }
            ::pcbWorkflows::_deleteIter $nIter
        }
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "connectivity: $failed"] }
    return [concat [list OK] $rows]
}

#############################################################################
# WRITE SUPPORT  -- everything above this line is read-only.
#
# Pattern taken from Cadence's own shipped capCommServerMethods::ModifyProperty:
#   SetEffectivePropStringValue <nameCStr> <valueCStr>  -> DboState
#   [$state OK] == 1 on success.
#
# Every mutator returns the PREVIOUS value so the caller can undo. Nothing
# here saves the design; persisting is a separate, explicit step.
#############################################################################

# Locate a part instance by reference designator. Returns "" if not found.
proc ::capBridge::_findPart { refdes pStatus } {
    set found ""
    catch {
        set d [::pcbWorkflows::_getActiveDesign]
        set NULLOBJ NULL
        set vIter [$d NewViewsIter $pStatus $::IterDefs_SCHEMATICS]
        set v     [$vIter NextView $pStatus]
        while { $v != $NULLOBJ && $found eq "" } {
            set sch   [DboViewToDboSchematic $v]
            set pIter [$sch NewPagesIter $pStatus]
            set pg    [$pIter NextPage $pStatus]
            while { $pg != $NULLOBJ && $found eq "" } {
                set iIter [$pg NewPartInstsIter $pStatus]
                set inst  [$iIter NextPartInst $pStatus]
                while { $inst != $NULLOBJ && $found eq "" } {
                    if { [::capBridge::_refDes $inst $pStatus] eq $refdes } {
                        set found $inst
                    }
                    set inst [$iIter NextPartInst $pStatus]
                }
                ::pcbWorkflows::_deleteIter $iIter
                set pg [$pIter NextPage $pStatus]
            }
            ::pcbWorkflows::_deleteIter $pIter
            set v [$vIter NextView $pStatus]
        }
        ::pcbWorkflows::_deleteIter $vIter
    }
    return $found
}

# setPartProp {refdes propName newValue}
# Returns: {OK refdes propName oldValue newValue}
proc ::capBridge::setPartProp { pList } {
    set refdes [lindex $pList 0]
    set prop   [lindex $pList 1]
    set val    [lindex $pList 2]

    if { $refdes eq "" || $prop eq "" } {
        return [::capBridge::_err "usage: setPartProp {refdes propName value}"]
    }

    set lStatus [DboState]
    set inst [::capBridge::_findPart $refdes $lStatus]
    if { $inst eq "" } { return [::capBridge::_err "no part with refdes '$refdes'"] }

    set old [::pcbWorkflows::_getProp $inst $prop]

    set ok 0
    set rc [catch {
        set nameCStr [DboTclHelper_sMakeCString $prop]
        set valCStr  [DboTclHelper_sMakeCString $val]
        set st [$inst SetEffectivePropStringValue $nameCStr $valCStr]
        set ok [$st OK]
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "setPartProp: $failed"] }
    if { $ok != 1 }  { return [::capBridge::_err "setPartProp: SetEffectivePropStringValue rejected '$prop'='$val' on $refdes"] }

    set now [::pcbWorkflows::_getProp $inst $prop]
    return [list OK $refdes $prop $old $now]
}

# getPartProp {refdes propName} -> {OK refdes propName value}
proc ::capBridge::getPartProp { pList } {
    set refdes [lindex $pList 0]
    set prop   [lindex $pList 1]
    set lStatus [DboState]
    set inst [::capBridge::_findPart $refdes $lStatus]
    if { $inst eq "" } { return [::capBridge::_err "no part with refdes '$refdes'"] }
    return [list OK $refdes $prop [::pcbWorkflows::_getProp $inst $prop]]
}

# saveDesign -- persist the active design to disk.
# Pattern: $session SaveDesign $design  (capAnnotateHBlockPageNumber.tcl:211)
# Returns {OK saved <designName>}.
proc ::capBridge::saveDesign { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }
    set name [::pcbWorkflows::_getDesignName $d]
    set rc [catch {
        set s $::DboSession_s_pDboSession
        DboSession -this $s
        $s SaveDesign $d
    } failed]
    if { $rc != 0 } { return [::capBridge::_err "saveDesign: $failed"] }
    return [list OK saved $name]
}

#############################################################################
# locateNet -- find where a net physically lives.
#
# There is NO page-level net iterator: nets are not page objects. Pages own
# WIRES, and a wire knows its net ($wire GetNet $status -- the signature used
# by Cadence's own capCommServerMethods::GetNet). So a net is located by
# scanning wires and asking each one.
#
# Ports, off-page connectors and globals are counted separately, because an
# orphaned net (0 pins) can be produced by a wire stub with no part pin on
# it, or by a connector/alias that never attached to anything.
#
# Returns: {OK {page wireCount portCount opcCount globalCount} ...}
#############################################################################
proc ::capBridge::locateNet { pList } {
    set want [string trim [lindex $pList 0]]
    if { $want eq "" } { return [::capBridge::_err "usage: locateNet {netName}"] }

    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set rows [list]
    set rc [catch {
        set st [DboState]
        set NULLOBJ NULL
        set vIter [$d NewViewsIter $st $::IterDefs_SCHEMATICS]
        set v     [$vIter NextView $st]
        while { $v != $NULLOBJ } {
            set sch   [DboViewToDboSchematic $v]
            set pIter [$sch NewPagesIter $st]
            set pg    [$pIter NextPage $st]
            while { $pg != $NULLOBJ } {
                set pgName [::pcbWorkflows::_getPageLocation $pg]
                set nWire 0

                set wIter [$pg NewWiresIter $st]
                set w [$wIter NextWire $st]
                while { $w != $NULLOBJ } {
                    catch {
                        set net [$w GetNet $st]
                        if { $net != $NULLOBJ } {
                            set c [DboTclHelper_sMakeCString]
                            $net GetName $c
                            if { [DboTclHelper_sGetConstCharPtr $c] eq $want } { incr nWire }
                        }
                    }
                    set w [$wIter NextWire $st]
                }
                ::pcbWorkflows::_deleteIter $wIter

                if { $nWire > 0 } { lappend rows [list $pgName $nWire] }
                set pg [$pIter NextPage $st]
            }
            ::pcbWorkflows::_deleteIter $pIter
            set v [$vIter NextView $st]
        }
        ::pcbWorkflows::_deleteIter $vIter
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "locateNet: $failed"] }
    if { [llength $rows] == 0 } {
        return [list OK NOT-FOUND-ON-ANY-WIRE $want]
    }
    return [concat [list OK] $rows]
}

#############################################################################
# hangingWires -- find wire endpoints that connect to nothing.
#
# Technique lifted from Cadence's own capDRC/capHangingWires.tcl, so every
# call here is confirmed rather than guessed:
#
#   $wire GetStartPoint/GetEndPoint <status>   -> CPoint
#   DboTclHelper_sGetCPointX / _sGetCPointY    -> coordinates
#   $page NewObjectsAtPointIter <point> <st>   -> objects at that location
#   $object IsCurrent                          -> 1 if it counts
#
# An endpoint with fewer than 2 current objects at it is dangling: the wire
# itself is one object, so anything properly connected has at least two.
#
# This is how to locate an orphaned net. Page-level DboNet objects have EMPTY
# names in this design -- real net names exist only on
# the flattened hierarchical nets -- so a net cannot be found by scanning
# pages for its name. Geometry is the way in.
#
# Returns: {OK {page x y end} ...}
#############################################################################
proc ::capBridge::hangingWires { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }

    set rows [list]
    set rc [catch {
        set st [DboState]
        set NULLOBJ NULL
        set vIter [$d NewViewsIter $st $::IterDefs_SCHEMATICS]
        set v     [$vIter NextView $st]
        while { $v != $NULLOBJ } {
            set sch   [DboViewToDboSchematic $v]
            set pIter [$sch NewPagesIter $st]
            set pg    [$pIter NextPage $st]
            while { $pg != $NULLOBJ } {
                set pgName [::pcbWorkflows::_getPageLocation $pg]

                set wIter [$pg NewWiresIter $st]
                set w [$wIter NextWire $st]
                while { $w != $NULLOBJ } {
                    foreach end {start end} {
                        if { $end eq "start" } {
                            set pt [$w GetStartPoint $st]
                        } else {
                            set pt [$w GetEndPoint $st]
                        }
                        set cnt 0
                        set oIter [$pg NewObjectsAtPointIter $pt $st]
                        set o [$oIter NextObject $st]
                        while { $o != $NULLOBJ && $cnt < 2 } {
                            if { [$o IsCurrent] == 1 } { incr cnt }
                            set o [$oIter NextObject $st]
                        }
                        ::pcbWorkflows::_deleteIter $oIter
                        if { $cnt < 2 } {
                            lappend rows [list $pgName \
                                [DboTclHelper_sGetCPointX $pt] \
                                [DboTclHelper_sGetCPointY $pt] $end]
                        }
                    }
                    set w [$wIter NextWire $st]
                }
                ::pcbWorkflows::_deleteIter $wIter
                set pg [$pIter NextPage $st]
            }
            ::pcbWorkflows::_deleteIter $pIter
            set v [$vIter NextView $st]
        }
        ::pcbWorkflows::_deleteIter $vIter
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "hangingWires: $failed"] }
    return [concat [list OK] $rows]
}

#############################################################################
# libPackages {libFullPath} -- list package names in an OLB.
#
# Needed because PlacePart takes pkgName and device explicitly and fails with
# "ORCAP-1687 Macro Player. Unable to place object" (a BLOCKING popup) if
# either is wrong. Guessing costs a dialog each time; this reads ground truth.
#
# Pattern from capLibraryCorrection/tcl/capLibUtil.tcl:178 -- the iterator
# uses NextName filling a CString, and loop control is [$status Failed],
# not a NULL check.
#############################################################################
proc ::capBridge::libPackages { pList } {
    set libPath [lindex $pList 0]
    if { $libPath eq "" } { return [::capBridge::_err "usage: libPackages {libFullPath}"] }

    set names [list]
    set rc [catch {
        set s $::DboSession_s_pDboSession
        DboSession -this $s
        set st [DboState]
        set libNameCStr [DboTclHelper_sMakeCString $libPath]
        set lib [$s GetLib $libNameCStr $st]
        if { $lib eq "NULL" } {
            error "GetLib returned NULL for '$libPath' (library not open in session?)"
        }
        set it [$lib NewPackageNamesIter $st]
        set nameCStr [DboTclHelper_sMakeCString]
        set st2 [$it NextName $nameCStr]
        while { [$st2 Failed] != 1 } {
            lappend names [DboTclHelper_sGetConstCharPtr $nameCStr]
            set st2 [$it NextName $nameCStr]
        }
    } failed]

    if { $rc != 0 } { return [::capBridge::_err "libPackages: $failed"] }
    return [concat [list OK] $names]
}

# pkgInfo {libFullPath pkgName} -- device / designator / footprint of a package.
# PlacePart needs pkgName AND device; they are not always the same string.
proc ::capBridge::pkgInfo { pList } {
    set libPath [lindex $pList 0]
    set pkgName [lindex $pList 1]
    set out [list]
    set rc [catch {
        set s $::DboSession_s_pDboSession
        DboSession -this $s
        set st [DboState]
        set lib [$s GetLib [DboTclHelper_sMakeCString $libPath] $st]
        if { $lib eq "NULL" } { error "lib not open: $libPath" }
        set pkg [$lib GetPackage [DboTclHelper_sMakeCString $pkgName] $st]
        if { $pkg eq "NULL" } { error "no package '$pkgName'" }
        set c [DboTclHelper_sMakeCString]
        $pkg GetDevice $c
        lappend out device [DboTclHelper_sGetConstCharPtr $c]
        set c2 [DboTclHelper_sMakeCString]
        catch { $pkg GetDesignator $c2 ; lappend out designator [DboTclHelper_sGetConstCharPtr $c2] }
        set c3 [DboTclHelper_sMakeCString]
        catch { $pkg GetPCBFootprint $c3 ; lappend out footprint [DboTclHelper_sGetConstCharPtr $c3] }
    } failed]
    if { $rc != 0 } { return [::capBridge::_err "pkgInfo: $failed"] }
    return [concat [list OK] $out]
}

#############################################################################
# pins -- every part's pins with their connection points.
#
# GetHotSpot is the point a wire must land on. Coordinates come back in
# DATABASE units (1/100 inch); the command layer (PlaceWire, SelectObject)
# wants INCHES, so divide by 100 before issuing commands.
#
# Returns: {OK {refdes pinNumber x y} ...}
#############################################################################
proc ::capBridge::pins { pList } {
    set d [::pcbWorkflows::_getActiveDesign]
    if { $d eq "NULL" } { return [::capBridge::_err "no active design"] }
    set rows [list]
    set rc [catch {
        set st [DboState]
        set NULL NULL
        set vi [$d NewViewsIter $st $::IterDefs_SCHEMATICS]
        set v  [$vi NextView $st]
        while { $v != $NULL } {
            set sc [DboViewToDboSchematic $v]
            set pi [$sc NewPagesIter $st]
            set pg [$pi NextPage $st]
            while { $pg != $NULL } {
                set ii [$pg NewPartInstsIter $st]
                set inst [$ii NextPartInst $st]
                while { $inst != $NULL } {
                    set rd [::capBridge::_refDes $inst $st]
                    set pit [$inst NewPinsIter $st]
                    set pin [$pit NextPin $st]
                    while { $pin != $NULL } {
                        set num "?"
                        catch {
                            set c [DboTclHelper_sMakeCString]
                            $pin GetPinNumber $c
                            set num [DboTclHelper_sGetConstCharPtr $c]
                        }
                        set x ""; set y ""
                        catch {
                            set hs [$pin GetHotSpot $st]
                            set x [DboTclHelper_sGetCPointX $hs]
                            set y [DboTclHelper_sGetCPointY $hs]
                        }
                        lappend rows [list $rd $num $x $y]
                        set pin [$pit NextPin $st]
                    }
                    ::pcbWorkflows::_deleteIter $pit
                    set inst [$ii NextPartInst $st]
                }
                ::pcbWorkflows::_deleteIter $ii
                set pg [$pi NextPage $st]
            }
            ::pcbWorkflows::_deleteIter $pi
            set v [$vi NextView $st]
        }
        ::pcbWorkflows::_deleteIter $vi
    } failed]
    if { $rc != 0 } { return [::capBridge::_err "pins: $failed"] }
    return [concat [list OK] $rows]
}
