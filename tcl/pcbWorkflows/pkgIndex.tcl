#################################################################################
# pkgIndex.tcl
# Package index for pcbWorkflows
#
# INSTALL LOCATION:
#   $CDS_ROOT\tools\capture\tclscripts\pcbWorkflows\pkgIndex.tcl
#
# Capture automatically sources all pkgIndex.tcl files in subdirectories of
# tclscripts at startup, making the pcbWorkflows package available for
# "package require pcbWorkflows" calls throughout the session.
#################################################################################

package ifneeded pcbWorkflows 1.0 [list source [file join $dir pcbWorkflows.tcl]]
