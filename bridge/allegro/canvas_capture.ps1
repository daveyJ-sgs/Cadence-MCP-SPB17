# canvas_capture.ps1 -- drive and capture the Allegro 3D Canvas window from outside Allegro.
#
#   pwsh canvas_capture.ps1 -Mode rect                              # print window / viewport rects
#   pwsh canvas_capture.ps1 -Mode size -Width 2400 -Height 1350     # place window at 0,0 with that CLIENT size
#   pwsh canvas_capture.ps1 -Mode capture -Out C:\x\top.png         # one PNG of the 3D viewport
#   pwsh canvas_capture.ps1 -Mode rotate -Dx 40 -Dy 0               # one Shift+middle drag (3D Canvas rotate)
#   pwsh canvas_capture.ps1 -Mode pan -Dx 40 -Dy 0                  # one middle drag (pan)
#   pwsh canvas_capture.ps1 -Mode zoom -Clicks 3                    # mouse wheel at viewport centre (+in / -out)
#   pwsh canvas_capture.ps1 -Mode frames -Frames 300 -TotalPx 1800 -Ease -Dir C:\x\frames
#   pwsh canvas_capture.ps1 -Mode close                             # WM_CLOSE to the canvas window
#
# WHY SCREEN GRAB: PrintWindow returns a blank bitmap for Cadence canvases (see
# docs/allegro_api_notes.md s14), so the viewport is copied from the screen with
# the window pinned TOPMOST for the duration and restored afterwards.
#
# WHY mouse_event: 3D Canvas rotates on Shift + MIDDLE drag and pans on a plain
# middle drag. No MCP tool does a middle-button drag, so the drag is synthesised
# at the OS level. The cursor is parked at the viewport centre first.

param(
  [ValidateSet("rect","size","capture","rotate","pan","zoom","frames","front","close","key")] [string]$Mode = "rect",
  [string]$Title = "Allegro 3D Canvas",
  [string]$Out = "capture.png",
  [string]$Dir = "frames",
  [int]$Width = 1920, [int]$Height = 1080, [int]$X = 0, [int]$Y = 0,
  [int]$Frames = 180, [int]$StepPx = 6, [int]$TotalPx = 0, [switch]$Ease,
  [int]$Dx = 0, [int]$Dy = 0, [int]$Clicks = 1,
  [int]$SettleMs = 300, [int]$Start = 0
)

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
if (-not ("W3D" -as [type])) {
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices; using System.Text;
public class W3D {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr hp, EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, int d, UIntPtr e);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte sc, uint f, UIntPtr e);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
}
"@
}
[W3D]::SetProcessDPIAware() | Out-Null

function Get-CanvasHwnd {
  $found = [System.Collections.ArrayList]::new()
  $cb = [W3D+EnumProc]{ param($h, $l)
    if ([W3D]::IsWindowVisible($h)) {
      $sb = [System.Text.StringBuilder]::new(512); [W3D]::GetWindowText($h, $sb, 512) | Out-Null
      if ($sb.ToString() -like "*$script:Title*") { [void]$found.Add($h) }
    }
    $true }
  [W3D]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
  if ($found.Count -eq 0) { throw "no visible window with title containing '$Title'" }
  return [IntPtr]$found[0]
}

function Get-ScreenRect([IntPtr]$h) {
  $r = New-Object W3D+RECT; [W3D]::GetWindowRect($h, [ref]$r) | Out-Null; return $r
}

function Get-ClientScreenRect([IntPtr]$h) {
  $c = New-Object W3D+RECT; [W3D]::GetClientRect($h, [ref]$c) | Out-Null
  $p = New-Object W3D+POINT; $p.X = 0; $p.Y = 0; [W3D]::ClientToScreen($h, [ref]$p) | Out-Null
  $r = New-Object W3D+RECT; $r.L = $p.X; $r.T = $p.Y; $r.R = $p.X + $c.R; $r.B = $p.Y + $c.B; return $r
}

# The 3D viewport is the largest visible child window of the canvas frame.
function Get-ViewportRect([IntPtr]$h) {
  $script:best = $null; $script:bestA = 0
  $cb = [W3D+EnumProc]{ param($ch, $l)
    if ([W3D]::IsWindowVisible($ch)) {
      $r = New-Object W3D+RECT; [W3D]::GetWindowRect($ch, [ref]$r) | Out-Null
      $a = ($r.R - $r.L) * ($r.B - $r.T)
      if ($a -gt $script:bestA) { $script:bestA = $a; $script:best = $r }
    }
    $true }
  [W3D]::EnumChildWindows($h, $cb, [IntPtr]::Zero) | Out-Null
  $client = Get-ClientScreenRect $h
  $ca = ($client.R - $client.L) * ($client.B - $client.T)
  if ($script:best -ne $null -and $script:bestA -gt 0.3 * $ca) { return $script:best }
  return $client
}

function Set-Front([IntPtr]$h, [bool]$topmost) {
  if ($topmost) { [W3D]::SetWindowPos($h, [IntPtr](-1), 0,0,0,0, 0x0043) | Out-Null }   # HWND_TOPMOST
  else          { [W3D]::SetWindowPos($h, [IntPtr](-2), 0,0,0,0, 0x0043) | Out-Null }   # HWND_NOTOPMOST
  [W3D]::SetForegroundWindow($h) | Out-Null
}

function Capture-Rect($r, [string]$path) {
  $w = $r.R - $r.L; $h = $r.B - $r.T
  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $w, $h))
  $dir = Split-Path $path; if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}

function Center($vp) { return @([int](($vp.L + $vp.R) / 2), [int](($vp.T + $vp.B) / 2)) }

# Middle-button drag across the viewport centre; with $shift it is a rotate, without it is a pan.
function Drag-Canvas($vp, [int]$dx, [int]$dy, [bool]$shift) {
  $c = Center $vp; $cx = $c[0]; $cy = $c[1]
  [W3D]::SetCursorPos($cx, $cy) | Out-Null; Start-Sleep -Milliseconds 40
  if ($shift) { [W3D]::keybd_event(0x10, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 20 }   # VK_SHIFT down
  [W3D]::mouse_event(0x0020, 0, 0, 0, [UIntPtr]::Zero)     # MOUSEEVENTF_MIDDLEDOWN
  $steps = [Math]::Max(2, [int](([Math]::Abs($dx) + [Math]::Abs($dy)) / 3))
  for ($i = 1; $i -le $steps; $i++) {
    [W3D]::SetCursorPos($cx + [int]($dx * $i / $steps), $cy + [int]($dy * $i / $steps)) | Out-Null
    Start-Sleep -Milliseconds 6
  }
  Start-Sleep -Milliseconds 20
  [W3D]::mouse_event(0x0040, 0, 0, 0, [UIntPtr]::Zero)     # MOUSEEVENTF_MIDDLEUP
  if ($shift) { [W3D]::keybd_event(0x10, 0, 2, [UIntPtr]::Zero) }                                  # VK_SHIFT up
}

function Wheel-Canvas($vp, [int]$clicks) {
  $c = Center $vp
  [W3D]::SetCursorPos($c[0], $c[1]) | Out-Null; Start-Sleep -Milliseconds 40
  $n = [Math]::Abs($clicks); $d = if ($clicks -ge 0) { 120 } else { -120 }
  for ($i = 0; $i -lt $n; $i++) { [W3D]::mouse_event(0x0800, 0, 0, $d, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60 }   # MOUSEEVENTF_WHEEL
}

$h = Get-CanvasHwnd
switch ($Mode) {
  "rect" {
    $w = Get-ScreenRect $h; $c = Get-ClientScreenRect $h; $v = Get-ViewportRect $h
    "hwnd     $h"
    "window   L=$($w.L) T=$($w.T) R=$($w.R) B=$($w.B)  ($($w.R-$w.L) x $($w.B-$w.T))"
    "client   L=$($c.L) T=$($c.T) R=$($c.R) B=$($c.B)  ($($c.R-$c.L) x $($c.B-$c.T))"
    "viewport L=$($v.L) T=$($v.T) R=$($v.R) B=$($v.B)  ($($v.R-$v.L) x $($v.B-$v.T))"
  }
  "front" { Set-Front $h $false; "raised" }
  "close" { [W3D]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null; "closed $h" }
  "key" {
    # Press a virtual-key code $Clicks times with the cursor parked over the viewport
    # (numpad view keys: VK_NUMPAD0..9 = 0x60..0x69). -Dx carries the VK code.
    Set-Front $h $false; Start-Sleep -Milliseconds 150
    $v = Get-ViewportRect $h; $c = Center $v; [W3D]::SetCursorPos($c[0], $c[1]) | Out-Null
    for ($i = 0; $i -lt $Clicks; $i++) {
      [W3D]::keybd_event([byte]$Dx, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 30
      [W3D]::keybd_event([byte]$Dx, 0, 2, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
    }
    "pressed vk=0x{0:X} x{1}" -f $Dx, $Clicks
  }
  "size" {
    [W3D]::ShowWindow($h, 9) | Out-Null   # SW_RESTORE
    [W3D]::SetWindowPos($h, [IntPtr]::Zero, $X, $Y, $Width, $Height, 0x0004 -bor 0x0040) | Out-Null   # NOZORDER|SHOWWINDOW
    Start-Sleep -Milliseconds 200
    $w = Get-ScreenRect $h; $c = Get-ClientScreenRect $h
    $fx = ($w.R - $w.L) - ($c.R - $c.L); $fy = ($w.B - $w.T) - ($c.B - $c.T)
    [W3D]::SetWindowPos($h, [IntPtr]::Zero, $X, $Y, $Width + $fx, $Height + $fy, 0x0004 -bor 0x0040) | Out-Null
    Start-Sleep -Milliseconds 300
    $c = Get-ClientScreenRect $h; $v = Get-ViewportRect $h
    "client now $($c.R-$c.L) x $($c.B-$c.T) at $($c.L),$($c.T); viewport $($v.R-$v.L) x $($v.B-$v.T)"
  }
  "capture" {
    Set-Front $h $true; Start-Sleep -Milliseconds $SettleMs
    $v = Get-ViewportRect $h; Capture-Rect $v $Out
    Set-Front $h $false
    "saved $Out ($($v.R-$v.L) x $($v.B-$v.T))"
  }
  "rotate" {
    Set-Front $h $false; Start-Sleep -Milliseconds 150
    $v = Get-ViewportRect $h; Drag-Canvas $v $Dx $Dy $true
    "rotated dx=$Dx dy=$Dy"
  }
  "pan" {
    Set-Front $h $false; Start-Sleep -Milliseconds 150
    $v = Get-ViewportRect $h; Drag-Canvas $v $Dx $Dy $false
    "panned dx=$Dx dy=$Dy"
  }
  "zoom" {
    Set-Front $h $false; Start-Sleep -Milliseconds 150
    $v = Get-ViewportRect $h; Wheel-Canvas $v $Clicks
    "wheel clicks=$Clicks"
  }
  "frames" {
    # Orbit: rotate a little, capture, repeat. With -TotalPx the drag budget is
    # spread over the frames (smoothstep-eased when -Ease), so a full turn can
    # be calibrated once and reproduced exactly; otherwise -StepPx per frame.
    if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Force $Dir | Out-Null }
    Set-Front $h $true; Start-Sleep -Milliseconds $SettleMs
    $v = Get-ViewportRect $h
    $acc = 0.0; $done = 0
    for ($i = 0; $i -lt $Frames; $i++) {
      $n = $Start + $i
      if ($i -gt 0) {
        if ($TotalPx -ne 0) {
          $t = $i / ($Frames - 1.0)
          $e = if ($Ease) { $t * $t * (3.0 - 2.0 * $t) } else { $t }
          $target = [int][Math]::Round($TotalPx * $e)
          $dx = $target - $done; $done = $target
        } else { $dx = $StepPx }
        if ($dx -ne 0) { Drag-Canvas $v $dx $Dy $true }
        Start-Sleep -Milliseconds $SettleMs
      }
      Capture-Rect $v (Join-Path $Dir ("frame_{0:D4}.png" -f $n))
    }
    Set-Front $h $false
    "wrote $Frames frames to $Dir starting at $Start ($($v.R-$v.L) x $($v.B-$v.T)); drag total $done px"
  }
}
