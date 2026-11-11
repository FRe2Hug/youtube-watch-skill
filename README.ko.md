# youtube-watch-skill

**설치 없이 AI 에이전트가 YouTube 를 "보게" 하는 스킬입니다. 자막·캡처·검색을 지원합니다.** · [English](README.md)

Claude Code(및 다른 Agent Skills 호스트)용 스킬입니다. 에이전트에게 YouTube 링크를 주면 다음 결과물을 받습니다.

- `transcript.txt`: `[mm:ss] 대사` 형식입니다. 영상에서 말하는 언어(또는 `--lang` 으로 고른 언어)의 수동 자막을 먼저 고르고, 다음은 영어, 그다음은 그 밖의 언어입니다. 수동 자막이 없으면 말하는 언어의 자동 자막을 씁니다. 기계번역 자막과 자동 더빙 트랙은 건너뜁니다.
- 장면 캡처(`0012_02m03s.png`): 장면이 바뀔 때마다 찍고, 바뀌지 않아도 30초마다 한 장씩 찍습니다.
- `index.txt`: 캡처마다 **그 순간에 하는 말**을 함께 적어 두므로, 에이전트는 필요한 이미지만 골라서 엽니다.
- `search`: 에이전트 안에서 YouTube 영상을 검색합니다(날짜·길이·조회수·채널).

모든 기능이 **OS 마다 실행 파일 하나**에 들어 있습니다. yt-dlp, ffmpeg, deno 가 그 안에 포함되어 있어서, Python·pip·Homebrew·winget 을 설치하거나 PATH 를 바꿀 필요가 없습니다.

## 설치

Claude Code 에서 다음 명령을 실행합니다.

```
/plugin marketplace add FRe2Hug/youtube-watch-skill
/plugin install youtube-watch-skill@youtube-watch-skill
```

그다음 YouTube 링크를 붙여 넣고 요청하면 됩니다. 예: *"이 영상 요약하고, 조명 설정하는 장면 보여줘."*

처음 쓸 때 OS 에 맞는 `ytwatch` 실행 파일(약 100MB)을 `~/.claude/bin/` 에 받습니다. 지원하는 환경은 Windows x64, Apple Silicon Mac, Linux x64 입니다.

**다른 에이전트(Codex·Cursor·Copilot 등)** 에서는 아직 확인하지 않았습니다. 스킬 폴더 `skills/youtube-watch/` 는 자기 SKILL.md 위치를 기준으로 스크립트를 찾도록 만들었으므로, [Agent Skills CLI](https://github.com/vercel-labs/skills) 로 설치하면 동작할 것으로 예상합니다.

```
npx skills add FRe2Hug/youtube-watch-skill
```

다른 호스트에서 써 보신 결과는 이슈로 알려 주세요.

## 옵션

| 옵션 | 용도 |
|---|---|
| `--subs-only` | 자막만 받습니다. 영상을 받지 않아서 빠릅니다. |
| `--start 2:15 --end 2:45 --max-gap 2` | 특정 구간을 최소 2초 간격으로 촘촘히 캡처합니다. |
| `--max-frames 40` | 캡처를 최대 N 장까지 고르게 남깁니다. 긴 영상에 씁니다. |
| `--width 768` | 이미지를 작게 만들어 토큰을 줄입니다. |
| `--dedup [DIFF]` | 직전에 남긴 캡처와 거의 같은 캡처(멈춘 슬라이드·화면)를 버립니다. 발표자가 움직이면 바뀐 것으로 보므로, 사람이 말하는 영상에서는 줄어드는 양이 적습니다. |
| `--lang ko` | 이 언어의 자막을 먼저 고릅니다. |
| `--scene 0.2` / `--max-gap 10` | 장면 전환 민감도와 캡처 사이 최대 간격을 정합니다. |
| `search "검색어" -n 20 --year` | YouTube 를 검색합니다. `--year` 를 붙이면 최근 1년 안에 올라온 영상만 나옵니다. |
| `update` | 최신 릴리스로 교체합니다. 매주 최신 yt-dlp 로 새로 빌드됩니다. |
| `selftest` | 내장된 ffmpeg 와 deno 가 동작하는지 오프라인으로 점검합니다. |

**자막이 없는 영상**은 `GROQ_API_KEY`(무료 한도 있음)나 `OPENAI_API_KEY` 를 설정하면 Whisper 로 받아 적어서, 같은 `transcript.txt` 형식으로 저장합니다. Whisper 가 말소리가 아니라고 판단한 구간과, 음악 위에 흔히 지어내는 "Thank you." 같은 문장은 걸러 냅니다. 키는 환경변수에서만 읽고 어디에도 기록하지 않습니다. 오디오를 절대 보내지 않으려면 `--no-asr` 를 씁니다.

## 특징

- **설치할 것이 없습니다.** 플러그인이 yt-dlp·ffmpeg·deno 가 든 실행 파일 하나를 가져옵니다. 런타임을 준비하거나 직접 업데이트할 필요가 없고, `update` 가 매주 새로 빌드된 파일을 받습니다.
- **찾고 나서 봅니다.** `search` 가 날짜·길이·조회수와 함께 YouTube 검색 결과를 보여 주므로, 에이전트가 직접 영상을 고를 수 있습니다.
- **캡처마다 그때 하는 말이 붙습니다.** `index.txt` 가 캡처 옆에 대사를 적어 두므로, 에이전트는 글을 먼저 읽고 필요한 이미지만 엽니다.
- **깔끔한 자막.** 기계번역·자동 더빙 트랙은 건너뜁니다. 자막이 없으면 Whisper 로 받아 적고, 음악 위에 흔히 지어내는 문장은 걸러 냅니다.
- **토큰 조절.** `--max-frames`, `--width`, `--dedup`, `--start/--end` 로 긴 영상도 부담 없이 봅니다.

지원하지 않는 것: 로컬(오프라인) 음성인식, 내 PC 의 영상 파일, YouTube 가 아닌 사이트.

## 출력

```
~/ytwatch/<영상 ID>/
  transcript.txt     # 머리말(제목·URL·채널·날짜·길이·조회수·자막 출처) + [mm:ss] 대사
  0001_00m00s.png …  # 가로 최대 1280px (--width 로 변경)
  index.txt          # 0012_02m03s.png  [02:03]  02:03 에 하는 말
```

영상 파일은 캡처가 끝나면 지웁니다.

## 한계

- 한 IP 에서 요청이 몰리면 YouTube 가 막습니다("Sign in to confirm you're not a bot", HTTP 429). 영상은 하나씩 받아야 합니다. 검색과 자막 20개 정도를 한꺼번에 받으면 막힐 수 있고, 30~60분 지나면 풀립니다.
- 비공개·멤버십·연령 제한 영상은 받지 못합니다.
- 실행 파일에 코드 서명이 없어서, 직접 실행하면 Windows SmartScreen 이 경고할 수 있습니다. 플러그인은 curl 이나 PowerShell 로 받기 때문에 격리 표시가 붙지 않습니다.

## 빌드

`.github/workflows/build.yml` 이 Windows·macOS·Linux 러너에서 PyInstaller 로 빌드합니다. 각 러너에서 `selftest` 와 실제 YouTube 시험을 돌린 뒤 릴리스를 올립니다. `main` 에 push 할 때와 매주 월요일에 실행됩니다. 소스는 `ytwatch.py` 입니다.

라이선스: 이 저장소의 소스는 MIT 입니다. 실행 파일에는 FFmpeg(GPL) 등이 포함되어 있으니 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 를 참고하세요.
