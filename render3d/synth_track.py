#!/usr/bin/env python3
"""synth_track.py -- a synth-swell soundtrack for the board build-up clip, and the mux.

    python render3d/synth_track.py <video.mp4> [--out <video_music.mp4>] [--wav track.wav]

No samples, no DAW: numpy oscillators, one-pole filters, a Schroeder reverb and a
ping-pong delay, rendered at 48 kHz stereo and muxed with the bundled ffmpeg (AAC).

The cue sheet follows the phases board_anim.py produces at 24 fps:

    0.0  bare            low drone fades in
    0.5  parts land      slow ascending arpeggio, filter starts opening
    3.2  nets route      arpeggio doubles, noise riser builds to the reveal
    8.0  reveal          chord hit + sub thump, filter fully open, long tail
    9.3  zoom in         shimmer pad, arpeggio thins out
   13.4  final hold      resolving chord swell, fade to silence at the end

Edit CUES if the clip's timing changes; everything else is derived from it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import wave

import numpy as np
from scipy.signal import lfilter

SR = 48000
CUES = {"parts": 0.5, "nets": 3.17, "reveal": 8.0, "zoom": 9.33, "resolve": 13.4}


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def env(dur, a, d, s, r, hold=None):
    """ADSR as a numpy curve. hold = seconds before release starts (default dur - r)."""
    n = int(dur * SR)
    hold = dur - r if hold is None else hold
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-4), 1.0)
    e = np.where((t >= a) & (t < a + d), 1 - (1 - s) * (t - a) / max(d, 1e-4), e)
    e = np.where((t >= a + d) & (t < hold), s, e)
    tail = np.clip((t - hold) / max(r, 1e-4), 0, 1)
    e = np.where(t >= hold, s * (1 - tail), e)
    return e


def saw(freq, dur, detune_cents=0.0, phase=0.0):
    f = freq * 2 ** (detune_cents / 1200)
    t = t_axis(dur)
    return 2 * ((t * f + phase) % 1.0) - 1


def lowpass_sweep(x, cutoff):
    """One-pole lowpass with a per-sample cutoff array (Hz)."""
    cutoff = np.broadcast_to(cutoff, x.shape)
    g = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):            # 48k * 15 s = 720k iterations: ~1 s, fine
        acc = (1 - g[i]) * x[i] + g[i] * acc
        y[i] = acc
    return y


def lowpass(x, cutoff):
    g = np.exp(-2 * np.pi * cutoff / SR)
    return lfilter([1 - g], [1, -g], x)


def delay(x, secs, fb, mix):
    n = int(secs * SR)
    y = np.copy(x)
    buf = np.zeros(len(x) + n)
    buf[:len(x)] = x
    for i in range(n, len(buf)):
        buf[i] += fb * buf[i - n]
    return (1 - mix) * y + mix * buf[:len(x)]


def reverb(x, size=1.0, mix=0.35):
    """Schroeder: four combs in parallel, two allpasses in series."""
    out = np.zeros_like(x)
    for ms, g in ((29.7, 0.805), (37.1, 0.827), (41.1, 0.783), (43.7, 0.764)):
        n = int(ms * size * SR / 1000)
        out += lfilter([1], np.r_[1, np.zeros(n - 1), -g], x)
    for ms, g in ((5.0, 0.7), (1.7, 0.7)):
        n = int(ms * SR / 1000)
        out = lfilter(np.r_[-g, np.zeros(n - 1), 1], np.r_[1, np.zeros(n - 1), -g], out)
    return (1 - mix) * x + mix * out / 4


def place(mix, sig, at, gain=1.0):
    i = int(at * SR)
    j = min(len(mix), i + len(sig))
    mix[i:j] += gain * sig[: j - i]


def build(total):
    N = int(total * SR)
    L = np.zeros(N)
    R = np.zeros(N)
    t = t_axis(total)

    # --- drone: detuned saws an octave apart, cutoff opens from 150 Hz to 2.8 kHz at the reveal
    cut = np.interp(t, [0, CUES["parts"], CUES["nets"], CUES["reveal"] - 0.05, CUES["reveal"], total],
                    [150, 220, 600, 1400, 2800, 1800])
    for ch, det in ((L, -6), (R, +6)):
        d = saw(midi(45), total, det) + 0.6 * saw(midi(33), total, det / 2) + 0.5 * saw(midi(52), total, det * 1.5)
        d = lowpass_sweep(d, cut) * env(total, 1.2, 0, 1, 1.4) * 0.22
        ch += d

    # --- arpeggio: A minor pentatonic climbing, pluck envelopes, pace doubles at the nets phase
    scale = [57, 60, 62, 64, 67, 69, 72, 74, 76, 79, 81, 84, 86, 88, 91]
    k = 0
    tt = CUES["parts"]
    while tt < CUES["zoom"] + 1.5:
        rate = 7.0 if tt < CUES["nets"] else 13.0
        if tt > CUES["zoom"]:
            rate = 5.0
        idx = (k + (k // 3)) % len(scale)
        if tt > CUES["nets"]:
            idx = min(idx + 3, len(scale) - 1)
        f = midi(scale[idx])
        dur = 0.8
        note = (saw(f, dur, -4) + saw(f, dur, 4) + 0.5 * np.sin(2 * np.pi * f * t_axis(dur)))
        note = lowpass(note, 1800 + 6 * f) * env(dur, 0.004, 0.25, 0.0, 0.1, hold=0.26)
        amp = 0.10 if tt < CUES["nets"] else 0.085
        if tt > CUES["zoom"]:
            amp = 0.05
        pan = 0.5 + 0.4 * np.sin(k * 0.9)
        place(L, note, tt, amp * (1 - pan) * 1.6)
        place(R, note, tt, amp * pan * 1.6)
        tt += 1.0 / rate
        k += 1

    # --- riser: filtered noise, bandpass centre climbing into the reveal
    rd = CUES["reveal"] - CUES["nets"]
    rn = np.random.default_rng(7).standard_normal(int(rd * SR))
    rt = t_axis(rd)
    rc = np.interp(rt, [0, rd], [300, 6000])
    riser = lowpass_sweep(rn, rc) - lowpass_sweep(rn, rc * 0.5)
    riser *= (rt / rd) ** 2.2 * 0.5
    place(L, riser, CUES["nets"], 0.9)
    place(R, riser, CUES["nets"], 1.1)

    # --- reveal: chord hit (A add9), slow bloom, long tail + sub thump
    chord = [45, 52, 57, 60, 64, 71, 76]
    cd = total - CUES["reveal"]
    hit = np.zeros(int(cd * SR))
    for n in chord:
        f = midi(n)
        hit += saw(f, cd, -5) + saw(f, cd, 5) + 0.8 * np.sin(2 * np.pi * f * t_axis(cd))
    hit = lowpass(hit, 3200) * env(cd, 0.06, 1.8, 0.35, 2.5, hold=cd - 2.5) * 0.065
    place(L, hit, CUES["reveal"], 1.0)
    place(R, hit, CUES["reveal"], 1.0)
    th = np.sin(2 * np.pi * np.cumsum(np.interp(t_axis(0.5), [0, 0.5], [90, 40])) / SR) * env(0.5, 0.005, 0.4, 0, 0.1, hold=0.4)
    place(L, th, CUES["reveal"], 0.5)
    place(R, th, CUES["reveal"], 0.5)

    # --- shimmer pad for the zoom: high sines with slow vibrato, swells in and out
    zd = CUES["resolve"] - CUES["zoom"] + 1.0
    zt = t_axis(zd)
    sh = np.zeros(int(zd * SR))
    # No vibrato: at these pitches even 0.4 % reads as a shrill "wow-wow". Steady
    # partials, the top one dropped, and a gentle low-pass keep it as air, not a siren.
    for n, w in ((69, 1.0), (76, 0.7), (81, 0.5), (88, 0.3)):
        sh += w * np.sin(2 * np.pi * midi(n) * zt)
    sh = lowpass(sh, 2200) * env(zd, 2.2, 0, 1, 1.8) * 0.03
    place(L, sh, CUES["zoom"], 1.0)
    place(R, sh * np.roll(np.ones_like(sh), 0), CUES["zoom"], 0.9)

    # --- resolve: final swell on the tonic, then everything fades
    fd = total - CUES["resolve"]
    fin = np.zeros(int(fd * SR))
    for n in (45, 57, 64, 69):
        fin += saw(midi(n), fd, -3) + saw(midi(n), fd, 3)
    fin = lowpass(fin, 1500) * env(fd, 0.5, 0, 1, 0.9, hold=fd - 0.9) * 0.05
    place(L, fin, CUES["resolve"], 1.0)
    place(R, fin, CUES["resolve"], 1.0)

    # --- space: ping-pong delay, then reverb, then a master fade and soft clip
    Ld = delay(L, 0.33, 0.35, 0.28)
    Rd = delay(R, 0.44, 0.35, 0.28)
    L, R = reverb(Ld, 1.0, 0.33), reverb(Rd, 1.07, 0.33)
    fade = np.interp(t, [0, 0.4, total - 0.6, total], [0, 1, 1, 0])
    L, R = np.tanh(1.4 * L * fade), np.tanh(1.4 * R * fade)
    peak = max(np.abs(L).max(), np.abs(R).max())
    g = 10 ** (-1.0 / 20) / peak                     # normalise to -1 dBFS
    return L * g, R * g


def write_wav(path, L, R):
    pcm = (np.stack([L, R], axis=1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def mux(video, wav, out):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", video, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)


def video_duration(video):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ff, "-i", video], capture_output=True, text=True)
    import re
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def main(argv):
    if not argv:
        sys.exit(__doc__)
    video = argv[0]
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    stem, ext = os.path.splitext(video)
    out = opt("--out", f"{stem}_music{ext}")
    wav = opt("--wav", f"{stem}_track.wav")
    total = video_duration(video)
    print(f"video {total:.2f} s -> rendering track")
    L, R = build(total)
    write_wav(wav, L, R)
    print("wav", wav, f"peak {20*np.log10(max(np.abs(L).max(), np.abs(R).max())):.1f} dBFS, "
          f"rms {20*np.log10(np.sqrt(np.mean(L**2))):.1f} dBFS")
    mux(video, wav, out)
    print("wrote", out, os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1:])
