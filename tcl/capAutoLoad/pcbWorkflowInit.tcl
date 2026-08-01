#################################################################################
# pcbWorkflowInit.tcl
# PCB Design Workflow Automation - Auto-load Initialization
#
# INSTALL LOCATION:
#   $CDS_ROOT\tools\capture\tclscripts\capAutoLoad\pcbWorkflowInit.tcl
#
# This file is auto-sourced by OrCAD Capture at every startup via the
# capAutoLoad mechanism. It ONLY registers menu items - no heavy computation.
# All actual logic resides in the pcbWorkflows package (lazy-loaded on demand).
#
# MENU STRUCTURE created under Accessories:
#   Accessories > PCB Workflows > Pre-Netlist Readiness Check
#   Accessories > PCB Workflows > High-Speed Net Audit
#   Accessories > PCB Workflows > BOM Quality Scrubber
#   Accessories > PCB Workflows > Net Naming Audit
#   Accessories > PCB Workflows > ---- (separator via disabled item)
#   Accessories > PCB Workflows > About / Help
#################################################################################

package require Tcl 8.4

namespace eval ::pcbWorkflowMenu {
    proc capTrue {} { return 1 }
}

# --- Design-level menu callbacks (receive pDesign handle) ---
# These are active when the Project Manager window is focused on a design.

proc ::pcbWorkflowMenu::addDesignMenus {} {
    AddAccessoryMenu "PCB Workflows" "Pre-Netlist Readiness Check" \
        "::pcbWorkflowMenu::runPreNetlistCheck"
    AddAccessoryMenu "PCB Workflows" "BOM Quality Scrubber" \
        "::pcbWorkflowMenu::runBomScrubber"
    AddAccessoryMenu "PCB Workflows" "High-Speed Net Audit" \
        "::pcbWorkflowMenu::runHSNetAudit"
    AddAccessoryMenu "PCB Workflows" "Net Naming Audit" \
        "::pcbWorkflowMenu::runNetNamingAudit"
}

# --- Schematic page-level menu callbacks (receive pPage, pOcc handles) ---
# These appear when a schematic page is the active window.

proc ::pcbWorkflowMenu::addPageMenus {} {
    AddAccessoryMenu "PCB Workflows" "Pre-Netlist Readiness Check" \
        "::pcbWorkflowMenu::runPreNetlistCheckFromPage"
    AddAccessoryMenu "PCB Workflows" "BOM Quality Scrubber" \
        "::pcbWorkflowMenu::runBomScrubberFromPage"
    AddAccessoryMenu "PCB Workflows" "High-Speed Net Audit" \
        "::pcbWorkflowMenu::runHSNetAuditFromPage"
    AddAccessoryMenu "PCB Workflows" "Net Naming Audit" \
        "::pcbWorkflowMenu::runNetNamingAuditFromPage"
}

# --- Dispatch procedures: lazy-load the package then call the real proc ---
# Design-context dispatchers (single arg: pDesign)

proc ::pcbWorkflowMenu::runPreNetlistCheck { pDesign } {
    package require pcbWorkflows
    ::pcbWorkflows::preNetlistCheck $pDesign
}

proc ::pcbWorkflowMenu::runBomScrubber { pDesign } {
    package require pcbWorkflows
    ::pcbWorkflows::bomScrubber $pDesign
}

proc ::pcbWorkflowMenu::runHSNetAudit { pDesign } {
    package require pcbWorkflows
    ::pcbWorkflows::hsNetAudit $pDesign
}

proc ::pcbWorkflowMenu::runNetNamingAudit { pDesign } {
    package require pcbWorkflows
    ::pcbWorkflows::netNamingAudit $pDesign
}

# Page-context dispatchers (two args: pPage, pOcc)
# These resolve the active design from the page object and call the same workflow.

proc ::pcbWorkflowMenu::runPreNetlistCheckFromPage { pPage pOcc } {
    package require pcbWorkflows
    set lStatus [DboState]
    set lSession $::DboSession_s_pDboSession
    DboSession -this $lSession
    set lDesign [$lSession GetActiveDesign]
    $lStatus -delete
    ::pcbWorkflows::preNetlistCheck $lDesign
}

proc ::pcbWorkflowMenu::runBomScrubberFromPage { pPage pOcc } {
    package require pcbWorkflows
    set lSession $::DboSession_s_pDboSession
    DboSession -this $lSession
    set lStatus [DboState]
    set lDesign [$lSession GetActiveDesign]
    $lStatus -delete
    ::pcbWorkflows::bomScrubber $lDesign
}

proc ::pcbWorkflowMenu::runHSNetAuditFromPage { pPage pOcc } {
    package require pcbWorkflows
    set lStatus [DboState]
    set lSession $::DboSession_s_pDboSession
    DboSession -this $lSession
    set lDesign [$lSession GetActiveDesign]
    $lStatus -delete
    ::pcbWorkflows::hsNetAudit $lDesign
}

proc ::pcbWorkflowMenu::runNetNamingAuditFromPage { pPage pOcc } {
    package require pcbWorkflows
    set lStatus [DboState]
    set lSession $::DboSession_s_pDboSession
    DboSession -this $lSession
    set lDesign [$lSession GetActiveDesign]
    $lStatus -delete
    ::pcbWorkflows::netNamingAudit $lDesign
}

# --- Register the menu creation actions ---
# These fire when Capture builds its Accessories menu for the respective context.

RegisterAction "_cdnCapTclAddDesignCustomMenu" \
    "::pcbWorkflowMenu::capTrue" "" \
    "::pcbWorkflowMenu::addDesignMenus" ""

RegisterAction "_cdnCapTclAddPageCustomMenu" \
    "::pcbWorkflowMenu::capTrue" "" \
    "::pcbWorkflowMenu::addPageMenus" ""
