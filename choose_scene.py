#!/usr/bin/env python3
"""
choose_scene.py - pick which buffer/scare video pair Video Looper 2 plays.

Library folder (default ~/VideoLibrary) holds pairs named:
    <Name>-Buffer.mp4     looping video
    <Name>-Scare.mp4      played on motion   (-Trigger / -Triggered also accepted)
Names may contain spaces and hyphens, e.g. "Macabre Manor Family Scare-Buffer.mp4".

On selection the pair is re-encoded for the Pi 4 if needed (once; the result is kept
in the library), copied into the looper's video folder with the names it expects,
and the looper is restarted.

Usage (as your normal user, without sudo):
    choose_scene.py                    # interactive menu
    choose_scene.py --list             # list scenes and exit
    choose_scene.py "Jack-O-Lantern"   # select by name, no menu
    choose_scene.py --encode-all       # encode every video in the library not yet encoded
"""
import argparse
import configparser
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

LOOPER_INI = "/boot/video_looper.ini"
LIBRARY = os.path.expanduser("~/VideoLibrary")


def looper_video_dir():
    """Video folder from Video Looper 2's config ([directory] path), else ~/Videos."""
    c = configparser.ConfigParser()
    try:
        c.read(LOOPER_INI)
        path = c.get("directory", "path", fallback="").strip()
    except configparser.Error:
        path = ""
    return path or os.path.expanduser("~/Videos")


VIDEOS = looper_video_dir()
BUFFER_NAME = "0_buffer_repeat_9999x.mp4"
SCARE_NAME = "1_scare.mp4"
CURRENT_FILE = ".current_scene"          # stored in the library folder
TAG = "pi4-looper-encoded"
EXTS = (".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".mpg", ".mpeg", ".wmv", ".ts")
# "<Name><sep><Role>[<extra>]" - sep may be - _ space or a typographic dash; the LAST role
# word wins, so names may contain "Scare"; anything after the role (e.g. " 1080p") is ignored.
ROLE_RE = re.compile(
    r"^(?P<name>.+)[\s_\-\u2013\u2014]+(?P<role>buffer|scare|triggered|trigger)"
    r"(?:[\s_\-\u2013\u2014(\[.].*)?$", re.I)


def scan(library):
    """Find pairs in the library and its subfolders. Returns (complete, incomplete, ignored)."""
    scenes, ignored = {}, []
    for root, dirs, files in os.walk(library):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in sorted(files):
            if f.startswith("."):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, library)
            stem, ext = os.path.splitext(f)
            if ext.lower() not in EXTS:
                ignored.append((rel, f"not a supported video type ({ext or 'no extension'})"))
                continue
            m = ROLE_RE.match(stem)
            if not m:
                ignored.append((rel, "name does not end in -Buffer or -Scare"))
                continue
            name = m.group("name").strip(" -_\u2013\u2014")
            role = "buffer" if m.group("role").lower() == "buffer" else "scare"
            entry = scenes.setdefault(name, {})
            if role in entry:
                ignored.append((rel, f"duplicate {role} for '{name}' "
                                     f"(using {os.path.relpath(entry[role], library)})"))
                continue
            entry[role] = path
    complete = {n: p for n, p in scenes.items() if "buffer" in p and "scare" in p}
    incomplete = {n: p for n, p in scenes.items() if n not in complete}
    return complete, incomplete, ignored


# --- video info: one ffprobe per file, results cached on disk by size + mtime ---------
CACHE_NAME = ".scene_cache.json"
_cache = {}
_cache_path = None


def load_cache(library):
    global _cache, _cache_path
    _cache_path = os.path.join(library, CACHE_NAME)
    try:
        with open(_cache_path) as f:
            _cache = json.load(f)
    except (OSError, ValueError):
        _cache = {}


def save_cache():
    if not _cache_path:
        return
    live = {k: v for k, v in _cache.items() if os.path.exists(k)}   # drop deleted files
    try:
        with open(_cache_path, "w") as f:
            json.dump(live, f)
    except OSError:
        pass


def _probe(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration:format_tags=comment", "-of", "json", path],
                             capture_output=True, text=True, timeout=30).stdout
        fmt_ = json.loads(out).get("format", {})
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"duration": None, "encoded": False}
    try:
        dur = float(fmt_.get("duration"))
    except (TypeError, ValueError):
        dur = None
    return {"duration": dur, "encoded": fmt_.get("tags", {}).get("comment") == TAG}


def info(path):
    try:
        st = os.stat(path)
    except OSError:
        return {"duration": None, "encoded": False}
    key = os.path.abspath(path)
    hit = _cache.get(key)
    if hit and hit.get("size") == st.st_size and hit.get("mtime") == st.st_mtime:
        return hit
    data = _probe(path)
    data.update(size=st.st_size, mtime=st.st_mtime)
    _cache[key] = data
    return data


def prefetch(paths):
    """Probe all uncached files in parallel (the Pi 4 has 4 cores)."""
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(info, paths))
    save_cache()


def duration(path):
    return info(path)["duration"]


def is_encoded(path):
    return info(path)["encoded"]


def encode(path):
    """Re-encode in place (via a temp file) with the settings that play smoothly on the Pi 4."""
    tmp = os.path.join(os.path.dirname(path), ".tmp_" + os.path.basename(os.path.splitext(path)[0]) + ".mp4")
    print(f"   encoding {os.path.basename(path)} (one time only) ...", flush=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-y", "-i", path,
           "-map", "0:v:0", "-map", "0:a:0?",
           "-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-level", "4.1",
           "-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-b:v", "8M", "-maxrate", "10M", "-bufsize", "16M",
           "-c:a", "aac", "-ac", "2", "-b:a", "192k", "-ar", "48000",
           "-metadata", f"comment={TAG}", "-movflags", "+faststart", tmp]
    if subprocess.run(cmd).returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        return None
    final = os.path.splitext(path)[0] + ".mp4"
    os.replace(tmp, final)
    if final != path:                    # e.g. .mov source -> keep only the .mp4
        os.remove(path)
    return final


def pending(scenes, incomplete):
    """All library videos (complete and incomplete pairs) that are not encoded yet."""
    out = []
    for group in (scenes, incomplete):
        for name in sorted(group, key=str.lower):
            for role in ("buffer", "scare"):
                path = group[name].get(role)
                if path and not is_encoded(path):
                    out.append((name, role, path))
    return out


def encode_all(scenes, incomplete):
    todo = pending(scenes, incomplete)
    if not todo:
        print("\nAll videos are already encoded.")
        return
    print(f"\nEncoding {len(todo)} video(s). This takes about a minute per video;")
    print("playback on the projector may stutter while it runs.\n")
    failed = 0
    for i, (name, role, path) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {name} - {role}")
        new = encode(path)
        if new:
            (scenes if name in scenes else incomplete)[name][role] = new
        else:
            failed += 1
            print(f"   !! failed: {os.path.basename(path)} (left unchanged)")
    save_cache()
    print(f"\nDone: {len(todo) - failed} encoded, {failed} failed.")


def fmt(sec):
    return "?" if sec is None else f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def current(library):
    try:
        return open(os.path.join(library, CURRENT_FILE)).read().strip()
    except OSError:
        return None


def activate(name, pair, library, videos, restart=True):
    print(f"\n>> Activating: {name}")
    for role in ("buffer", "scare"):
        if not is_encoded(pair[role]):
            new = encode(pair[role])
            if not new:
                sys.exit(f"!! encoding failed for {pair[role]} - nothing changed")
            pair[role] = new
    os.makedirs(videos, exist_ok=True)
    for f in os.listdir(videos):                      # remove the previous scene's videos
        if os.path.splitext(f)[1].lower() in EXTS:
            os.remove(os.path.join(videos, f))
    shutil.copy2(pair["buffer"], os.path.join(videos, BUFFER_NAME))
    shutil.copy2(pair["scare"], os.path.join(videos, SCARE_NAME))
    with open(os.path.join(library, CURRENT_FILE), "w") as f:
        f.write(name + "\n")
    save_cache()

    sd = duration(pair["scare"])
    print(f"   copied to {videos}")
    if sd:
        print(f"   scare lasts {fmt(sd)} -> set the PIR Tx to at least ~{int(sd) + 8} s")
    if restart:
        print("   restarting Video Looper ...")
        subprocess.run(["sudo", "systemctl", "restart", "video_looper"])
    print("Done.")


def main():
    ap = argparse.ArgumentParser(description="Choose the buffer/scare pair for Video Looper 2")
    ap.add_argument("name", nargs="?", help="scene name to activate without the menu")
    ap.add_argument("--list", action="store_true", help="list scenes and exit")
    ap.add_argument("--encode-all", action="store_true",
                    help="encode every library video not yet encoded, then exit")
    ap.add_argument("--library", default=LIBRARY, help=f"scene library (default {LIBRARY})")
    ap.add_argument("--videos", default=VIDEOS,
                    help=f"Video Looper's video folder (default from {LOOPER_INI}: {VIDEOS})")
    ap.add_argument("--no-restart", action="store_true", help="do not restart the looper")
    a = ap.parse_args()

    if os.geteuid() == 0:
        sys.exit("Run choose_scene.py as your normal user, without sudo.")
    if not os.path.isdir(a.library):
        sys.exit(f"Library folder not found: {a.library}\nCreate it and add <Name>-Buffer.mp4 / <Name>-Scare.mp4 pairs.")
    if not shutil.which("ffprobe"):
        sys.exit("ffmpeg not installed: sudo apt install -y ffmpeg")

    load_cache(a.library)
    scenes, incomplete, ignored = scan(a.library)
    prefetch([p for group in (scenes, incomplete) for pair in group.values() for p in pair.values()])
    names = sorted(scenes, key=str.lower)

    if a.encode_all:
        encode_all(scenes, incomplete)
        return

    if a.name:
        match = [n for n in names if n.lower() == a.name.lower()]
        if not match:
            sys.exit(f"Scene not found: {a.name}\nAvailable: {', '.join(names) or 'none'}")
        activate(match[0], scenes[match[0]], a.library, a.videos, not a.no_restart)
        return

    while True:
        active = current(a.library)
        print(f"\nScenes in {a.library}:\n")
        if not names:
            print("  (no complete pairs found)")
        for i, n in enumerate(names, 1):
            mark = "  <- active" if n == active else ""
            done = sum(is_encoded(scenes[n][r]) for r in ("buffer", "scare"))
            enc = {2: "encoded", 1: "1/2 encoded", 0: "not encoded"}[done]
            print(f"  {i:2}) {n:<40} scare {fmt(duration(scenes[n]['scare'])):>5}   {enc:<12}{mark}")
        for n, p in incomplete.items():
            missing = "Scare" if "scare" not in p else "Buffer"
            print(f"   !  {n}: missing {n}-{missing}.mp4")
        if ignored:
            print("\n  Ignored files:")
            for rel, why in ignored:
                print(f"   -  {rel}: {why}")
        todo = len(pending(scenes, incomplete))
        if a.list:
            if todo:
                print(f"\n{todo} video(s) not encoded yet - run: choose_scene.py --encode-all")
            return

        options = f"1-{len(names)} to select" if names else ""
        if todo:
            options += (", " if options else "") + f"E to encode all pending ({todo})"
        if not options:
            return
        try:
            choice = input(f"\n{options}, Enter to cancel: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not choice:
            print("Cancelled.")
            return
        if choice.lower() == "e" and todo:
            encode_all(scenes, incomplete)
            continue                                   # show the menu again
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            n = names[int(choice) - 1]
            activate(n, scenes[n], a.library, a.videos, not a.no_restart)
            return
        print("Invalid choice.")


if __name__ == "__main__":
    main()
