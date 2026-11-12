"""ytwatch: YouTube URL -> transcript.txt + scene captures (png) + index.txt

  ytwatch <url> [-o DIR] [--scene 0.3] [--max-gap 30] [--subs-only]
            [--start 2:15] [--end 2:45] [--max-frames N] [--width 1280] [--dedup] [--no-asr] [--lang ko]
  ytwatch search "<query>" [-n 20] [--year]
  ytwatch update
  ytwatch selftest

No subtitles? Set GROQ_API_KEY (or OPENAI_API_KEY) and the audio is transcribed with Whisper.
"""
import argparse
import html
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import yt_dlp

REPO = "FRe2Hug/youtube-watch-skill"
DEFAULT_OUT = Path.home() / "ytwatch"
EXE = ".exe" if os.name == "nt" else ""
ASSET = {"win32": "ytwatch-windows-x64.exe", "darwin": "ytwatch-macos-arm64"}.get(sys.platform, "ytwatch-linux-x64")
CHUNK = 1200  # seconds of audio per speech-to-text request (32 kbps mono mp3 -> ~4.6 MB)
ASR = [  # env var, provider, endpoint, model
    ("GROQ_API_KEY", "groq", "https://api.groq.com/openai/v1/audio/transcriptions", "whisper-large-v3"),
    ("OPENAI_API_KEY", "openai", "https://api.openai.com/v1/audio/transcriptions", "whisper-1"),
]


def bundled(name):
    """ffmpeg/deno packed into the exe by PyInstaller, or next to the script when run from source."""
    name += EXE
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    p = base / name
    return str(p) if p.exists() else shutil.which(name)


def ffmpeg(*args):
    r = subprocess.run([bundled("ffmpeg") or "ffmpeg", "-hide_banner", *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit("ffmpeg failed:\n" + r.stderr[-2000:])
    return r


def ydl_opts(**extra):
    opts = {"quiet": True, "no_warnings": True, "noprogress": True}
    ff = bundled("ffmpeg")
    if ff:
        opts["ffmpeg_location"] = ff
    deno = bundled("deno")
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    opts.update(extra)
    return opts


def ssl_ctx():
    try:
        import certifi  # bundled with yt-dlp[default]; frozen macOS/Linux builds have no system CA path
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ---------- subtitles ----------

def ts(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec // 60 % 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_time(t):
    parts = str(t).replace(",", ".").split(":")
    sec = 0.0
    for p in parts:
        sec = sec * 60 + float(p)
    return sec


def parse_vtt(text):
    """Return [(start, end, line)], with YouTube auto-caption rolling duplicates removed."""
    cues = []
    blocks = re.split(r"\n\s*\n", text.replace("\r", ""))
    for b in blocks:
        lines = b.strip().split("\n")
        for i, l in enumerate(lines):
            m = re.match(r"([\d:.,]+)\s*-->\s*([\d:.,]+)", l)
            if m:
                body = [re.sub(r"<[^>]+>", "", x).strip() for x in lines[i + 1:]]
                body = [html.unescape(x) for x in body if x]
                if body:
                    cues.append((parse_time(m.group(1)), parse_time(m.group(2)), body))
                break
    out, seen = [], []
    for start, end, body in cues:
        for line in body:
            if line in seen[-3:]:
                continue
            seen.append(line)
            out.append((start, end, line))
    return out


def write_transcript(out, info, label, cues):
    with open(out / "transcript.txt", "w", encoding="utf-8") as f:
        f.write(f"# {info.get('title')}\n# {info.get('webpage_url')}\n"
                f"# {info.get('channel')} | {fmt_date(info.get('upload_date'))} | {ts(info.get('duration') or 0)}"
                f" | views {info.get('view_count')}\n# subtitles: {label}\n\n")
        for start, _, line in cues:
            f.write(f"[{ts(start)}] {line}\n")


def get_subs(info, out, tmp, prefer=None):
    """Download the best subtitle and write transcript.txt.

    Manual: --lang > spoken language > en > any. Then auto captions in the spoken language.
    Auto captions list every machine-translated language too; those are poor and often HTTP 429,
    so only the original-language track is used.
    """
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat"}
    auto = info.get("automatic_captions") or {}
    spoken = (info.get("language") or "").split("-")[0]  # "en-US" -> "en" (track key is "en-orig")
    wants = list(dict.fromkeys(w for w in (prefer, spoken, "en") if w))
    pick = None
    for want in wants:
        lang = next((l for l in manual if l == want or l.startswith(want + "-")), None)
        if lang:
            pick = (lang, "manual")
            break
    if not pick and manual:
        pick = (next(iter(manual)), "manual")
    if not pick and auto:
        # dubbed videos list several "-orig" tracks; prefer --lang, then the spoken language, then en
        origs = [l for l in auto if l.endswith("-orig")]
        orig = (next((l for w in wants for l in origs if l.split("-")[0] == w), None)
                or (spoken if spoken in auto else None)
                or next(iter(origs), None))
        if orig:
            pick = (orig, "auto")
    if not pick:
        return None, []
    lang, kind = pick
    opts = ydl_opts(
        skip_download=True, subtitleslangs=[lang], subtitlesformat="vtt",
        writesubtitles=kind == "manual", writeautomaticsub=kind == "auto",
        outtmpl=str(Path(tmp) / "sub.%(ext)s"),
    )
    with yt_dlp.YoutubeDL(opts) as y:
        y.process_ie_result(info, download=True)
    vtt = next(Path(tmp).glob("sub*.vtt"), None)
    if not vtt:
        return None, []
    cues = parse_vtt(vtt.read_text(encoding="utf-8", errors="replace"))
    label = f"{lang} ({kind})"
    write_transcript(out, info, label, cues)
    return label, cues


# ---------- speech-to-text (no subtitles) ----------

def post_audio(url, key, model, path, lang):
    """OpenAI-compatible /audio/transcriptions call. The key goes only into the Authorization header."""
    boundary = uuid.uuid4().hex
    fields = {"model": model, "response_format": "verbose_json", "temperature": "0"}
    if lang:
        fields["language"] = lang
    body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                    for k, v in fields.items())
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
             f"Content-Type: audio/mpeg\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Authorization": f"Bearer {key}", "User-Agent": "ytwatch",
               "Content-Type": f"multipart/form-data; boundary={boundary}"}
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=600, context=ssl_ctx()) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(min(float(e.headers.get("retry-after") or 20), 60))


# Whisper invents these over music or silence
HALLUCINATIONS = {"thank you", "thanks for watching", "thank you for watching", "please subscribe", "you",
                  "subtitles by the amaraorg community", "시청해 주셔서 감사합니다", "시청해주셔서 감사합니다",
                  "구독과 좋아요 부탁드립니다", "감사합니다", "ご視聴ありがとうございました", "字幕志愿者"}


def is_speech(seg):
    text = seg.get("text", "").strip()
    norm = re.sub(r"[^\w\s]", "", text).strip().lower()
    nsp = seg.get("no_speech_prob", 0)
    if not norm or nsp >= 0.6:  # empty, only symbols (♪ 🎵), or the model itself says "no speech"
        return False
    return not (norm in HALLUCINATIONS and nsp > 0.2)


def transcribe(info, out, tmp):
    prov = next(((p, u, m, os.environ[k]) for k, p, u, m in ASR if os.environ.get(k)), None)
    if not prov:
        return None, []
    name, url, model, key = prov
    with yt_dlp.YoutubeDL(ydl_opts(format="ba/b", outtmpl=str(Path(tmp) / "audio.%(ext)s"))) as y:
        y.extract_info(info["webpage_url"], download=True)
    audio = next(p for p in Path(tmp).glob("audio.*") if p.suffix != ".part")
    chunks = Path(tmp) / "chunks"
    chunks.mkdir()
    ffmpeg("-i", audio, "-vn", "-ac", 1, "-ar", 16000, "-c:a", "libmp3lame", "-b:a", "32k",
           "-f", "segment", "-segment_time", CHUNK, "-reset_timestamps", 1, chunks / "%03d.mp3")
    lang = (info.get("language") or "").split("-")[0]
    cues = []
    try:
        for i, c in enumerate(sorted(chunks.glob("*.mp3"))):
            off = i * CHUNK
            res = post_audio(url, key, model, c, lang if len(lang) == 2 else None)
            segs = res.get("segments") or [{"start": 0, "end": CHUNK, "text": res.get("text", "")}]
            cues += [(s["start"] + off, s["end"] + off, s["text"].strip()) for s in segs if is_speech(s)]
    except (urllib.error.URLError, OSError, ValueError) as e:
        msg = e.read().decode("utf-8", "replace")[:300] if isinstance(e, urllib.error.HTTPError) else str(e)[:300]
        print(f"speech-to-text failed ({name}): {getattr(e, 'code', '')} {msg}", file=sys.stderr)
        return None, []
    if not cues:
        print(f"speech-to-text ({name}): no speech detected", file=sys.stderr)
        return None, []
    label = f"{model} ({name} speech-to-text)"
    write_transcript(out, info, label, cues)
    return label, cues


# ---------- frames ----------

def download_video(info, tmp):
    opts = ydl_opts(
        format="bv*[height<=720][ext=mp4]/bv*[height<=720]/b[height<=720]/b",
        outtmpl=str(Path(tmp) / "video.%(ext)s"),
    )
    with yt_dlp.YoutubeDL(opts) as y:  # fresh extract: stream URLs are bound to the session that made them (403 otherwise)
        y.extract_info(info["webpage_url"], download=True)
    return next(p for p in Path(tmp).glob("video.*") if p.suffix != ".part")


def dedup(frames, pairs, limit):
    """Drop a capture whose 32x18 grayscale thumbnail differs from the last kept one by < limit (0-255 mean)."""
    w, h = 32, 18
    raw = subprocess.run([bundled("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(frames / "%05d.png"),
                          "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    thumbs = [raw[i:i + w * h] for i in range(0, len(raw), w * h)]
    if len(thumbs) != len(pairs):
        return pairs
    keep, last = [pairs[0]], thumbs[0]
    for p, t in zip(pairs[1:], thumbs[1:]):
        if sum(abs(x - y) for x, y in zip(last, t)) / (w * h) >= limit:
            keep.append(p)
            last = t
    return keep


def extract_frames(video, out, tmp, a):
    """First frame, every scene change (at least 2 s apart), at least one frame every max_gap s.

    --start/--end limit the range, --dedup drops near-identical captures, --max-frames thins evenly.
    """
    gap2 = min(2, a.max_gap)
    expr = (f"if(isnan(prev_selected_t),1,"
            f"gte(t-prev_selected_t,{a.max_gap})+gt(scene,{a.scene})*gte(t-prev_selected_t,{gap2}))")
    chain = [f"select='{expr}'", f"scale='min({a.width},iw)':-2", "showinfo"]
    start = a.start or 0
    cmd = (["-ss", start] if start else []) + ["-i", video]
    if a.end:
        cmd += ["-t", a.end - start]
    frames = Path(tmp) / "frames"
    frames.mkdir()
    r = ffmpeg(*cmd, "-vf", ",".join(chain), "-fps_mode", "vfr", frames / "%05d.png")
    times = [float(t) + start for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    pairs = list(zip(sorted(frames.glob("*.png")), times))
    if a.dedup and len(pairs) > 1:
        pairs = dedup(frames, pairs, a.dedup)
    k = a.max_frames
    if k and len(pairs) > k:
        n = len(pairs)
        pairs = [pairs[i] for i in sorted({round(j * (n - 1) / max(k - 1, 1)) for j in range(k)})]
    result = []
    for i, (src, t) in enumerate(pairs, 1):
        name = f"{i:04d}_{int(t) // 60:02d}m{int(t) % 60:02d}s.png"
        shutil.move(str(src), out / name)
        result.append((t, name))
    return result


# ---------- commands ----------

def run(args):
    with yt_dlp.YoutubeDL(ydl_opts()) as y:
        info = y.extract_info(args.url, download=False)
    out = Path(args.output) if args.output else DEFAULT_OUT / info["id"]
    out.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="ytw_")
    try:
        try:
            sub_label, cues = get_subs(info, out, tmp, args.lang)
        except yt_dlp.utils.DownloadError as e:  # keep going: frames are still useful
            sub_label, cues = f"failed ({str(e).splitlines()[0][:120]})", []
        if not cues and not args.no_asr:
            try:
                label, cues = transcribe(info, out, tmp)
                sub_label = label or sub_label
            except yt_dlp.utils.DownloadError as e:
                print(f"speech-to-text: audio download failed ({str(e).splitlines()[0][:120]})", file=sys.stderr)
        frames = [] if args.subs_only else extract_frames(download_video(info, tmp), out, tmp, args)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # video/audio files never stay

    if frames:
        with open(out / "index.txt", "w", encoding="utf-8") as f:
            f.write(f"# {info.get('title')}\n# {info.get('webpage_url')}\n\n")
            for t, name in frames:
                said = next((l for s, e, l in cues if s <= t < e), "")
                if not said:  # nearest line before
                    said = next((l for s, e, l in reversed(cues) if s <= t), "")
                if not said:  # frame before the first line (e.g. 00:00): line starting within 5 s
                    said = next((l for s, e, l in cues if t < s <= t + 5), "")
                f.write(f"{name}\t[{ts(t)}]\t{said}\n")

    hint = "" if cues or args.no_asr or any(os.environ.get(k) for k, *_ in ASR) else \
        "  (set GROQ_API_KEY or OPENAI_API_KEY to transcribe the audio)"
    print(f"title:    {info.get('title')}")
    print(f"duration: {ts(info.get('duration') or 0)}")
    print(f"folder:   {out}")
    print(f"subtitle: {sub_label or 'none'}" + (f" -> transcript.txt ({len(cues)} lines)" if cues else hint))
    if not args.subs_only:
        print(f"frames:   {len(frames)} png -> index.txt")


def fmt_date(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d else "?"


def search(argv):
    p = argparse.ArgumentParser(prog="ytwatch search")
    p.add_argument("query")
    p.add_argument("-n", type=int, default=20, help="number of results (default 20)")
    p.add_argument("--year", action="store_true", help="only videos uploaded in the last year")
    a = p.parse_args(argv)
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(a.query)
    if a.year:
        url += "&sp=EgIIBQ%3D%3D"  # YouTube filter: upload date = this year
    with yt_dlp.YoutubeDL(ydl_opts(extract_flat="in_playlist", playlistend=a.n)) as y:
        entries = [e for e in y.extract_info(url, download=False)["entries"] if e.get("id")][:a.n]

    def upload_date(e):  # flat search results carry no date
        try:
            with yt_dlp.YoutubeDL(ydl_opts()) as y:
                return y.extract_info(e["url"], download=False, process=False).get("upload_date")
        except yt_dlp.utils.DownloadError:
            return None

    with ThreadPoolExecutor(8) as pool:
        dates = list(pool.map(upload_date, entries))
    for e, d in zip(entries, dates):
        views = f"{e['view_count']:,}" if e.get("view_count") is not None else "?"
        print(f"{fmt_date(d)}	{ts(e.get('duration') or 0)}	{views:>11}	{e.get('channel')}	{e.get('title')}	{e['url']}")


def update(argv):
    if argv:
        sys.exit("usage: ytwatch update\n\nReplace this exe with the latest release from "
                 f"github.com/{REPO}.")
    if not getattr(sys, "frozen", False):
        sys.exit("update only works for the built exe")
    exe = Path(sys.executable)
    tmp = Path(tempfile.mkdtemp(prefix="ytw_up_"))
    new = tmp / ASSET
    try:
        url = f"https://github.com/{REPO}/releases/latest/download/{ASSET}"
        with urllib.request.urlopen(url, timeout=300, context=ssl_ctx()) as r, open(new, "wb") as f:
            shutil.copyfileobj(r, f)
    except urllib.error.URLError:  # private repo: fall back to gh
        r = subprocess.run(["gh", "release", "download", "--repo", REPO, "--pattern", ASSET,
                            "--dir", str(tmp), "--clobber"])
        if r.returncode:
            sys.exit("download failed")
    if os.name == "nt":
        old = exe.with_suffix(".old")
        old.unlink(missing_ok=True)
        exe.rename(old)  # a running exe can be renamed but not overwritten
        shutil.move(str(new), exe)
    else:
        staged = exe.with_name(exe.name + ".new")
        shutil.move(str(new), staged)
        staged.chmod(0o755)
        os.replace(staged, exe)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"updated: {exe}")


def selftest():
    """Offline check that the bundled ffmpeg/deno work: synthetic video -> scene captures."""
    tmp = Path(tempfile.mkdtemp(prefix="ytw_test_"))
    try:
        video = tmp / "test.mp4"
        ffmpeg("-f", "lavfi", "-i",
               "testsrc2=d=10:s=640x360:r=10[a];smptebars=d=10:s=640x360:r=10[b];[a][b]concat=n=2[out0]",
               "-pix_fmt", "yuv420p", video)
        out = tmp / "out"
        out.mkdir()
        a = SimpleNamespace(scene=0.3, max_gap=4, width=1280, dedup=False, start=None, end=None, max_frames=None)
        frames = extract_frames(video, out, tmp, a)
        cut = any(9.5 <= t <= 10.5 for t, _ in frames)
        encoders = ffmpeg("-encoders").stdout
        deno = subprocess.run([bundled("deno") or "deno", "--version"], capture_output=True, text=True)
        try:  # the CA bundle used by update and speech-to-text (frozen macOS/Linux builds have no system CA path)
            urllib.request.urlopen("https://api.github.com", timeout=15, context=ssl_ctx()).close()
            https = True
        except urllib.error.URLError as e:
            https = not isinstance(e.reason, ssl.SSLError)  # offline is not a failure, a certificate error is
            print(f"note  HTTPS check: {e.reason}")
        checks = {
            "HTTPS certificates (update, speech-to-text)": https,
            "frames >= 5": len(frames) >= 5,
            "scene change at 10s captured": cut,
            "png files written": all((out / n).stat().st_size > 0 for _, n in frames),
            "ffmpeg has libmp3lame": "libmp3lame" in encoders,
            "deno runs": deno.returncode == 0,
        }
        for k, v in checks.items():
            print(f"{'ok  ' if v else 'FAIL'}  {k}")
        print(f"frames: {[f'{t:.1f}' for t, _ in frames]}")
        if not all(checks.values()):
            sys.exit(1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    sys.stdout.reconfigure(errors="replace")
    if getattr(sys, "frozen", False):
        Path(sys.executable).with_suffix(".old").unlink(missing_ok=True)
    cmd = sys.argv[1:2]
    if cmd == ["search"]:
        return search(sys.argv[2:])
    if cmd == ["update"]:
        return update(sys.argv[2:])
    if cmd == ["selftest"]:
        return selftest()
    p = argparse.ArgumentParser(prog="ytwatch", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("-o", "--output", help=f"output folder (default {DEFAULT_OUT}{os.sep}<video id>)")
    p.add_argument("--scene", type=float, default=0.3, help="scene-change threshold 0..1 (default 0.3)")
    p.add_argument("--max-gap", type=float, default=30, help="max seconds between frames (default 30)")
    p.add_argument("--subs-only", action="store_true", help="transcript only, no video download")
    p.add_argument("--start", type=parse_time, help="capture from this time (90, 1:30 or 1:02:03)")
    p.add_argument("--end", type=parse_time, help="capture until this time")
    p.add_argument("--max-frames", type=int, help="keep at most N captures, evenly spread")
    p.add_argument("--width", type=int, default=1280, help="max capture width in px (default 1280)")
    p.add_argument("--dedup", type=float, nargs="?", const=3.0, metavar="DIFF",
                   help="drop captures nearly identical to the last kept one (DIFF = mean 0-255 change, default 3; raise it to drop more)")
    p.add_argument("--no-asr", action="store_true", help="never send audio to a speech-to-text API")
    p.add_argument("--lang", help="preferred subtitle language, e.g. ko (default: the language spoken in the video)")
    p.add_argument("--version", action="version", version=f"ytwatch (yt-dlp {yt_dlp.version.__version__})")
    args = p.parse_args()
    if args.start is not None and args.end is not None and args.end <= args.start:
        p.error("--end must be after --start")
    try:
        run(args)
    except yt_dlp.utils.DownloadError as e:
        sys.exit(f"{e}\n\nyt-dlp may be outdated -> run: ytwatch update")


if __name__ == "__main__":
    main()
