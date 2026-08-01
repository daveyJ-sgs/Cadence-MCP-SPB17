#############################################################################
# capBridgeServerInit.tcl
#
# Auto-starts Capture's Communication Server on every launch, bound to
# LOOPBACK ONLY, so the bridge is available without typing two commands into
# the Command Window each session.
#
# NOT DEPLOYED YET -- deliberately. Deploy with:
#
#   cp tcl/capAutoLoad/capBridgeServerInit.tcl \
#      "C:/Cadence/SPB_17.4/tools/capture/tclscripts/capAutoLoad/"
#
# then restart Capture and confirm with:
#
#   netstat -ano | grep 9020        # expect 127.0.0.1:9020, NOT 0.0.0.0:9020
#
# To undo, delete the deployed copy. Nothing else is touched.
#
#---------------------------------------------------------------------------
# WHY LOOPBACK MATTERS
#
# ::capCommServer::StartServer calls
#
#     socket -server ::capCommServer::DoServerAccept $port
#
# with no -myaddr, so TCL binds ALL interfaces. Measured on this machine
# while the server was running the normal way:
#
#     TCP    0.0.0.0:9020    LISTENING
#     TCP    [::]:9020       LISTENING
#
# The dispatcher runs `$procName $arguments` with no namespace restriction,
# and `eval` fits its one-argument convention, so ANY host that can reach
# port 9020 can execute arbitrary TCL inside Capture -- arbitrary file access
# with the user's privileges, no authentication anywhere in the path.
#
# Binding 127.0.0.1 limits that to this machine. It is still unauthenticated
# local RPC, so any local process can use it; that is an accepted trade-off
# for a design-automation channel, but it should be a conscious one.
#---------------------------------------------------------------------------
# SAFETY
#
# Everything below is wrapped in catch. A failure here must never block
# Capture from starting -- this file runs at startup, and an uncaught error
# in an auto-loaded script is a bad way to discover a typo.
#############################################################################

proc capBridgeServerInit_start {} {
    if { [catch {

        package require capCommServer

        namespace eval ::capBridgeServer {
            variable chan 0
            variable port 0
        }

        proc ::capBridgeServer::isRunning { pList } {
            variable chan
            return [list OK [expr {$chan ne "0"}]]
        }

        proc ::capBridgeServer::startLocal { pList } {
            variable chan
            variable port
            set p [lindex $pList 0]
            if { $p eq "" } { set p 9020 }
            if { $chan ne "0" } { return [list OK already-running $port] }
            set rc [catch {
                set chan [socket -server ::capCommServer::DoServerAccept -myaddr 127.0.0.1 $p]
                set port $p
            } failed]
            if { $rc != 0 } {
                set chan 0
                return [list ERROR "startLocal: $failed"]
            }
            return [list OK listening 127.0.0.1 $port]
        }

        proc ::capBridgeServer::stopLocal { pList } {
            variable chan
            variable port
            if { $chan eq "0" } { return [list OK not-running] }
            catch { close $chan }
            set chan 0
            set was $port
            set port 0
            return [list OK stopped $was]
        }

        # Bind loopback on the default port. If something else already holds
        # 9020 this returns an ERROR list rather than throwing.
        set result [::capBridgeServer::startLocal {}]
        puts "capBridgeServer: $result"

    } err] } {
        # Never let a startup script break Capture.
        catch { puts "capBridgeServerInit failed (non-fatal): $err" }
    }
}

capBridgeServerInit_start
