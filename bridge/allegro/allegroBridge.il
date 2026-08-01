;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; allegroBridge.il — external control channel for Allegro PCB Editor 17.4
;;
;; SKILL has NO socket support (verified: nothing socket-related anywhere in
;; doc/skipcref or doc/algroskill). It does have ipcBeginProcess, which starts
;; a child process wired to stdin/stdout/stderr. So the child owns the socket
;; and this side talks to it over pipes:
;;
;;   client --TCP 9030--> allegro_helper.py --stdout--> abDataHandler
;;                              ^                            | evalstring
;;                              +------ ipcWriteProcess ------+
;;
;; USAGE — at the Skill> prompt (type `skill` at Command: first):
;;
;;   load("<repo>/bridge/allegro/allegroBridge.il")
;;   abStart()
;;
;; <repo> is this repository's root. If the environment variable
;; CADENCE_PCB_REPO is set, this file finds its own Python helper from it and
;; no editing is needed; see abRepoRoot below.
;;
;; Then from outside:  python bridge/allegro/allegro_client.py "axlDBGetDesign()"
;;
;; Stop with abStop(). Check with abStatus().
;;
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; DESIGN NOTES
;;
;; * Responses must be ONE LINE. The helper does one readline per exchange,
;;   so an embedded newline desynchronizes everything after it. abFlatten
;;   collapses newlines before sending.
;;
;; * Data does NOT arrive line-aligned. ipcBeginProcess hands the data handler
;;   whatever chunk the OS delivered, which may be a partial line or several
;;   lines at once. abDataHandler therefore buffers and only evaluates on a
;;   complete newline-terminated command.
;;
;; * Every evaluation is wrapped in errset so a bad expression returns an
;;   error string instead of unwinding through the IPC callback, which would
;;   likely take Allegro with it.
;;
;; * Deliberately NOT modelled on Capture's PlaceWire mistake: nothing here
;;   invokes interactive/modal commands. axlShell() runs native commands
;;   non-interactively; interactive placement from a callback is exactly the
;;   pattern that crashed Capture six times.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

abChild   = nil            ; child process id from ipcBeginProcess
abBuf     = ""             ; partial-line accumulator
abPort    = 9030
abPython  = "python"

;; Repo root. Prefer the global set by allegro.ilinit, fall back to the
;; environment. No path is hard-coded: this file is deployed verbatim on
;; every machine, so a baked-in absolute path would be wrong everywhere but
;; one. Returns nil if neither source is available -- abStart reports that.
procedure( abRepoRoot()
    or( and(boundp('pcbRepo) pcbRepo)
        getShellEnvVar("CADENCE_PCB_REPO") )
)

;; The Python helper that owns the socket, and the bridge log.
;; The log goes under %HOME% (Cadence's own variable, always present in a
;; running Allegro) rather than the repo, so a read-only checkout still works.
procedure( abHelperPath()
    let( (root)
        root = abRepoRoot()
        and(root strcat(root "/bridge/allegro/allegro_helper.py"))
    )
)

procedure( abLogPath()
    let( (home)
        home = or(getShellEnvVar("HOME") ".")
        strcat(home "/allegro_bridge.log")
    )
)

;; Collapse a value to a single line so it cannot desync the stream.
procedure( abFlatten( v )
    let( (s)
        s = errset(sprintf(nil "%L" v))
        s = if( s car(s) "<unprintable>" )
        ;; A literal newline escape is fine here -- this is a source
        ;; payload, so there is no quoting hazard to avoid.
        buildString(parseString(s "\n") " ")
    )
)

;; Evaluate one command string and return a single-line result.
procedure( abEval( cmd )
    let( (r)
        r = errset(evalstring(cmd) t)
        if( r
            then abFlatten(car(r))
            else sprintf(nil "ERROR %s" abFlatten(errset.errset))
        )
    )
)

;; Never let anything escape into the IPC callback: an uncaught error there
;; kills the handler with no response, and the client just times out.
procedure( abSafeEval( line )
    let( (r)
        r = errset(abEval(line))
        if( r car(r) "ERROR internal failure in abEval" )
    )
)

;; Called by ipcBeginProcess whenever the helper writes to stdout.
;; Buffers, then evaluates each complete line.
procedure( abDataHandler( cid data )
    let( (nl idx line)
        abBuf = strcat(abBuf data)
        nl = "\n"
        while( (idx = index(abBuf nl))
            ;; index() returns the tail starting at the match; compute the
            ;; prefix length from the length difference.
            line = substring(abBuf 1 (strlen(abBuf) - strlen(idx)))
            ;; substring past the end returns NIL, not "". When the newline is
            ;; the last character -- i.e. every well-formed request -- abBuf
            ;; became nil and the NEXT call's strcat(abBuf data) threw inside
            ;; the IPC callback, killing the handler silently. Command 1 always
            ;; worked, command 2 always hung. Normalise nil back to "".
            abBuf = substring(idx 2)
            unless( abBuf abBuf = "" )
            line = abTrim(line)
            when( line && nequal(line "")
                ipcWriteProcess(cid strcat(abSafeEval(line) nl))
            )
        )
        t
    )
)

procedure( abTrim( s )
    let( (r)
        r = if( s s "" )
        while( r && (strlen(r) > 0) &&
               member(substring(r strlen(r) 1) list(" " "\t" "\r"))
            r = substring(r 1 (strlen(r) - 1))
        )
        r
    )
)

procedure( abErrHandler( cid data )
    printf("allegroBridge[helper stderr]: %s\n" data)
    t
)

procedure( abPostFunc( cid )
    printf("allegroBridge: helper process exited\n")
    abChild = nil
    t
)

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; Control
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

procedure( abStart( @optional (port nil) )
    when( port abPort = port )
    if( abChild
        then
            printf("allegroBridge: already running (child %L)\n" abChild)
            abChild
        else
            let( (cmd helper)
                helper = abHelperPath()
                cond(
                    ;; Distinguish the two failure modes: not configured at all,
                    ;; versus configured but pointing somewhere wrong. Both are
                    ;; easy to fix once named, and impossible to guess otherwise.
                    ( !helper
                        printf("allegroBridge: CADENCE_PCB_REPO is not set -- cannot locate allegro_helper.py\n")
                        printf("allegroBridge:   setx CADENCE_PCB_REPO \"C:/path/to/cadence-design-automation\"\n")
                        nil )
                    ( !isFile(helper)
                        printf("allegroBridge: helper not found at %s\n" helper)
                        printf("allegroBridge: check CADENCE_PCB_REPO points at the repo root\n")
                        nil )
                    ( t
                        cmd = sprintf(nil "%s %s %d" abPython helper abPort)
                        printf("allegroBridge: starting: %s\n" cmd)
                        abBuf = ""
                        abChild = ipcBeginProcess(cmd "" 'abDataHandler 'abErrHandler 'abPostFunc abLogPath())
                        if( abChild
                            then printf("allegroBridge: LISTENING on 127.0.0.1:%d (child %L)\n" abPort abChild)
                            else printf("allegroBridge: FAILED to start helper\n")
                        )
                        abChild )
                )
            )
    )
)

procedure( abStop()
    if( abChild
        then
            ipcKillProcess(abChild)
            abChild = nil
            printf("allegroBridge: stopped\n")
            t
        else
            printf("allegroBridge: not running\n")
            nil
    )
)

procedure( abStatus()
    printf("allegroBridge: child=%L port=%d alive=%L\n"
           abChild abPort (if abChild ipcIsAliveProcess(abChild) nil))
    t
)

;; Convenience for testing from the Skill> prompt without a client.
procedure( abSelfTest()
    printf("abEval test -> %s\n" abEval("strcat(\"hello \" \"world\")"))
    printf("abEval math -> %s\n" abEval("1+2"))
    t
)

printf("\n=== allegroBridge.il loaded ===\n")
printf("  abStart()     start helper + socket on 127.0.0.1:%d\n" abPort)
printf("  abStatus()    show state\n")
printf("  abStop()      stop helper\n")
printf("  abSelfTest()  evaluate two expressions locally (no socket)\n\n")
