#!/usr/bin/env python3
"""WO GALI (वो गली) V5 Final validator: hard 55.0-second ceiling + audit rules.

Use it from the command line:
    python wo_gali_validator.py STORY_03_ARTIFACT.md
    python wo_gali_validator.py STORY_03_ARTIFACT.md --audio STORY_03_VIRAJ.mp3
    python wo_gali_validator.py STORY_03_ARTIFACT.md --audio-seconds 51.3

Or import it from agent_1 / agent_4:
    from wo_gali_validator import validate_artifact, validate_audio_seconds, audio_duration_seconds
    errors, warnings = validate_artifact(markdown_text)
    errors += validate_audio_seconds(audio_duration_seconds("voice.mp3"))

Exit code 0 = pass, 1 = rule violation, 2 = usage or file error.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locked production constants
# ---------------------------------------------------------------------------
MIN_CHARS = 550
MAX_CHARS = 590
CHARS_PER_SECOND = 11.8          # calibration: 614 chars ≈ 52.0s
HARD_MAX_SECONDS = 55.0          # absolute ceiling for voice and VID timeline
TARGET_MIN_SECONDS = 48.0
TARGET_MAX_SECONDS = 53.0
TIME_TOLERANCE = 0.05            # rounding tolerance for one-decimal timestamps

LIP_SYNC_PHRASE = (
    "lips and jaw open and close in smooth natural silent visual lip-sync "
    "motion without any spoken voice"
)
AUDIO_PREFIX = "Audio: Generate ONLY these physical background sound effects:"
AUDIO_SUFFIX = (
    "Strictly NO voice generation, NO spoken words, NO narration, NO vocals, "
    "and NO AI speech."
)

SECTION_A_FIELDS = (
    "Story Name",
    "Top Yellow Banner Text",
    "Total Character Count",
    "Hard Maximum Voice Duration",
    "ElevenLabs Hindi Voice Script",
)

SPEECH_TRIGGERS = re.compile(
    r"\b("
    r"say|says|said|saying|"
    r"whisper|whispers|whispered|whispering|"
    r"murmur|murmurs|murmured|murmuring|"
    r"shout|shouts|shouted|shouting|"
    r"ask|asks|asked|asking|"
    r"scream|screams|screamed|screaming|"
    r"cry|cries|cried|crying|"
    r"yell|yells|yelled|yelling|"
    r"talk|talks|talked|talking|"
    r"speak|speaks|speaking|begins to speak|when speaking|"
    r"voice says|call out|calls out"
    r")\b",
    re.IGNORECASE,
)
VOCAL_SFX = re.compile(
    r"\b(scream\w*|shout\w*|whisper\w*|giggl\w*|laugh\w*|sob\w*|cry\w*|cries|"
    r"humming|gasp\w*|breath\w*|voice|vocal|moan\w*|groan\w*|wail\w*)\b",
    re.IGNORECASE,
)
MINOR_WORDS = re.compile(
    r"\b(girl|girls|boy|boys|child|children|kid|kids|teen|teens|teenager|"
    r"teenage|student|students|schoolchild|school uniform)\b",
    re.IGNORECASE,
)

NUQTA = "\u093c"
ALLOWED_NUQTA_BASES = {"\u0921", "\u0922"}              # ड, ढ  -> ड़, ढ़
ALLOWED_PRECOMPOSED = {"\u095c", "\u095d"}               # ड़, ढ़ (precomposed)
FORBIDDEN_PRECOMPOSED = {
    "\u0958": "क़", "\u0959": "ख़", "\u095a": "ग़", "\u095b": "ज़",
    "\u095e": "फ़", "\u095f": "य़",
}
DIGITS = re.compile(r"[0-9\u0966-\u096f]")
DEVANAGARI = re.compile(r"[\u0900-\u097f]")

IMG_LINE = re.compile(
    r"^- \*\*IMG-(\d+) \(Scene (\d+) · Chars: (\d+) · ~(\d+(?:\.\d+)?)s · \"(.+?)\"\):\*\* `([^`]+)`\s*$"
)
VID_LINE = re.compile(
    r"^- \*\*VID-(\d+) \(Scene (\d+) · (\d+(?:\.\d+)?)s–(\d+(?:\.\d+)?)s · "
    r"Duration: (\d+(?:\.\d+)?)s · Chars: (\d+)\):\*\* `([^`]+)`\s*$"
)


# ---------------------------------------------------------------------------
# Hindi script checks
# ---------------------------------------------------------------------------
def nuqta_errors(text: str, label: str = "text") -> list[str]:
    """Allow native ड़/ढ़ (decomposed or precomposed); reject क़ ख़ ग़ ज़ फ़ य़ and any other nuqta."""
    errors = []
    for i, ch in enumerate(text):
        if ch in FORBIDDEN_PRECOMPOSED:
            errors.append(f"{label}: forbidden nuqta letter {FORBIDDEN_PRECOMPOSED[ch]} at index {i}")
        elif ch == NUQTA:
            base = text[i - 1] if i > 0 else ""
            if base not in ALLOWED_NUQTA_BASES:
                errors.append(
                    f"{label}: forbidden nuqta on '{base}{NUQTA}' at index {i} "
                    "(only native ड़ and ढ़ are allowed)"
                )
    return errors


def estimated_seconds(char_count: int) -> float:
    return round(char_count / CHARS_PER_SECOND, 1)


def validate_voice_script(script: str) -> tuple[list[str], list[str]]:
    """Section A script: 550–590 chars, nuqta-free, no digits, <= 55.0s estimated."""
    errors, warnings = [], []
    n = len(script)
    if not MIN_CHARS <= n <= MAX_CHARS:
        errors.append(f"Section A script has {n} characters; required {MIN_CHARS}–{MAX_CHARS}")
    secs = estimated_seconds(n)
    if secs > HARD_MAX_SECONDS:
        errors.append(f"Section A estimated duration {secs}s exceeds hard ceiling {HARD_MAX_SECONDS}s")
    elif not TARGET_MIN_SECONDS <= secs <= TARGET_MAX_SECONDS:
        warnings.append(
            f"Section A estimated duration {secs}s is outside the "
            f"{TARGET_MIN_SECONDS}–{TARGET_MAX_SECONDS}s target window (aim for 570–590 characters)"
        )
    errors += nuqta_errors(script, "Section A script")
    if DIGITS.search(script):
        errors.append("Section A script contains digits; write numbers in Hindi words")
    if re.search(r"scene\s*\d+", script, re.IGNORECASE):
        errors.append("Section A script contains a 'Scene NN' label")
    return errors, warnings


def validate_audio_seconds(seconds: float) -> list[str]:
    """Agent 4 gate: the real voiceover MP3 must be <= 55.0s."""
    if seconds > HARD_MAX_SECONDS:
        return [f"Voiceover audio is {seconds:.2f}s; hard ceiling is {HARD_MAX_SECONDS}s"]
    return []


def audio_duration_seconds(path: str | Path) -> float:
    """Read MP3/WAV duration with mutagen if installed, otherwise ffprobe."""
    try:
        from mutagen import File as MutagenFile  # type: ignore

        audio = MutagenFile(str(path))
        if audio is not None and audio.info is not None:
            return float(audio.info.length)
    except ImportError:
        pass
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("Install mutagen (pip install mutagen) or ffmpeg/ffprobe to read audio duration")
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


# ---------------------------------------------------------------------------
# Artifact checks
# ---------------------------------------------------------------------------
def _section_a(lines: list[str]) -> tuple[list[str], str, list[str]]:
    """Return (header bullet lines, script paragraph, errors)."""
    errors = []
    start = next((i for i, l in enumerate(lines) if l.startswith("# SECTION A")), None)
    if start is None:
        return [], "", ["Missing '# SECTION A' heading"]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("# SECTION")), len(lines))
    body = lines[start + 1:end]
    headers = [l for l in body if l.startswith("- **")]
    script_idx = next((i for i, l in enumerate(body) if "ElevenLabs Hindi Voice Script" in l), None)
    if script_idx is None:
        return headers, "", errors + ["Section A is missing the ElevenLabs Hindi Voice Script line"]
    paragraph = [l.strip() for l in body[script_idx + 1:] if l.strip()]
    if not paragraph:
        errors.append("Section A voice script paragraph is empty")
    elif len(paragraph) > 1:
        errors.append("Section A must contain one continuous paragraph after the 5 header lines")
    return headers, " ".join(paragraph), errors


def _check_section_a_headers(headers: list[str], script: str) -> list[str]:
    errors = []
    if len(headers) != len(SECTION_A_FIELDS):
        errors.append(f"Section A has {len(headers)} header lines; required exactly {len(SECTION_A_FIELDS)}")
    for field in SECTION_A_FIELDS:
        if not any(h.startswith(f"- **{field}") for h in headers):
            errors.append(f"Section A is missing the '{field}' header line")
    count_line = next((h for h in headers if h.startswith("- **Total Character Count")), "")
    m = re.search(r"(\d+)", count_line)
    if m and script and int(m.group(1)) != len(script):
        errors.append(
            f"Section A 'Total Character Count' says {m.group(1)} but the script has {len(script)} characters"
        )
    return errors


def _check_prompt_text(prompt: str, label: str) -> list[str]:
    errors = []
    if DEVANAGARI.search(prompt):
        errors.append(f"{label}: Devanagari inside the English prompt")
    if re.search(r"['\"‘’“”]", prompt):
        errors.append(f"{label}: quotation marks or apostrophes inside the prompt")
    if not re.search(r"\ba young Indian (woman|man)\b", prompt):
        errors.append(f"{label}: missing 'a young Indian woman' / 'a young Indian man' description")
    minors = sorted({w.lower() for w in MINOR_WORDS.findall(prompt)})
    if minors:
        errors.append(f"{label}: content-filter risk words {minors}")
    if re.search(r"same as (IMG|VID)|same character|previous scene|this exact scene", prompt, re.IGNORECASE):
        errors.append(f"{label}: not self-contained (refers to another scene)")
    return errors


def _check_vid_prompt(prompt: str, label: str) -> list[str]:
    errors = _check_prompt_text(prompt, label)
    triggers = sorted({t.lower() for t in SPEECH_TRIGGERS.findall(prompt)})
    if triggers:
        errors.append(f"{label}: speech-trigger words {triggers}")
    if LIP_SYNC_PHRASE not in prompt:
        errors.append(f"{label}: missing mandatory silent lip-sync phrase")
    for word in ("blink", "pupil"):
        if word not in prompt.lower():
            errors.append(f"{label}: missing '{word}' motion")
    if AUDIO_PREFIX not in prompt or not prompt.rstrip().endswith(AUDIO_SUFFIX):
        errors.append(f"{label}: missing exact audio suffix")
    else:
        sfx = prompt.split(AUDIO_PREFIX, 1)[1].rsplit(AUDIO_SUFFIX, 1)[0].strip().rstrip(".")
        if not sfx:
            errors.append(f"{label}: audio suffix has no SFX listed")
        vocal = sorted({v.lower() for v in VOCAL_SFX.findall(sfx)})
        if vocal:
            errors.append(f"{label}: vocal sounds in Spot SFX {vocal}")
    return errors


def validate_artifact(text: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    lines = text.splitlines()

    # Rule 1 / Rule 8: structure, fences, placeholders
    for sec in ("A", "B", "C", "D"):
        if not any(l.startswith(f"# SECTION {sec}") for l in lines):
            errors.append(f"Missing '# SECTION {sec}' heading")
    if any(l.lstrip().startswith("```") for l in lines):
        errors.append("Artifact contains triple-backtick code fences")
    if "[" in text or "]" in text:
        errors.append("Artifact contains square-bracket characters")
    if re.search(r"<[^>\n]*>", text):
        errors.append("Artifact contains angle-bracket placeholders")
    for i, l in enumerate(lines, 1):
        if l.count("`") % 2:
            errors.append(f"Line {i}: unbalanced backticks")
        if l.count("**") % 2:
            errors.append(f"Line {i}: unbalanced bold markers")

    # Rule 2 + 55s ceiling: Section A
    headers, script, sa_errors = _section_a(lines)
    errors += sa_errors + _check_section_a_headers(headers, script)
    if script:
        e, w = validate_voice_script(script)
        errors += e
        warnings += w

    # Rule 3 / 4 / 5: IMG and VID lines
    imgs, vids = {}, []
    for i, l in enumerate(lines, 1):
        if l.lstrip().startswith(("- **IMG-", "**IMG-", "### IMG-")):
            m = IMG_LINE.match(l)
            if not m:
                errors.append(f"Line {i}: IMG line does not match the single-line parsing contract")
                continue
            num, chars, prompt = int(m.group(1)), int(m.group(3)), m.group(6)
            imgs[num] = chars
            errors += _check_prompt_text(prompt, f"IMG-{num:02d}")
        elif l.lstrip().startswith(("- **VID-", "**VID-", "### VID-")):
            m = VID_LINE.match(l)
            if not m:
                errors.append(f"Line {i}: VID line does not match the single-line parsing contract")
                continue
            num = int(m.group(1))
            start, end, dur = float(m.group(3)), float(m.group(4)), float(m.group(5))
            chars, prompt = int(m.group(6)), m.group(7)
            vids.append((num, start, end, dur, chars))
            errors += _check_vid_prompt(prompt, f"VID-{num:02d}")

    if not imgs:
        errors.append("No IMG prompts found")
    if not vids:
        errors.append("No VID prompts found")
    if imgs and vids and sorted(imgs) != [v[0] for v in sorted(vids)]:
        errors.append("IMG and VID prompts are not paired 1:1 by number")

    # 55.0s ceiling on the VID timeline
    prev_end = 0.0
    total = 0.0
    for num, start, end, dur, chars in sorted(vids):
        label = f"VID-{num:02d}"
        if abs(start - prev_end) > TIME_TOLERANCE:
            errors.append(f"{label}: starts at {start}s but previous scene ended at {prev_end}s")
        if abs((end - start) - dur) > TIME_TOLERANCE:
            errors.append(f"{label}: Duration {dur}s does not match {start}s–{end}s")
        if imgs.get(num) is not None and imgs[num] != chars:
            errors.append(f"{label}: Chars {chars} differs from IMG-{num:02d} Chars {imgs[num]}")
        expected = round(chars / CHARS_PER_SECOND, 1)
        if abs(expected - dur) > 0.2:
            warnings.append(f"{label}: Duration {dur}s differs from Chars ÷ {CHARS_PER_SECOND} = {expected}s")
        prev_end = end
        total += dur
    if vids:
        total = round(total, 1)
        if total > HARD_MAX_SECONDS:
            errors.append(f"Sum of VID durations is {total}s; hard ceiling is {HARD_MAX_SECONDS}s")
        if prev_end > HARD_MAX_SECONDS:
            errors.append(f"Last VID ends at {prev_end}s; hard ceiling is {HARD_MAX_SECONDS}s")
        if script:
            scene_chars = sum(v[4] for v in vids)
            if abs(scene_chars - len(script)) > 5:
                warnings.append(
                    f"Scene Chars sum to {scene_chars}, Section A script has {len(script)} characters"
                )

    # Rule 6: D1 thumbnail
    d1 = next((l for l in lines if l.startswith("- **D1 (")), "")
    if not d1:
        errors.append("Missing D1 thumbnail prompt line")
    else:
        for needle in ("9:16", "1024x1792", "central 80%", "No text, no captions, no watermark"):
            if needle not in d1:
                errors.append(f"D1 thumbnail prompt is missing '{needle}'")

    return errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a WO GALI V5 artifact (hard 55.0s ceiling).")
    ap.add_argument("artifact", help="Path to the Agent 1 Markdown artifact")
    ap.add_argument("--audio", help="Path to the generated voiceover MP3 (Agent 4 gate)")
    ap.add_argument("--audio-seconds", type=float, help="Measured voiceover duration in seconds")
    args = ap.parse_args(argv)

    try:
        text = Path(args.artifact).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read {args.artifact}: {exc}", file=sys.stderr)
        return 2

    errors, warnings = validate_artifact(text)
    try:
        if args.audio:
            errors += validate_audio_seconds(audio_duration_seconds(args.audio))
        if args.audio_seconds is not None:
            errors += validate_audio_seconds(args.audio_seconds)
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
        print(f"ERROR: cannot read audio duration: {exc}", file=sys.stderr)
        return 2

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"FAIL  {e}")
    print("PASS" if not errors else f"FAILED with {len(errors)} error(s)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
