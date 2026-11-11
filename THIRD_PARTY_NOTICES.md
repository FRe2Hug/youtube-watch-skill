# Third-party software

The source code in this repository is MIT licensed (see `LICENSE`).
The release binaries additionally bundle the following programs, each under its own license:

| Component | License | Source |
|---|---|---|
| FFmpeg (Windows: gyan.dev "release essentials" build; Linux: johnvansickle.com static build; macOS arm64: jellyfin-ffmpeg portable GPL build) | GPL v3 (GPL builds; the build workflow refuses any `--enable-nonfree` build) | https://ffmpeg.org/download.html · https://www.gyan.dev/ffmpeg/builds/ · https://johnvansickle.com/ffmpeg/ · https://github.com/jellyfin/jellyfin-ffmpeg |
| yt-dlp | Unlicense | https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs | Unlicense | https://github.com/yt-dlp/ejs |
| Deno | MIT | https://github.com/denoland/deno |
| Python and its standard library (via PyInstaller) | PSF License | https://www.python.org/ |
| PyInstaller bootloader | GPL v2 with a bootloader exception | https://github.com/pyinstaller/pyinstaller |
| certifi, and the other yt-dlp[default] dependencies | MPL 2.0 / MIT / Apache 2.0 / BSD | https://pypi.org/project/yt-dlp/ |

FFmpeg is included unmodified, as a separate executable inside the binary; yt-frames calls it as a subprocess.
The exact FFmpeg version and its source code are available from the links above. The build steps that produce
each binary are in `.github/workflows/build.yml`.
