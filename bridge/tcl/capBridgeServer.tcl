#############################################################################
# capBridgeServer.tcl -- loopback-only start for Capture's Communication Server
#
# SECURITY: ::capCommServer::StartServer calls
#
#     socket -server ::capCommServer::DoServerAccept $port
#
# with no -myaddr, so TCL binds ALL interfaces. Verified on this machine:
#
#     TCP    0.0.0.0:9020    LISTENING
#     TCP    [::]:9020       LISTENING
#
# The dispatcher runs `$procName $arguments` with no namespace restriction,
# and `eval` satisfies its one-argument convention -- so any host that can
# reach port 9020 can execute arbitrary TCL inside Capture, which means
# arbitrary file access with the user's privileges. There is no
# authentication of any kind.
#
# This module starts the SAME server with the SAME accept handler, but bound
# to 127.0.0.1 so only this machine can connect. It keeps its own channel
# variable rather than reusing ::capCommServer::mSocketChannel, so it cannot
# corrupt the state of a server started the normal way.
#############################################################################

package require capCommServer

namespace eval ::capBridgeServer {
    variable chan 0
    variable port 0
}

proc ::capBridgeServer::isRunning { pList } {
    variable chan
    return [list OK [expr {$chan ne "0"}]]
}

# startLocal {?port?} -- bind loopback only. Default port 9020.
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
