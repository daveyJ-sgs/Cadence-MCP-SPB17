"""Encode rendered frame folders into social-ready videos.

    python render3d/make_video.py turntable [--video DIR]   # frames_turntable -> turntable_1080p.mp4 + square + gif
    python render3d/make_video.py reveal    [--video DIR]   # frames_reveal    -> reveal_1080p.mp4
    python render3d/make_video.py combo     [--video DIR]   # reveal + turntable joined with a crossfade

DIR defaults to <render3d.out>/video from board.json. Uses the static ffmpeg that ships with
imageio-ffmpeg (pip install imageio-ffmpeg), so nothing has to be installed system-wide.
H.264, yuv420p, 30 fps, crf 18 plays everywhere; the square crop assumes the subject is
centred, which the renderer guarantees.
"""
from __future__ import annotations
import sys, re, pathlib, argparse, subprocess
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 30


def run(args):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *map(str, args)], check=True)


def encode(frames_dir, out):
    run(["-framerate", FPS, "-i", frames_dir / "f_%04d.png", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-vf", "format=yuv420p", "-movflags", "+faststart", out])
    print(f"  wrote {out} {out.stat().st_size / 1e6:.1f} MB")


def square(src, out):
    run(["-i", src, "-vf", "crop=1080:1080:420:0,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-movflags", "+faststart", out])
    print("  wrote", out)


def gif(src, out, width=720, fps=15):
    pal = out.with_suffix(".palette.png")
    run(["-i", src, "-vf", f"fps={fps},scale={width}:-1:flags=lanczos,palettegen=max_colors=192", pal])
    run(["-i", src, "-i", pal, "-filter_complex",
         f"fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4", out])
    pal.unlink(missing_ok=True)
    print(f"  wrote {out} {out.stat().st_size / 1e6:.1f} MB")


def duration(path):
    probe = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def combo(reveal, turn, out, xfade=0.8):
    off = duration(reveal) - xfade
    run(["-i", reveal, "-i", turn, "-filter_complex",
         f"[0:v][1:v]xfade=transition=fade:duration={xfade}:offset={off:.3f},format=yuv420p[v]",
         "-map", "[v]", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-movflags", "+faststart", out])
    print(f"  wrote {out} {out.stat().st_size / 1e6:.1f} MB")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["turntable", "reveal", "combo"])
    ap.add_argument("--video", help="folder holding frames_* and receiving the mp4s")
    ap.add_argument("--stem", default="board", help="output file name stem")
    a = ap.parse_args(argv)
    video = pathlib.Path(a.video) if a.video else None
    if video is None:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from bridge.allegro import board_profile
        video = pathlib.Path(board_profile.load()["render3d"]["out"]) / "video"
    s = a.stem
    if a.what == "turntable":
        out = video / f"{s}_turntable_1080p.mp4"
        encode(video / "frames_turntable", out)
        square(out, video / f"{s}_turntable_square_1080.mp4")
        gif(out, video / f"{s}_turntable_preview.gif")
    elif a.what == "reveal":
        encode(video / "frames_reveal", video / f"{s}_reveal_1080p.mp4")
    else:
        combo(video / f"{s}_reveal_1080p.mp4", video / f"{s}_turntable_1080p.mp4", video / f"{s}_reveal_and_spin_1080p.mp4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
