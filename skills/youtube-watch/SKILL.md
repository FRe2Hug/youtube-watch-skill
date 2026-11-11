---
name: youtube-watch
description: Watch and find YouTube videos. Given a YouTube URL (youtube.com, youtu.be), ytwatch extracts the transcript (transcript.txt), scene-change screenshots (png) and index.txt that ties each screenshot to what is said at that moment; `search` finds videos on YouTube. Use when the user shares a YouTube link or asks to watch, summarize, explain or "see what it looks like", researches a topic through videos, or wants to find videos on YouTube. Works for videos in any language.
license: MIT
---

# Watching YouTube (ytwatch)

You cannot play video. ytwatch turns a video into text and images you can read.

## Run

`SKILL_DIR` is the folder that contains this SKILL.md (the file you just read). Run the launcher from there:

macOS / Linux / Git Bash on Windows:

```
sh "<SKILL_DIR>/scripts/ytwatch.sh" <URL> [options]
```

Windows PowerShell:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>/scripts/ytwatch.ps1" <URL> [options]
```

The first run downloads one self-contained binary (~100 MB) to `~/.claude/bin/`. Nothing else is installed.

Output: `~/ytwatch/<video id>/`
- `transcript.txt` — `[mm:ss] line`. Subtitle priority: manual in `--lang` (if given) → manual in the spoken language → manual en → other manual → auto captions in the spoken language (machine-translated and auto-dubbed tracks are skipped)
- `0001_00m00s.png` … — one per scene change, and at least one every 30 s. Up to 1280 px wide
- `index.txt` — `file [time] what is said at that time`
- The video file itself is deleted after capture.

Options (put the URL first)
- `--subs-only` transcript only (no video download, fast)
- `--start 2:15 --end 2:45` capture only this range. To zoom in, add `--max-gap 2` (a capture at least every 2 s)
- `--max-frames 40` keep at most N captures, evenly spread (long videos)
- `--width 768` smaller captures (fewer tokens per image)
- `--dedup` drop captures nearly identical to the last kept one, e.g. a still slide (`--dedup 6` drops more). Little effect when a speaker is moving
- `--scene 0.2` scene-change sensitivity (lower = more captures, default 0.3)
- `--max-gap 10` longest gap between captures in seconds (default 30)
- `-o <dir>` output folder
- `--no-asr` never send audio to a speech-to-text API
- `--lang ko` prefer subtitles in this language (use the user's language when they ask in it)

No captions: if `GROQ_API_KEY` (or `OPENAI_API_KEY`) is set in the environment, the audio is transcribed with Whisper and `transcript.txt` is written the same way. Never print or write the key.

## Search

```
sh "<SKILL_DIR>/scripts/ytwatch.sh" search "<query>" -n 20 --year
```

- One line per video: `date  length  views  channel  title  URL` (tab-separated). `--year` = uploaded within the last year
- Use this instead of web search to find YouTube videos. Read the chosen ones with `--subs-only` first.

## How to read

1. Talk-heavy video (lecture, interview): run `--subs-only` and read transcript.txt first.
2. When looks matter (equipment, modeling, drawings, a process): run the full command, read `index.txt`, then open only the screenshots you need. Don't open them all at once.
3. Long video or a tight token budget: `--max-frames 40 --width 768 --dedup`. For one moment: `--start/--end --max-gap 2`.
4. When answering, cite the screenshot time and file name (`[02:03] 0012_02m03s.png`).

## If it fails

- `yt-dlp may be outdated` → run the launcher with `update`, then retry.
- `Sign in to confirm you're not a bot` / `429` → YouTube is rate-limiting this IP. Wait 30–60 minutes. Fetch several videos one at a time with a few seconds in between, not in parallel.
- Login-only, age-restricted and private videos cannot be fetched. Tell the user.
- `subtitle: none` → describe from the screenshots only and say the spoken content is unknown (or suggest setting `GROQ_API_KEY`).
- Run the launcher with `selftest` to check offline that the bundled ffmpeg/deno work.
