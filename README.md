# Choose Scene for Video Looper 2

A scene picker for [Adafruit Video Looper 2](https://github.com/adafruit/pi_video_looper2) on the Raspberry Pi,
made for motion-triggered projection effects such as Halloween window and wall projections.

Keep a library of **scenes** on the Pi. Each scene is a pair of videos: a calm loop that plays while nobody is
around (the *buffer*) and the effect that plays when a sensor or button triggers it (the *scare*). Run
`choose_scene.py` and it lists every scene with the length of its scare, whether it is ready to play, and which
one is active. Pick a number and it converts the videos to a format the Pi plays smoothly (only the first time),
copies them into Video Looper's folder with the right names, and restarts the looper. A few seconds later the new
scene is playing.

```
Scenes in /home/pi/VideoLibrary:

   1) Jack_O_Lantern_JumpScare                 scare  0:32   encoded       <- active
   2) Macabre Manor Family Scare               scare  0:45   encoded
   3) Witch Brew                               scare  0:28   not encoded
   !  Lonely Ghost: missing Lonely Ghost-Scare.mp4

  Ignored files:
   -  Random clip.mp4: name does not end in -Buffer or -Scare

1-3 to select, E to encode all pending (2), Enter to cancel:
```

## Features

- **Menu or one-liner:** pick from a menu, or activate a scene by name with `choose_scene.py "Witch Brew"`.
- **Automatic encoding:** videos are re-encoded once to H.264 High@4.1, 30 fps constant frame rate, stereo AAC 48 kHz.
  Some downloaded effect videos stutter on the Pi 4 with Video Looper 2 even though they look standard; after this
  re-encode they play smoothly. The encoded file replaces the original in the library, so keep your originals elsewhere.
- **Encode everything ahead of time** with `E` in the menu or `--encode-all`, so switching scenes is instant.
- **Tells you how to set your PIR sensor:** shows the scare length and the minimum hold time (Tx) for an HC-SR501,
  so the scare is never cut off and restarted halfway.
- **Tolerant naming:** `-`, `_`, spaces or typographic dashes before the role, extra text such as ` 1080p` or ` (HD)`
  after it, and subfolders are all fine. Files that cannot be used are listed with the reason.
- **Fast:** each video is probed once, in parallel, and cached by size and modification time.

## Requirements

- Raspberry Pi running [Video Looper 2](https://github.com/adafruit/pi_video_looper2) (tested on a Pi 4 with
  64-bit Raspberry Pi OS).
- Video Looper configured to play from a folder and to jump to the second video on a trigger, for example in
  `/boot/video_looper.ini`:

  ```ini
  [video_looper]
  file_reader = directory

  [directory]
  path = /home/<user>/Videos

  [control]
  gpio_pin_map = "D26" : 1
  ```

  Choose Scene reads `path` from `/boot/video_looper.ini` and copies the active pair there as
  `0_buffer_repeat_9999x.mp4` (index 0, looped 9999 times using Video Looper's `_repeat_Nx` filename feature) and
  `1_scare.mp4` (index 1, played on the trigger, after which the playlist returns to the buffer).
  **Any other videos in that folder are removed** when a scene is activated.
- `ffmpeg` (the installer adds it if missing).

For an HC-SR501 PIR sensor wired directly to the Pi without an inverter, see the `gpio_pin_mode` option in
[this Video Looper 2 fork](https://github.com/juanchuj/pi_video_looper2).

## Install

```bash
git clone https://github.com/juanchuj/Choose-Scene-for-Video-Looper-2
cd Choose-Scene-for-Video-Looper-2
./install.sh
```

This installs `choose_scene.py` to `~/.local/bin`, creates `~/VideoLibrary`, and adds `~/.local/bin` to your PATH
if needed. Run it as your normal user, not with `sudo`.

## Adding scenes

Copy pairs into `~/VideoLibrary` (subfolders are fine):

```
~/VideoLibrary/
  Jack-O-Lantern-Buffer.mp4
  Jack-O-Lantern-Scare.mp4
  Macabre Manor Family Scare-Buffer.mp4
  Macabre Manor Family Scare-Triggered.mov
```

- The scene name is everything before the **last** role word, so names may contain hyphens or even the word "Scare".
- The second video may end in `-Scare`, `-Trigger` or `-Triggered`.
- Supported types: `.mp4 .mov .mkv .m4v .avi .webm .mpg .mpeg .wmv .ts`. Everything is converted to `.mp4` when encoded.

Copying large video files over Wi-Fi is slow. A USB stick formatted as exFAT is usually the quickest way:

```bash
cp -v /media/$USER/<STICK>/*.mp4 ~/VideoLibrary/ && sync
```

## Usage

| Command | What it does |
|---|---|
| `choose_scene.py` | Menu: pick a scene, or `E` to encode all pending videos |
| `choose_scene.py --list` | List scenes and exit |
| `choose_scene.py "Name"` | Activate a scene by name (case-insensitive) |
| `choose_scene.py --encode-all` | Encode every library video not yet encoded |
| `--library PATH` | Use another library folder (default `~/VideoLibrary`) |
| `--videos PATH` | Use another looper video folder (default: `path` from `/boot/video_looper.ini`) |
| `--no-restart` | Do not restart the `video_looper` service after switching |

Encoding uses all four CPU cores and takes about a minute per video on a Pi 4, so do it before showtime: playback
may stutter while it runs.

## Files it creates

- `~/VideoLibrary/.current_scene`: name of the active scene.
- `~/VideoLibrary/.scene_cache.json`: cached video durations and encoding status. Safe to delete.

## License

MIT, see [LICENSE](LICENSE).
