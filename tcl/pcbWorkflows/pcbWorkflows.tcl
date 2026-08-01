#################################################################################
# pcbWorkflows.tcl
# PCB Design Workflow Automation - Core Procedures
#
# INSTALL LOCATION:
#   $CDS_ROOT\tools\capture\tclscripts\pcbWorkflows\pcbWorkflows.tcl
#
# Package: pcbWorkflows 1.0
# Requires: DboTclWriteBasic (provided by OrCAD Capture installation)
#
# WORKFLOWS PROVIDED:
#   ::pcbWorkflows::preNetlistCheck  - Full readiness audit before netlisting
#   ::pcbWorkflows::bomScrubber      - BOM field completeness check
#   ::pcbWorkflows::hsNetAudit       - High-speed / differential pair net audit
#   ::pcbWorkflows::netNamingAudit   - Net naming convention compliance check
#
# CONFIGURATION:
#   Edit the "User Configuration" section below to match your design standards.
#################################################################################

package require Tcl 8.4

# Verify the Cadence database TCL layer is available.
# DboTclWriteBasic is loaded internally by Capture at startup - we don't
# load it ourselves (Capture intercepts and ignores redundant load attempts).
# We just verify a known Dbo command exists before proceeding.
# If it's missing for any reason, all logging falls back to puts() safely.
if { [catch { DboTclHelper_sMakeCString "probe" } _probeErr] } {
    puts "pcbWorkflows: Dbo layer not yet available - logging will use Command Window."
    puts "  If this persists, run Tools > Design Rules Check once to initialize"
    puts "  the database layer, then retry."
}

package provide pcbWorkflows 1.0

namespace eval ::pcbWorkflows {

    #===========================================================================
    # USER CONFIGURATION - Edit these to match your design conventions
    #===========================================================================

    # Required part properties - every placed component must have these populated
    # and non-empty. Add or remove fields to match your library standard.
    # NOTE: Capture property names use SPACES, not underscores. Verified live
    # against SCHEMATIC1 by enumerating a part's effective properties:
    # "PCB Footprint" exists and holds e.g. "cap196"; "PCB_Footprint" does not
    # exist at all. Asking for a non-existent name returns "", which this
    # workflow then reported as "Missing PCB Footprint (netlister will abort)"
    # for all 44 parts -- a false positive on every part in the design.
    #
    # "Part Number" and "Manufacturer" genuinely are absent from these parts,
    # so warnings for those are legitimate. They are spelled with spaces here
    # to match Capture's convention for when they do get added.
    variable requiredPartProps {
        {PCB Footprint}
        {Part Number}
        Manufacturer
        Value
    }

    # Placeholder strings that indicate a property was never properly filled in.
    # Any part with one of these as a property value will be flagged.
    variable placeholderValues {
        TBD
        tbd
        ???
        ""
        NONE
        none
        N/A
        TODO
    }

    # High-speed net name patterns (TCL regexp patterns).
    # Nets matching any of these will be included in the HS Net Audit.
    variable hsNetPatterns {
        {(?i)CLK}
        {(?i)_CK$}
        {(?i)DDR}
        {(?i)LPDDR}
        {(?i)SERDES}
        {(?i)LVDS}
        {(?i)PCIE}
        {(?i)USB}
        {(?i)SGMII}
        {(?i)RGMII}
        {(?i)MIPI}
        {(?i)HSIC}
        {(?i)_TX$}
        {(?i)_RX$}
        {(?i)_DP$}
        {(?i)_DN$}
        {(?i)_P$}
        {(?i)_N$}
    }

    # Differential pair suffix pairs {positive_suffix negative_suffix}
    # Used to validate that every _P net has a corresponding _N net.
    variable diffPairSuffixes {
        {_P  _N}
        {_DP _DN}
        {_TX _RX}
        {P   N}
    }

    # Power net naming: power nets should match this pattern (all caps + underscore/digits)
    # Set to "" to skip this check.
    variable powerNetPattern {^[A-Z][A-Z0-9_]+$}

    # Net names that are explicitly allowed to be lowercase (e.g. GND variants)
    variable powerNetExceptions {
        GND
        AGND
        DGND
        PGND
        SHIELD
    }

    #===========================================================================
    # INTERNAL HELPERS
    #===========================================================================

    # All output goes to puts -> Command Window.
    # Safe, reliable, no Tk or Dbo dependencies required.
    # View output: View > Toolbar > Command Window

    proc _logHeader { title } {
        set bar [string repeat "=" 70]
        puts ""
        puts $bar
        puts "  $title"
        puts $bar
    }

    proc _logSection { section } {
        puts ""
        puts "--- $section ---"
    }

    proc _log { msg } {
        puts $msg
    }

    proc _logSummary { errors warnings } {
        set bar [string repeat "-" 70]
        puts ""
        puts $bar
        puts "  SUMMARY:  $errors ERROR(s)   $warnings WARNING(s)"
        puts $bar
        puts ""
    }

    # Get active design from session - returns NULL if none open.
    # NOTE: Do not use 'return' inside catch in a TCL proc - it gets caught
    # as TCL_RETURN. Set a variable before catch, assign inside, return after.
    proc _getActiveDesign {} {
        set lDesign NULL
        catch {
            set lSession $::DboSession_s_pDboSession
            DboSession -this $lSession
            set lStatus [DboState]
            set lDesign [$lSession GetActiveDesign]
        }
        return $lDesign
    }

    # Get design name string
    proc _getDesignName { pDesign } {
        set nameStr "Unknown"
        catch {
            set lName [DboTclHelper_sMakeCString]
            $pDesign GetRootName $lName
            set nameStr [DboTclHelper_sGetConstCharPtr $lName]
        }
        return $nameStr
    }

    # Check if a string value is a placeholder / empty
    proc _isPlaceholder { val } {
        variable placeholderValues
        set trimmed [string trim $val]
        if { $trimmed eq "" } { return 1 }
        foreach ph $placeholderValues {
            if { [string equal -nocase $trimmed $ph] } { return 1 }
        }
        return 0
    }

    # Get a part instance's reference designator.
    #
    # DboPartInst_sGetReference takes TWO arguments (obj, status) and returns
    # a CString POINTER, not a TCL string. The original one-argument form
    # here raised "Wrong number of arguments" on every call; the catch
    # swallowed it and this proc returned "?" for every part, always -- which
    # made Workflow 1 report the entire design as unannotated. Verified
    # 2026-07-27 over the Communication Server bridge against SCHEMATIC1,
    # which is in fact fully annotated.
    #
    # The failure default is deliberately NOT "?": that is a legitimate value
    # for a genuinely unannotated part, so using it for errors makes a broken
    # API call indistinguishable from a real finding. That ambiguity is
    # exactly what hid this bug. "<ERR:refdes>" cannot be mistaken for data.
    #
    # pStatus is optional so existing single-argument callers keep working;
    # pass one in to avoid allocating a DboState per part.
    proc _getRefDes { pInst {pStatus ""} } {
        set val ""
        set ownStatus 0
        set rc [catch {
            if { $pStatus eq "" } {
                set pStatus [DboState]
                set ownStatus 1
            }
            set lRefCStr [DboPartInst_sGetReference $pInst $pStatus]
            set val [DboTclHelper_sGetConstCharPtr $lRefCStr]
        }]
        if { $ownStatus } { catch { $pStatus -delete } }
        if { $rc != 0 } { return "<ERR:refdes>" }
        if { $val eq "" } { return "?" }
        return $val
    }

    # Get a named property value from a part instance (returns "" if not found).
    # GetEffectivePropStringValue fills the output CString param in-place.
    proc _getProp { pInst propName } {
        set val ""
        catch {
            set lPropNameCStr [DboTclHelper_sMakeCString $propName]
            set lPropValCStr  [DboTclHelper_sMakeCString]
            $pInst GetEffectivePropStringValue $lPropNameCStr $lPropValCStr
            set val [DboTclHelper_sGetConstCharPtr $lPropValCStr]
        }
        return $val
    }

    # Get page name string for a page object
    proc _getPageLocation { pPage } {
        set pageName "?"
        catch {
            set lPageName [DboTclHelper_sMakeCString]
            $pPage GetName $lPageName
            set pageName [DboTclHelper_sGetConstCharPtr $lPageName]
        }
        return $pageName
    }

    # Safe iterator delete - use -delete method, not delete_* free functions
    proc _deleteIter { iter } {
        catch { $iter -delete }
    }

    #===========================================================================
    # WORKFLOW 1: PRE-NETLIST READINESS CHECK
    #===========================================================================
    # Iterates every placed part instance across all schematic pages and checks:
    #   - Required properties are present and non-placeholder
    #   - PCB Footprint specifically is populated (netlister will abort without it)
    #   - Reference designator is not still "?" (unannotated)
    # Also checks all nets for single-node conditions.
    # Results written to the Capture Session Log.
    #===========================================================================

    proc preNetlistCheck { {pDesign ""} } {
        if { [catch { _preNetlistCheckImpl $pDesign } err] } {
            puts "pcbWorkflows ERROR in Pre-Netlist Check: $err"
        }
    }

    proc _preNetlistCheckImpl { {pDesign ""} } {
        if { $pDesign eq "" } {
            set pDesign [_getActiveDesign]
        }
        set lNullObj NULL
        if { $pDesign == $lNullObj } {
            _log "ERROR: No active design found. Open a design first."
            return
        }

        set designName [_getDesignName $pDesign]
        _logHeader "PRE-NETLIST READINESS CHECK  |  Design: $designName"

        set errorCount   0
        set warningCount 0
        set partCount    0
        set netCount     0

        # --- Part property checks ---
        _logSection "Part Property Validation"

        set lStatus [DboState]
        set lNullObj NULL

        # Collect all part issues across all pages
        set lViewsIter [$pDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
        set lView [$lViewsIter NextView $lStatus]

        while { $lView != $lNullObj } {
            set lSchematic [DboViewToDboSchematic $lView]
            set lSchName [DboTclHelper_sMakeCString]
            $lSchematic GetName $lSchName
            set schNameStr [DboTclHelper_sGetConstCharPtr $lSchName]

            set lPagesIter [$lSchematic NewPagesIter $lStatus]
            set lPage [$lPagesIter NextPage $lStatus]

            while { $lPage != $lNullObj } {
                set pageNameStr [_getPageLocation $lPage]

                # Iterate all placed part instances on this page
                set lPartsIter [$lPage NewPartInstsIter $lStatus]
                set lInst [$lPartsIter NextPartInst $lStatus]

                while { $lInst != $lNullObj } {
                    incr partCount

                    set refDes [_getRefDes $lInst]
                    set location "$schNameStr/$pageNameStr"

                    # Check for unannotated reference designator
                    # Was: [string match "*\?*" $refDes] -- broken. Inside a
                    # double-quoted TCL word, \? is not a recognized escape,
                    # so TCL strips the backslash and string match receives
                    # the glob "*?*". In glob, ? matches ANY single character,
                    # so this matched every non-empty refdes and flagged all
                    # 44 parts of a fully annotated design as unannotated.
                    # A plain substring search has no such quoting hazard.
                    if { [string first "?" $refDes] >= 0 } {
                        _log "  ERROR  \[$location\]  Unannotated RefDes: $refDes"
                        incr errorCount
                    }

                    # Check each required property
                    variable requiredPartProps
                    foreach prop $requiredPartProps {
                        set val [_getProp $lInst $prop]
                        if { [_isPlaceholder $val] } {
                            if { $prop eq "PCB_Footprint" || $prop eq "PCB Footprint" } {
                                _log "  ERROR  \[$location\]  $refDes : Missing PCB Footprint (netlister will abort)"
                                incr errorCount
                            } else {
                                _log "  WARN   \[$location\]  $refDes : Property '$prop' is empty or placeholder"
                                incr warningCount
                            }
                        }
                    }

                    set lInst [$lPartsIter NextPartInst $lStatus]
                }
                _deleteIter $lPartsIter

                set lPage [$lPagesIter NextPage $lStatus]
            }
            _deleteIter $lPagesIter

            set lView [$lViewsIter NextView $lStatus]
        }
        _deleteIter $lViewsIter

        # --- Net checks: single-node nets ---
        _logSection "Net Connectivity Validation"

        set lFlatNetsIter [$pDesign NewFlatNetsIter $lStatus]
        if { $lFlatNetsIter != $lNullObj } {
            set lFlatNet [$lFlatNetsIter NextFlatNet $lStatus]
            while { $lFlatNet != $lNullObj } {
                incr netCount
                set lNetName [DboTclHelper_sMakeCString]
                $lFlatNet GetName $lNetName
                set netNameStr [DboTclHelper_sGetConstCharPtr $lNetName]

                # Get pin count on this net
                set lPinsIter [$lFlatNet NewPortOccurrencesIter $lStatus]
                set pinCount 0
                set lPort [$lPinsIter NextPortOccurrence $lStatus]
                while { $lPort != $lNullObj } {
                    incr pinCount
                    set lPort [$lPinsIter NextPortOccurrence $lStatus]
                }
                _deleteIter $lPinsIter

                if { $pinCount == 1 } {
                    _log "  WARN   Single-node net (1 pin only): '$netNameStr'"
                    incr warningCount
                } elseif { $pinCount == 0 } {
                    _log "  ERROR  Orphaned net (0 pins): '$netNameStr'"
                    incr errorCount
                }

                set lFlatNet [$lFlatNetsIter NextFlatNet $lStatus]
            }
            _deleteIter $lFlatNetsIter
        }

        $lStatus -delete
        DboTclHelper_sReleaseAllCreatedPtrs

        # Summary
        _log "\n  Parts checked: $partCount"
        _log "  Nets checked:  $netCount"
        _logSummary $errorCount $warningCount

        if { $errorCount == 0 && $warningCount == 0 } {
            _log "  >> Design appears READY for netlist export <<"
        } elseif { $errorCount == 0 } {
            _log "  >> No blocking errors. Review warnings before netlisting. <<"
        } else {
            _log "  >> $errorCount blocking error(s) must be fixed before netlisting. <<"
        }
    } ;# end _preNetlistCheckImpl

    #===========================================================================
    # WORKFLOW 2: BOM QUALITY SCRUBBER
    #===========================================================================
    # Walks all parts and checks BOM-critical fields for placeholder/empty values.
    # Generates a summary table in the session log suitable for copy-paste review.
    #===========================================================================

    proc bomScrubber { {pDesign ""} } {
        if { [catch { _bomScrubberImpl $pDesign } err] } {
            puts "pcbWorkflows ERROR in BOM Scrubber: $err"
        }
    }

    proc _bomScrubberImpl { {pDesign ""} } {
        if { $pDesign eq "" } {
            set pDesign [_getActiveDesign]
        }
        set lNullObj NULL
        if { $pDesign == $lNullObj } {
            _log "ERROR: No active design found."
            return
        }

        set designName [_getDesignName $pDesign]
        _logHeader "BOM QUALITY SCRUBBER  |  Design: $designName"

        # BOM fields to check - adjust to match your database fields
        # Space-separated names, not underscores -- see requiredPartProps.
        set bomFields { Value {Part Number} Manufacturer {PCB Footprint} }

        set lStatus [DboState]
        set issueCount 0
        set partCount  0

        set lViewsIter [$pDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
        set lView [$lViewsIter NextView $lStatus]

        while { $lView != $lNullObj } {
            set lSchematic [DboViewToDboSchematic $lView]
            set lPagesIter [$lSchematic NewPagesIter $lStatus]
            set lPage [$lPagesIter NextPage $lStatus]

            while { $lPage != $lNullObj } {
                set pageNameStr [_getPageLocation $lPage]
                set lPartsIter [$lPage NewPartInstsIter $lStatus]
                set lInst [$lPartsIter NextPartInst $lStatus]

                while { $lInst != $lNullObj } {
                    incr partCount
                    set refDes [_getRefDes $lInst]
                    set issues {}

                    foreach field $bomFields {
                        set val [_getProp $lInst $field]
                        if { [_isPlaceholder $val] } {
                            lappend issues $field
                        }
                    }

                    if { [llength $issues] > 0 } {
                        incr issueCount
                        _log "  $refDes  \[Page: $pageNameStr\]  Missing: [join $issues {, }]"
                    }

                    set lInst [$lPartsIter NextPartInst $lStatus]
                }
                _deleteIter $lPartsIter
                set lPage [$lPagesIter NextPage $lStatus]
            }
            _deleteIter $lPagesIter
            set lView [$lViewsIter NextView $lStatus]
        }
        _deleteIter $lViewsIter

        $lStatus -delete
        DboTclHelper_sReleaseAllCreatedPtrs

        _log "\n  Parts checked: $partCount"
        _logSummary $issueCount 0
        if { $issueCount == 0 } {
            _log "  >> All BOM fields are populated. Design is BOM-ready. <<"
        } else {
            _log "  >> $issueCount part(s) have incomplete BOM data. <<"
        }
    } ;# end _bomScrubberImpl

    #===========================================================================
    # WORKFLOW 3: HIGH-SPEED NET AUDIT
    #===========================================================================
    # Finds all nets matching high-speed patterns, reports connectivity,
    # validates differential pair pairing (every _P has a _N), and flags
    # any diff pair nets that appear to be missing their complement.
    #===========================================================================

    proc hsNetAudit { {pDesign ""} } {
        if { [catch { _hsNetAuditImpl $pDesign } err] } {
            puts "pcbWorkflows ERROR in HS Net Audit: $err"
        }
    }

    proc _hsNetAuditImpl { {pDesign ""} } {
        if { $pDesign eq "" } {
            set pDesign [_getActiveDesign]
        }
        set lNullObj NULL
        if { $pDesign == $lNullObj } {
            _log "ERROR: No active design found."
            return
        }

        set designName [_getDesignName $pDesign]
        _logHeader "HIGH-SPEED NET AUDIT  |  Design: $designName"

        variable hsNetPatterns
        variable diffPairSuffixes

        set lStatus [DboState]
        set hsNets {}       ;# list of {netName pinCount}
        set diffPNets {}    ;# nets that look like diff pair positives
        set diffNNets {}    ;# nets that look like diff pair negatives
        set warningCount 0

        # Iterate flat nets
        set lFlatNetsIter [$pDesign NewFlatNetsIter $lStatus]
        if { $lFlatNetsIter != $lNullObj } {
            set lFlatNet [$lFlatNetsIter NextFlatNet $lStatus]
            while { $lFlatNet != $lNullObj } {
                set lNetName [DboTclHelper_sMakeCString]
                $lFlatNet GetName $lNetName
                set netName [DboTclHelper_sGetConstCharPtr $lNetName]

                # Count pins
                set lPinsIter [$lFlatNet NewPortOccurrencesIter $lStatus]
                set pinCount 0
                set lPort [$lPinsIter NextPortOccurrence $lStatus]
                while { $lPort != $lNullObj } {
                    incr pinCount
                    set lPort [$lPinsIter NextPortOccurrence $lStatus]
                }
                _deleteIter $lPinsIter

                # Check against HS patterns
                set isHS 0
                foreach pattern $hsNetPatterns {
                    if { [regexp $pattern $netName] } {
                        set isHS 1
                        break
                    }
                }

                if { $isHS } {
                    lappend hsNets [list $netName $pinCount]

                    # Check for diff pair membership
                    foreach pair $diffPairSuffixes {
                        set pSuffix [lindex $pair 0]
                        set nSuffix [lindex $pair 1]
                        if { [string match "*${pSuffix}" $netName] } {
                            lappend diffPNets $netName
                        } elseif { [string match "*${nSuffix}" $netName] } {
                            lappend diffNNets $netName
                        }
                    }
                }

                set lFlatNet [$lFlatNetsIter NextFlatNet $lStatus]
            }
            _deleteIter $lFlatNetsIter
        }

        $lStatus -delete
        DboTclHelper_sReleaseAllCreatedPtrs

        # Report HS nets
        _logSection "High-Speed Nets Found ([llength $hsNets] total)"
        foreach netInfo [lsort -index 0 $hsNets] {
            set netName [lindex $netInfo 0]
            set pinCount [lindex $netInfo 1]
            _log "  [format %-40s $netName]  pins: $pinCount"
        }

        # Validate diff pair pairing
        _logSection "Differential Pair Validation"
        foreach pair $diffPairSuffixes {
            set pSuffix [string trim [lindex $pair 0]]
            set nSuffix [string trim [lindex $pair 1]]

            foreach pNet $diffPNets {
                if { [string match "*${pSuffix}" $pNet] } {
                    # Derive expected complement net name
                    set base [string range $pNet 0 end-[string length $pSuffix]]
                    set expectedN "${base}${nSuffix}"
                    if { [lsearch $diffNNets $expectedN] < 0 } {
                        _log "  WARN  Diff pair positive '$pNet' has no matching '$expectedN'"
                        incr warningCount
                    } else {
                        _log "  OK    Pair: $pNet  <-->  $expectedN"
                    }
                }
            }
        }

        _logSummary 0 $warningCount
    } ;# end _hsNetAuditImpl

    #===========================================================================
    # WORKFLOW 4: NET NAMING CONVENTION AUDIT
    #===========================================================================
    # Checks all nets in the design against naming conventions:
    #   - Power nets (connected to PWR pins) should be ALL_CAPS
    #   - System-generated names (N#####) flagged as informational
    #   - Illegal characters (', !, space) flagged as errors
    #===========================================================================

    proc netNamingAudit { {pDesign ""} } {
        if { [catch { _netNamingAuditImpl $pDesign } err] } {
            puts "pcbWorkflows ERROR in Net Naming Audit: $err"
        }
    }

    proc _netNamingAuditImpl { {pDesign ""} } {
        if { $pDesign eq "" } {
            set pDesign [_getActiveDesign]
        }
        set lNullObj NULL
        if { $pDesign == $lNullObj } {
            _log "ERROR: No active design found."
            return
        }

        set designName [_getDesignName $pDesign]
        _logHeader "NET NAMING CONVENTION AUDIT  |  Design: $designName"

        variable powerNetPattern
        variable powerNetExceptions

        set lStatus [DboState]
        set errorCount   0
        set warningCount 0
        set infoCount    0
        set netCount     0

        set lFlatNetsIter [$pDesign NewFlatNetsIter $lStatus]
        if { $lFlatNetsIter != $lNullObj } {
            set lFlatNet [$lFlatNetsIter NextFlatNet $lStatus]
            while { $lFlatNet != $lNullObj } {
                incr netCount
                set lNetName [DboTclHelper_sMakeCString]
                $lFlatNet GetName $lNetName
                set netName [DboTclHelper_sGetConstCharPtr $lNetName]

                # Check for illegal characters
                if { [regexp {['! ]} $netName] } {
                    _log "  ERROR  Illegal characters in net name: '$netName'  (avoid ' ! and spaces)"
                    incr errorCount
                }

                # Flag auto-generated net names (informational only)
                if { [regexp {^N\d{5,}$} $netName] } {
                    _log "  INFO   Auto-generated net name '$netName' - consider adding a net alias"
                    incr infoCount
                }

                # Power net naming check (requires net type info via pin iteration)
                # We approximate: check nets whose name looks like a power supply label
                # but violates the uppercase convention
                if { $powerNetPattern ne "" } {
                    # Flag nets that start with V, v, P, p, 3, 5, 1 (likely power)
                    # but don't match the all-caps pattern
                    if { [regexp {^[VvPp35129]} $netName] && \
                         ![regexp $powerNetPattern $netName] && \
                         [lsearch $powerNetExceptions $netName] < 0 } {
                        _log "  WARN   Possible power net not following ALL_CAPS convention: '$netName'"
                        incr warningCount
                    }
                }

                set lFlatNet [$lFlatNetsIter NextFlatNet $lStatus]
            }
            _deleteIter $lFlatNetsIter
        }

        $lStatus -delete
        DboTclHelper_sReleaseAllCreatedPtrs

        _log "\n  Nets checked: $netCount"
        _log "  Auto-named nets (INFO): $infoCount"
        _logSummary $errorCount $warningCount
    } ;# end _netNamingAuditImpl

} ;# end namespace ::pcbWorkflows
