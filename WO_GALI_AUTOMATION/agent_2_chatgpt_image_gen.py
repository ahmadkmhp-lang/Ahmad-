#!/usr/bin/env python3
r"""
WO GALI AUTOMATION — AGENT 2 (V10.0 NEW-UI HARDENED):
DUAL-TAB CHATGPT + AUTO REFERENCE-IMAGE FACE-LOCK + EP 07-20+ UNIVERSAL BATCH
==============================================================================
Run Commands in PowerShell:
    cd "C:\AI KHAN\FINAL NEW BEST STORY\WO_GALI_AUTOMATION"
    py -3.13 -u .\agent_2_chatgpt_image_gen.py "12-15"

    # Other supported runs:
    py -3.13 -u .\agent_2_chatgpt_image_gen.py "EP 07-10"
    py -3.13 -u .\agent_2_chatgpt_image_gen.py "11-20"
    py -3.13 -u .\agent_2_chatgpt_image_gen.py "ALL"
    py -3.13 -u .\agent_2_chatgpt_image_gen.py "15"
    py -3.13 -u .\agent_2_chatgpt_image_gen.py "STORY_10_Upar_wali_Berth.md"
    py -3.13 -u .\agent_2_chatgpt_image_gen.py            # interactive menu

LOCKED FLOW (unchanged from V9.2):
  1. Attach to Brave over CDP (http://127.0.0.1:9222, profile ./brave_profiles/chatgpt_profile) or start it.
     A Brave window the script attached to is never closed.
  2. TAB-1 opens on https://chatgpt.com/ -> press [ENTER] in PowerShell -> TAB-2 opens automatically.
  3. Phase 1: IMG_001 master anchor on TAB-1. Phase 2: TAB-1 = ODD (3, 5, 7...) and TAB-2 = EVEN (2, 4, 6...)
     in parallel, each in its own continuous chat. Every image after IMG_001 (THUMBNAIL included) uploads up to
     2 reference PNGs (IMG_001 + nearest previous saved scene) with REF_INSTRUCTION before the verbatim
     # SECTION B / D1 prompt.
  4. Fresh chats on both tabs for every episode. Resume comes only from valid PNGs on disk
     (PIL verify, min side >= 512, >= 25 KB, SHA-256 duplicate guard).
  5. Names: EP_XX_<StorySlug>_IMAGES / IMG_001_EP_XX_<StorySlug>.png .. IMG_0NN_THUMBNAIL_EP_XX_<StorySlug>.png

WHAT V10.0 CHANGES (ChatGPT 2026 layouts):
  - Finds your sent message and the generated image without data-message-author-role, conversation-turn ids
    or #prompt-textarea (old article/section layout, data-turn-key layout and the bare app-shell layout).
  - Saves the image by fetching its own src inside the page (the same file the Download button saves), so it
    needs no Edit/Share/Download clicks and no UI lock. Share -> Download is only a last fallback.
  - Uploaded reference images are never saved as results: DOM order after your message, user-bubble markers,
    SHA-256 and a perceptual hash against every saved PNG of the episode.
  - The UI lock is held only while attaching/typing and clicking Send. Waiting, downloading and saving run in
    parallel on both tabs.
  - No chat-state file and no lock crash: a tab follows ChatGPT's temporary -> final /c/<id>; a tab that lost its
    chat gets a fresh chat (the reference upload keeps faces locked).
  - Shared cooldown that reads "resets in 9 minutes" / "after 4:30 PM". Rate-limit waits do not use up retries.
  - Recovery for crashed/closed tabs, Cloudflare/login pauses, failed sends and "conversation too long".
  - No global Brave download-folder override (V9.2 pointed Brave downloads at a temp folder it later deleted).

Optional config.json keys (defaults):
  "brave_executable_path", "brave_chatgpt_profile_dir": "./brave_profiles/chatgpt_profile",
  "chatgpt_url": "https://chatgpt.com/", "remote_debugging_port": 9222,
  "generation_timeout_sec": 300, "composer_wait_sec": 900
"""

import asyncio
import base64
import ctypes
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from PIL import Image
from playwright.async_api import Page, async_playwright


VERSION = "V10.0"
STATE_FILE = "_active_story_state.json"
MIN_IMAGE_BYTES = 25_000
MIN_IMAGE_SIDE = 512
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
IGNORE_MD_WORDS = {"GUIDE", "README", "AGENT", "SETUP", "WORKFLOW", "PROMPT", "MASTER", "REQUIREMENT", "SUMMARY", "AUDITOR"}
MAX_REFS = 2

REF_INSTRUCTION = (
    "Match ONLY the exact character faces (main and supporting), hair, outfits, and 2D webtoon art style "
    "from the attached reference image(s). Do NOT copy the old pose or camera angle. "
    "Draw the exact new verbatim scene: "
)
ANCHOR_PREFIX = "Generate this exact image: "

# Timing (seconds). Module-level so they are easy to tune.
POLL_SEC = 2.0
FIRST_POLL_DELAY_SEC = 3.0
SEND_CONFIRM_SEC = 20.0
UPLOAD_READY_SEC = 90.0
ATTACH_CONFIRM_SEC = 12.0
NUDGE_EVERY_SEC = 30.0
SETTLE_FALLBACK_SEC = 25.0
COOLDOWN_MIN_SEC = 90
COOLDOWN_MARGIN_SEC = 15
COOLDOWN_DEFAULT_SEC = 300
COOLDOWN_MAX_SEC = 24 * 3600
MAX_RATE_LIMIT_WAITS_PER_ITEM = 8
ANCHOR_ATTEMPTS = 3
DHASH_DUP_MAX_BITS = 10

# Attempt outcomes
OK = "ok"
RATE_LIMITED = "rate_limited"
FAILED = "failed"
BROKEN = "broken"
NEEDS_FRESH_CHAT = "needs_fresh_chat"

RATE_LIMIT_RE = re.compile(
    r"rate.limit|too many requests|(?:image|generation|upload|usage|message)s?\s+limit|"
    r"limit\s+(?:for|on|reached)|you.ve (?:hit|reached)[^\n]{0,80}limit|hit the [a-z ]{0,24}limit|"
    r"try again (?:in|after)|cooldown|(?:generating|creating) images too quickly|limit resets|"
    r"create more images when",
    re.I,
)
# Dialog text (e.g. "What's new: higher image limits") is only treated as a rate limit with these phrases.
RATE_LIMIT_DIALOG_RE = re.compile(
    r"you.ve (?:hit|reached)[^\n]{0,80}limit|limit resets|try again (?:in|after)|too many requests|"
    r"(?:generating|creating) images too quickly",
    re.I,
)
ERROR_RE = re.compile(
    r"something went wrong|an error occurred|error (?:occurred|generating|while generating)|experienced an error|"
    r"network error|there was an error|unable to load|failed to (?:generate|load|create)|hmm\.{2,3}\s*something",
    re.I,
)
REFUSAL_RE = re.compile(
    r"content polic|violat\w* (?:our|the|content|usage)|guardrails|"
    r"(?:can.t|cannot|can not|unable to|not able to|won.t be able to)\s+(?:help with|create|generate|make|produce|draw)",
    re.I,
)
TOO_LONG_RE = re.compile(
    r"maximum (?:conversation )?length|conversation (?:is )?too long|reached the (?:maximum|max) (?:length|context)",
    re.I,
)
BUSY_TEXT_RE = re.compile(
    r"\b(?:creating|generating|making|rendering|drawing|editing|preparing)\b[^.\n]{0,40}\bimage\b|"
    r"\bimage creation in progress\b|\bthinking\b|\bworking on (?:it|your)|\bgetting started\b|\balmost (?:done|there)\b",
    re.I,
)

EPISODE_TOPIC_REGISTRY: Dict[int, Tuple[str, str]] = {
    7: ("बाथरूम के नल की आवाज", "Raat_Teen_Baje_ka_Nal"),
    8: ("पड़ोसी की खिड़की", "Padosi_ki_Khidki"),
    9: ("अस्पताल का वार्ड नंबर नौ", "Ward_Number_9"),
    10: ("ट्रेन की ऊपर वाली बर्थ", "Upar_wali_Berth"),
    11: ("रसोई का बोलता स्पीकर", "Bolta_Speaker"),
    12: ("कल की तारीख वाला पार्सल", "Kal_ka_Parcel"),
    13: ("भूला हुआ कॉलेज दोस्त", "Bhoola_Hua_Dost"),
    14: ("सपने वाला पुराना बाजार", "Sapne_Wala_Bazaar"),
    15: ("शादी की तस्वीर का मेहमान", "Tasveer_ka_Mehmaan"),
    16: ("पत्थर की आखिरी सीमा", "Patthar_ki_Seema"),
    17: ("दुकान की बूढ़ी ग्राहक", "Boodhi_Grahak"),
    18: ("2 मिनट वाली बस", "2_Minute_Wali_Bus"),
    19: ("कोहरे में गायब ढाबा", "Kohre_ka_Dhaba"),
    20: ("बारिश का खाली मोड़", "Barish_ka_Mod"),
}


# =============================================================================
# Logging / OS helpers
# =============================================================================
def setup_console() -> None:
    """Never crash on emoji/Devanagari when PowerShell output is redirected to a file."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def log(msg: str = "") -> None:
    body = msg.lstrip("\n")
    lead = "\n" * (len(msg) - len(body))
    print(f"{lead}[{time.strftime('%H:%M:%S')}] {body}" if body else lead, flush=True)


def short_err(exc: BaseException, limit: int = 160) -> str:
    text = (str(exc) or exc.__class__.__name__).strip().splitlines()
    return (text[0] if text else exc.__class__.__name__)[:limit]


def fmt_secs(sec: float) -> str:
    sec = int(max(0, round(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def prevent_windows_sleep(enable: bool = True) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000043 if enable else 0x80000000)
    except Exception:
        pass


# =============================================================================
# File / PNG helpers
# =============================================================================
def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_PNG_CHECK_CACHE: Dict[str, Tuple[int, int, bool]] = {}


def _check_png_file(path: Path) -> bool:
    try:
        with Image.open(path) as im:
            if im.format != "PNG":
                return False
            im.verify()
        with Image.open(path) as im:
            if min(im.size) < MIN_IMAGE_SIDE:
                return False
            im.load()
        return True
    except Exception:
        return False


def is_valid_png_file(path: Path) -> bool:
    """Genuine PNG (PIL verify + full decode), min side >= 512, >= 25 KB. Cached by size + mtime."""
    try:
        st = path.stat()
    except OSError:
        return False
    if not path.is_file() or st.st_size < MIN_IMAGE_BYTES:
        return False
    key = str(path)
    cached = _PNG_CHECK_CACHE.get(key)
    if cached and cached[0] == st.st_size and cached[1] == st.st_mtime_ns:
        return cached[2]
    ok = _check_png_file(path)
    _PNG_CHECK_CACHE[key] = (st.st_size, st.st_mtime_ns, ok)
    return ok


def ensure_true_png_bytes(raw_bytes: bytes) -> Optional[bytes]:
    """Validates PNG bytes, or losslessly re-encodes WebP/JPEG bytes into a genuine >=512px PNG."""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as im:
            if min(im.size) < MIN_IMAGE_SIDE:
                return None
            im.load()
            if im.format == "PNG" and raw_bytes.startswith(PNG_MAGIC) and len(raw_bytes) >= MIN_IMAGE_BYTES:
                return raw_bytes
            frame = im
            if frame.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                frame = frame.convert("RGBA" if "A" in frame.getbands() else "RGB")
            buf = io.BytesIO()
            frame.save(buf, format="PNG")
            out = buf.getvalue()
            return out if len(out) >= MIN_IMAGE_BYTES else None
    except Exception:
        return None


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """tmp file + os.replace, retrying briefly because Windows antivirus/indexers can hold new files."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    for attempt in range(8):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.25 * (attempt + 1))
    os.replace(tmp, path)


def ensure_true_png_file(src_path: Path, dst_path: Path) -> bool:
    out = ensure_true_png_bytes(src_path.read_bytes())
    if not out:
        return False
    atomic_write_bytes(dst_path, out)
    if src_path.resolve() != dst_path.resolve():
        try:
            src_path.unlink(missing_ok=True)
        except Exception:
            pass
    return True


_RESAMPLE = getattr(Image, "Resampling", Image).BILINEAR


def dhash_bits(source) -> Optional[int]:
    """256-bit difference hash. Re-encoded or resized copies of one image stay within a few bits."""
    try:
        src = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
        with Image.open(src) as im:
            data = im.convert("L").resize((17, 16), _RESAMPLE).tobytes()
        bits = 0
        for y in range(16):
            row = data[y * 17:(y + 1) * 17]
            for x in range(16):
                bits = (bits << 1) | (1 if row[x] < row[x + 1] else 0)
        return bits
    except Exception:
        return None


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def png_size(data: bytes) -> Tuple[int, int]:
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return (0, 0)


# =============================================================================
# Story parsing / naming (same rules as V9.2 so existing folders resume)
# =============================================================================
def extract_episode_number(md_stem: str) -> Optional[int]:
    m = re.match(r"^(?:STORY|EP(?:ISODE)?)[_\-\s]*0*(\d+)(?=[_\-\s]|$)", md_stem, re.IGNORECASE)
    return int(m.group(1)) if m else None


def build_short_ep_slug(md_stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", md_stem).strip("_")
    m = re.match(r"^(?:STORY|EP(?:ISODE)?)_0*(\d+)(?:_(.*))?$", cleaned, re.IGNORECASE)
    if m:
        ep_num = int(m.group(1))
        rest = (m.group(2) or "").strip("_")
        if ep_num in EPISODE_TOPIC_REGISTRY and (not rest or rest.casefold() == EPISODE_TOPIC_REGISTRY[ep_num][1].casefold()):
            rest = EPISODE_TOPIC_REGISTRY[ep_num][1]
        slug = f"EP_{ep_num:02d}_{rest}" if rest else f"EP_{ep_num:02d}"
    else:
        slug = cleaned or "EP_01_STORY"
    return slug[:36].strip("_")


def extract_story_topic_name(md_path: Path) -> str:
    try:
        txt = md_path.read_text(encoding="utf-8-sig", errors="ignore")
        m_name = re.search(r"\*\*Story\s+Name:?\*\*\s*:?\s*(.+)", txt, re.IGNORECASE)
        if m_name:
            return m_name.group(1).strip()
        m_banner = re.search(r"\*\*Top\s+Yellow\s+Banner\s+Text:?\*\*\s*:?\s*(.+)", txt, re.IGNORECASE)
        if m_banner:
            return m_banner.group(1).strip()
    except Exception:
        pass
    ep_num = extract_episode_number(md_path.stem)
    if ep_num and ep_num in EPISODE_TOPIC_REGISTRY:
        return f"{EPISODE_TOPIC_REGISTRY[ep_num][0]} ({EPISODE_TOPIC_REGISTRY[ep_num][1]})"
    return md_path.stem


def load_config(config_path: str = "config.json") -> Dict:
    default_cfg = {
        "brave_executable_path": "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
        "brave_chatgpt_profile_dir": "./brave_profiles/chatgpt_profile",
        "chatgpt_url": "https://chatgpt.com/",
        "remote_debugging_port": 9222,
        "generation_timeout_sec": 300,
        "composer_wait_sec": 900,
    }
    if os.path.exists(config_path):
        try:
            data = json.loads(Path(config_path).read_text(encoding="utf-8-sig", errors="replace"))
            return {**default_cfg, **data}
        except Exception as exc:
            log(f"⚠️ config.json could not be read ({short_err(exc)}) — using defaults.")
    return default_cfg


def resolve_brave_executable(configured_path: str) -> Optional[str]:
    candidates = [
        configured_path,
        r"C:\Users\Gulab-Khan\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return str(Path(c).resolve())
    return None


def parse_all_image_and_thumbnail_prompts_from_md(md_path: Path) -> Tuple[List[Tuple[int, str]], Optional[str]]:
    """Extracts verbatim IMG-01..IMG-N prompts from # SECTION B and D1 Thumbnail from # SECTION D."""
    txt = md_path.read_text(encoding="utf-8-sig", errors="ignore")

    sec_b_match = re.search(r"#\s*SECTION\s+B\b.*?(?=#\s*SECTION\s+[CD]\b|\Z)", txt, re.DOTALL | re.IGNORECASE)
    sec_b_txt = sec_b_match.group(0) if sec_b_match else txt

    results: Dict[int, str] = {}

    for m in re.finditer(r"\*\*IMG-0*(\d+)[^*\n]*\*\*\s*:?\s*`([^\n`]+)`?", sec_b_txt, re.IGNORECASE):
        idx = int(m.group(1))
        prompt_str = m.group(2).strip()
        if idx not in results and len(prompt_str) > 30:
            results[idx] = prompt_str

    for blk in re.findall(r"<image_prompt>\s*(.*?)\s*</image_prompt>", sec_b_txt, re.DOTALL):
        m = re.search(r"IMG-0*(\d+)", blk, re.IGNORECASE)
        idx = int(m.group(1)) if m else (len(results) + 1)
        clean = re.sub(r"^IMG-0*\d+\s*\([^)]*\)\s*:\s*", "", blk.strip(), flags=re.IGNORECASE)
        if idx not in results and len(clean) > 30:
            results[idx] = clean

    for m in re.finditer(
        r"###\s*IMG-0*(\d+)\b[^\n]*\n(?:(?!###\s*IMG-).)*?```(?:text)?\s*\n(.*?)```",
        sec_b_txt,
        re.DOTALL | re.IGNORECASE,
    ):
        idx = int(m.group(1))
        prompt_str = re.sub(r"\s+", " ", m.group(2)).strip()
        if idx not in results and len(prompt_str) > 30:
            results[idx] = prompt_str

    for line in sec_b_txt.splitlines():
        m = re.search(r"\*\*IMG-0*(\d+)[^*]*\*\*\s*:?\s*(.+)$", line.strip(), re.IGNORECASE)
        if m:
            idx = int(m.group(1))
            if idx not in results:
                prompt_str = m.group(2).strip().strip("`\"'")
                if len(prompt_str) > 30:
                    results[idx] = prompt_str

    sec_d_match = re.search(r"#\s*SECTION\s+D\b.*$", txt, re.DOTALL | re.IGNORECASE)
    sec_d_txt = sec_d_match.group(0) if sec_d_match else txt
    d1_thumb: Optional[str] = None
    m_d1 = re.search(r"\*\*D1\s*\([^)\n]*Thumbnail[^)\n]*\):?\*\*\s*:?\s*`([^\n`]+)`?", sec_d_txt, re.IGNORECASE)
    if m_d1 and len(m_d1.group(1).strip()) > 30:
        d1_thumb = m_d1.group(1).strip()
    else:
        m_d2 = re.search(r"##\s*D1\.\s*Thumbnail[^\n]*\n+```(?:text)?\s*\n(.*?)```", sec_d_txt, re.DOTALL | re.IGNORECASE)
        if m_d2 and len(m_d2.group(1).strip()) > 30:
            d1_thumb = re.sub(r"\s+", " ", m_d2.group(1)).strip()

    return sorted(results.items(), key=lambda x: x[0]), d1_thumb


def list_valid_story_mds(base_dir: Path) -> List[Path]:
    mds = []
    for f in base_dir.glob("*.md"):
        if any(ig in f.name.upper() for ig in IGNORE_MD_WORDS):
            continue
        if parse_all_image_and_thumbnail_prompts_from_md(f)[0]:
            mds.append(f.resolve())

    def _sort_key(p: Path) -> Tuple[int, int, str]:
        ep = extract_episode_number(p.stem)
        return (0, ep, p.name.lower()) if ep is not None else (1, 999, p.name.lower())

    mds.sort(key=_sort_key)
    return mds


_BARE_SELECTOR_WORDS = {"EP", "EPS", "EPISODE", "EPISODES", "STORY", "STORIES", "MD"}


def _match_stories_by_token(token: str, base_dir: Path, all_valid: List[Path]) -> List[Path]:
    token_clean = token.strip().strip("\"'")
    if not token_clean or token_clean.upper() in _BARE_SELECTOR_WORDS:
        return []
    if token_clean.upper() == "ALL":
        return list(all_valid)

    m_range = re.match(
        r"^(?:EP(?:ISODES?)?|STORY)?[_\-\s]*0*(\d+)\s*(?:-|–|—|to)\s*(?:EP(?:ISODES?)?|STORY)?[_\-\s]*0*(\d+)$",
        token_clean,
        re.IGNORECASE,
    )
    if m_range:
        lo, hi = sorted((int(m_range.group(1)), int(m_range.group(2))))
        matched = [f for f in all_valid if (extract_episode_number(f.stem) is not None and lo <= extract_episode_number(f.stem) <= hi)]
        present = {extract_episode_number(f.stem) for f in matched}
        missing = [n for n in range(lo, hi + 1) if n not in present]
        if missing:
            log(f"⚠️ Missing .md files for {', '.join(f'EP {n:02d}' for n in missing)} — continuing with available episodes.")
        return matched

    m_single = re.match(r"^(?:EP(?:ISODE)?|STORY)?[_\-\s]*0*(\d+)$", token_clean, re.IGNORECASE)
    if m_single:
        target_ep = int(m_single.group(1))
        hits = [f for f in all_valid if extract_episode_number(f.stem) == target_ep]
        if not hits:
            log(f"⚠️ Missing .md file for EP {target_ep:02d}.")
        return hits

    cand = Path(token_clean)
    if not cand.is_absolute():
        cand = (base_dir / token_clean).resolve()
    if cand.exists() and cand.is_file():
        return [cand]

    if len(token_clean) >= 3:
        for f in all_valid:
            if token_clean.upper() in f.name.upper():
                return [f]
    return []


def _resolve_tokens(parts: List[str], base_dir: Path, all_valid: List[Path]) -> List[Path]:
    selected: List[Path] = []
    for part in parts:
        hits = _match_stories_by_token(part, base_dir, all_valid)
        if not hits and re.search(r"\s", part):
            for sub in part.split():
                hits.extend(_match_stories_by_token(sub, base_dir, all_valid))
        for f in hits:
            if f not in selected:
                selected.append(f)
    return selected


async def resolve_story_batch(base_dir: Path, cli_story_args: List[str]) -> List[Path]:
    all_valid = list_valid_story_mds(base_dir)
    if cli_story_args:
        joined = " ".join(a.strip() for a in cli_story_args if a.strip())
        parts = [p.strip() for p in re.split(r"[,;]+", joined) if p.strip()]
        selected = _resolve_tokens(parts, base_dir, all_valid)
        if selected:
            return selected
        raise FileNotFoundError(f"Could not find story .md file(s) matching: {cli_story_args}")

    if not all_valid:
        raise FileNotFoundError("No Story .md file with Section B (IMG-01..IMG-N) prompts found in folder!")
    if len(all_valid) == 1:
        return all_valid

    log(f"\n📂 Available Story Files for ChatGPT Dual-Tab Image Generation ({VERSION}):")
    for idx, st in enumerate(all_valid, 1):
        prompts, thumb = parse_all_image_and_thumbnail_prompts_from_md(st)
        topic = extract_story_topic_name(st)
        log(f"   [{idx:02d}] {st.name}  ({len(prompts) + (1 if thumb else 0)} images) | {topic}")
    log("   Tip: Enter menu numbers (e.g., 1,2), episode range (e.g., 10-15 or 11-20), or ALL!")
    raw = (await asyncio.to_thread(input, f"  Select Story Number(s) / Range [Default: last story {len(all_valid)}]: ")).strip()
    if not raw:
        return [all_valid[-1]]
    if raw.upper() == "ALL":
        return list(all_valid)

    chosen: List[Path] = []
    for part in [p for p in re.split(r"[,;]+", raw) if p.strip()]:
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= len(all_valid):
            hits = [all_valid[int(part) - 1]]
        elif re.fullmatch(r"\d+(?:\s+\d+)+", part):
            hits = [all_valid[int(n) - 1] for n in part.split() if 1 <= int(n) <= len(all_valid)]
        else:
            hits = _resolve_tokens([part], base_dir, all_valid)
        for p in hits:
            if p not in chosen:
                chosen.append(p)
    return chosen or [all_valid[-1]]


def is_image_already_saved(images_dir: Path, img_num: int, ep_slug: str, legacy_slug: str, is_thumb: bool = False) -> Optional[Path]:
    candidates = [
        images_dir / (f"IMG_{img_num:03d}_THUMBNAIL_{ep_slug}.png" if is_thumb else f"IMG_{img_num:03d}_{ep_slug}.png"),
        images_dir / (f"IMG_{img_num:03d}_THUMBNAIL_{legacy_slug}.png" if is_thumb else f"IMG_{img_num:03d}_{legacy_slug}.png"),
        images_dir / (f"{ep_slug}_THUMBNAIL_9x16.png" if is_thumb else f"IMG-{img_num:02d}.png"),
        images_dir / f"IMG_{img_num:02d}_{ep_slug}.png",
    ]
    for c in candidates:
        if is_valid_png_file(c):
            return c
    return None


def build_story_queue(base_dir: Path, md_path: Path, include_thumb: bool = True) -> Tuple[Path, str, List[Dict]]:
    ep_slug = build_short_ep_slug(md_path.stem)
    legacy_slug = re.sub(r"[^A-Za-z0-9]+", "_", md_path.stem).strip("_")[:32]
    images_dir = (base_dir / f"{ep_slug}_IMAGES").resolve()
    images_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "story_md_path": str(md_path.resolve()),
        "story_md_name": md_path.name,
        "story_topic": extract_story_topic_name(md_path),
        "story_slug": ep_slug,
        "legacy_slug": legacy_slug,
        "images_folder": str(images_dir),
        "videos_folder": str((base_dir / "ALL STORY VID").resolve()),
    }
    atomic_write_bytes(base_dir / STATE_FILE, json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8"))

    prompts, d1_thumb = parse_all_image_and_thumbnail_prompts_from_md(md_path)
    if not prompts:
        raise ValueError(f"Zero IMG-01..IMG-N prompts found inside Section B of '{md_path.name}'!")

    queue: List[Dict] = []
    for img_num, p_text in prompts:
        img_code = f"IMG_{img_num:03d}"
        out_file = images_dir / f"IMG_{img_num:03d}_{ep_slug}.png"
        existing = is_image_already_saved(images_dir, img_num, ep_slug, legacy_slug, is_thumb=False)
        if existing and existing.resolve() != out_file.resolve():
            ensure_true_png_file(existing, out_file)
        queue.append({"index": img_num, "img_code": img_code, "prompt": p_text, "output_path": out_file})

    if d1_thumb and include_thumb:
        thumb_num = prompts[-1][0] + 1
        out_thumb = images_dir / f"IMG_{thumb_num:03d}_THUMBNAIL_{ep_slug}.png"
        existing_t = is_image_already_saved(images_dir, thumb_num, ep_slug, legacy_slug, is_thumb=True)
        if existing_t and existing_t.resolve() != out_thumb.resolve():
            ensure_true_png_file(existing_t, out_thumb)
        queue.append({"index": thumb_num, "img_code": f"IMG_{thumb_num:03d}_THUMBNAIL", "prompt": d1_thumb, "output_path": out_thumb})

    return images_dir, ep_slug, queue


def select_reference_images_for_item(queue: List[Dict], current_index: int) -> List[Path]:
    """IMG_001 + the nearest previous saved scene PNG (max 2). Re-evaluated at every submit."""
    if current_index <= 1:
        return []
    refs: List[Path] = []
    for it in queue:
        if it["index"] == 1:
            p1: Path = it["output_path"]
            if is_valid_png_file(p1):
                refs.append(p1.resolve())
            break
    prev_candidates = [it for it in queue if 1 < it["index"] < current_index]
    prev_candidates.sort(key=lambda x: x["index"], reverse=True)
    for it in prev_candidates:
        pp: Path = it["output_path"]
        if is_valid_png_file(pp):
            rp = pp.resolve()
            if rp not in refs:
                refs.append(rp)
            break
    return refs[:MAX_REFS]


# =============================================================================
# Shared rate-limit cooldown
# =============================================================================
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", re.I)
_CLOCK_RE = re.compile(r"\b(?:at|after|until|by)\s+(\d{1,2}):(\d{2})\s*([ap]\.?\s?m\.?)?", re.I)


def parse_wait_seconds(text: str) -> int:
    """'resets in 1 hour 5 minutes' -> 3900, 'try again after 4:30 PM' -> seconds until then, else 0."""
    best = 0.0
    for line in (text or "").splitlines() or [""]:
        total = 0.0
        for n, unit in _DURATION_RE.findall(line):
            u = unit.lower()
            total += float(n) * (3600 if u.startswith("h") else 60 if u.startswith("m") else 1)
        if not total and re.search(r"\b(?:an|one) hour\b", line, re.I):
            total = 3600
        if not total and re.search(r"\b(?:a|one) minute\b", line, re.I):
            total = 60
        m = _CLOCK_RE.search(line)
        if m:
            hh, mm, ampm = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower().replace(".", "").replace(" ", "")
            if ampm == "pm" and hh < 12:
                hh += 12
            if ampm == "am" and hh == 12:
                hh = 0
            if hh < 24 and mm < 60:
                now = datetime.now()
                target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                total = max(total, (target - now).total_seconds())
        best = max(best, total)
    return int(best)


class Cooldown:
    """One cooldown shared by both tabs. A rate limit seen on either tab pauses new prompts on both."""

    def __init__(self) -> None:
        self.until = 0.0

    def remaining(self) -> float:
        return max(0.0, self.until - time.monotonic())

    def mark(self, text: str, who: str) -> float:
        secs = parse_wait_seconds(text)
        delay = min(COOLDOWN_MAX_SEC, max(COOLDOWN_MIN_SEC, secs + COOLDOWN_MARGIN_SEC)) if secs else COOLDOWN_DEFAULT_SEC
        new_until = time.monotonic() + delay
        if new_until > self.until + 5:
            self.until = new_until
            line = next((ln for ln in (text or "").splitlines() if RATE_LIMIT_RE.search(ln)), text or "")
            resume = (datetime.now() + timedelta(seconds=delay)).strftime("%H:%M:%S")
            log(f"  ⏳ [{who}] Rate limit: \"{snippet(line)}\" — shared cooldown {fmt_secs(delay)} (both tabs resume ≈ {resume})")
        return delay

    async def wait(self, who: str) -> None:
        if self.remaining() <= 0:
            return
        log(f"  ⏳ [{who}] Waiting for shared cooldown ({fmt_secs(self.remaining())} left)...")
        last_note = time.monotonic()
        while self.remaining() > 0:
            await asyncio.sleep(min(15.0, max(0.5, self.remaining())))
            if self.remaining() > 0 and time.monotonic() - last_note >= 300:
                log(f"  ⏳ [{who}] Still cooling down — {fmt_secs(self.remaining())} left...")
                last_note = time.monotonic()


# =============================================================================
# Anchor keys: short, markdown-safe pieces of the message used to find it in the chat
# =============================================================================
_KEY_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.:;()/-")


def _safe_window(text: str, max_len: int, skip_partial_word: bool) -> str:
    text = re.sub(r"\s+", " ", text)
    if skip_partial_word and " " in text:
        text = text[text.index(" ") + 1:]
    out = []
    for ch in text:
        if ch not in _KEY_SAFE_CHARS or len(out) >= max_len:
            break
        out.append(ch)
    window = "".join(out)
    if len(out) >= max_len and " " in window:
        window = window[: window.rindex(" ")]
    return window.strip()


def _first_safe_run(text: str, min_len: int, max_len: int) -> str:
    text = re.sub(r"\s+", " ", text)
    run: List[str] = []
    for ch in text + "\x00":
        if ch in _KEY_SAFE_CHARS:
            run.append(ch)
            continue
        candidate = "".join(run).strip()
        if len(candidate) >= min_len:
            return _safe_window(candidate, max_len, False)
        run = []
    return ""


def anchor_keys(prefix: str, verbatim: str) -> List[str]:
    """[unique key spanning prefix->scene text, shared head of the message]. Quote-free, so XPath-safe."""
    full = re.sub(r"\s+", " ", prefix + verbatim).strip()
    keys: List[str] = []
    start = max(0, len(prefix.rstrip()) - 26)
    unique = _safe_window(full[start:], 96, True)
    if len(unique) < 40:
        unique = _first_safe_run(verbatim, 40, 90)
    if unique:
        keys.append(unique)
    head = _safe_window(full, 64, False)
    if len(head) >= 24 and head not in keys:
        keys.append(head)
    return keys


_UI_WORDS_RE = re.compile(r"^(?:(?:edit message|edit|copy|share|you said:?|chatgpt said:?)\s*)+", re.I)


def snippet(text: str, limit: int = 160) -> str:
    """Last part of a reply for the log, without leading button labels such as 'Edit'/'Copy'."""
    s = _UI_WORDS_RE.sub("", (text or "").strip())
    return s if len(s) <= limit else "…" + s[-limit:]


def norm_text(s: str) -> str:
    s = (s or "").replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s).strip()


# =============================================================================
# Page-side JavaScript (marker-independent; works on old and 2026 ChatGPT layouts)
# =============================================================================
JS_PRELUDE = r"""
  const norm = (s) => String(s || '')
    .replace(/[\u2018\u2019\u201A\u201B\u2032]/g, "'")
    .replace(/[\u201C\u201D\u201E\u201F\u2033]/g, '"')
    .replace(/[\u2010-\u2015]/g, '-')
    .replace(/[\s\u00A0\u200B]+/g, ' ')
    .trim();
  const isShown = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity || '1') > 0.05;
  };
  const after = (a, b) => !!(a && b && a !== b && !a.contains(b) &&
    (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
  const labelOf = (b) => ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '') + ' ' +
    (b.getAttribute('data-testid') || '') + ' ' + (b.getAttribute('data-test-id') || '')).toLowerCase();
  const EDITOR_SELECTORS = [
    'form[data-chatgpt-composer] [contenteditable="true"][role="textbox"]',
    '#prompt-textarea[contenteditable="true"]', '#prompt-textarea',
    '[data-testid="prompt-textarea"]', '[data-testid="composer-text-input"]',
    'div.ProseMirror[contenteditable="true"]', 'form [contenteditable="true"][role="textbox"]',
    'form [contenteditable="true"]', 'form textarea', '[contenteditable="true"][role="textbox"]'
  ];
  const findEditor = () => {
    for (const sel of EDITOR_SELECTORS) {
      let found = [];
      try { found = Array.from(document.querySelectorAll(sel)).filter(isShown); } catch (e) { found = []; }
      if (found.length) return found[found.length - 1];
    }
    return null;
  };
  const composerRootOf = (ed) => {
    if (ed) return ed.closest('form') || ed.closest('[data-testid*="composer" i]') || ed.parentElement;
    return document.querySelector('form[data-chatgpt-composer]');
  };
  const STOP_SEL = '[data-testid="stop-button"], [data-test-id="stop-button"], button[data-testid*="stop" i], ' +
    'button[data-test-id*="stop" i], button[aria-label*="Stop" i], #composer-submit-button[aria-label*="Stop" i]';
  const SEND_SEL = '[data-testid="send-button"], [data-test-id="send-button"], #composer-submit-button, ' +
    'button[aria-label*="Send" i], button[data-testid*="send" i], form[data-chatgpt-composer] button[type="submit"]';
  const findSends = (root) => {
    const all = Array.from(document.querySelectorAll(SEND_SEL)).filter(b => isShown(b) && !/stop/.test(labelOf(b)));
    const inRoot = root ? all.filter(b => root.contains(b)) : [];
    return inRoot.length ? inRoot : all;
  };
  const keyOf = (src) => {
    try {
      if (!src) return '';
      if (src.startsWith('data:')) {
        let h = 2166136261;
        const step = Math.max(1, Math.floor(src.length / 4096));
        for (let i = 0; i < src.length; i += step) { h ^= src.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
        return 'data:' + src.length + ':' + h.toString(16);
      }
      if (src.startsWith('blob:')) return src;
      const u = new URL(src, location.href);
      const id = u.searchParams.get('id') || u.searchParams.get('file_id');
      if (id) return 'id:' + id;
      const m = u.pathname.match(/file[-_][A-Za-z0-9]{6,}/);
      if (m) return 'file:' + m[0];
      return u.origin + u.pathname;
    } catch (e) { return String(src).slice(0, 300); }
  };
  const USER_SEL = '[data-user-message-bubble="true"], [data-message-author-role="user"], [data-turn="user"], ' +
    '[data-content-search-unit-key$=":user"], [data-chatgpt-search-unit-key$=":user"]';
  const ASSIST_SEL = '[data-message-author-role="assistant"], [data-turn="assistant"], ' +
    '[data-content-search-unit-key$=":assistant"], [data-chatgpt-search-unit-key*="assistant"], ' +
    '[data-markdown-text-style="assistant-message"]';
"""

JS_SCAN = "(args) => {" + JS_PRELUDE + r"""
  const keys = (args && args.keys) || [];
  const preKeys = new Set((args && args.preKeys) || []);
  const fileNames = (args && args.fileNames) || [];
  const out = { url: location.href, title: document.title || '', hidden: document.visibilityState === 'hidden' };

  const editor = findEditor();
  const composerRoot = composerRootOf(editor);
  const inComposer = (el) => !!(composerRoot && composerRoot.contains(el));
  out.hasEditor = !!editor;
  out.editorText = editor ? norm(editor.innerText || editor.value || editor.textContent || '') : '';

  out.challenge = /just a moment|attention required|verify you are human|checking your browser|请稍候/i.test(out.title) ||
    !!document.querySelector('iframe[src*="challenges.cloudflare.com"], #challenge-form, #challenge-stage');
  let loggedOut = !!Array.from(document.querySelectorAll('[data-testid="login-button"]')).find(isShown);
  if (!loggedOut) {
    const btns = Array.from(document.querySelectorAll('button, a')).slice(0, 400);
    loggedOut = !!btns.find(b => isShown(b) && b.getBoundingClientRect().top < 140 &&
      /^(log in|login|sign in)$/i.test(norm(b.innerText || b.textContent)));
  }
  out.loggedOut = loggedOut;

  out.stopVisible = Array.from(document.querySelectorAll(STOP_SEL)).some(isShown);
  const sends = findSends(composerRoot);
  out.sendVisible = sends.length > 0;
  out.sendEnabled = sends.some(b => !b.disabled && b.getAttribute('aria-disabled') !== 'true');

  let attachImgs = 0, removeBtns = 0, nameHits = 0, uploading = false;
  if (composerRoot) {
    attachImgs = Array.from(composerRoot.querySelectorAll('img')).filter(im => {
      const r = im.getBoundingClientRect(); return r.width >= 24 && r.height >= 24; }).length;
    removeBtns = Array.from(composerRoot.querySelectorAll('button, [role="button"]'))
      .filter(b => isShown(b) && /remove|delete|discard/.test(labelOf(b))).length;
    uploading = !!Array.from(composerRoot.querySelectorAll('[role="progressbar"], [aria-busy="true"], ' +
      '[class*="animate-spin"], [aria-label*="Uploading" i], [data-state="uploading"]')).find(isShown);
    if (fileNames.length) {
      const hay = (composerRoot.innerText || '') + ' ' + Array.from(composerRoot.querySelectorAll('[aria-label], [title], img[alt]'))
        .map(e => (e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || '') + ' ' + (e.getAttribute('alt') || '')).join(' ');
      nameHits = fileNames.filter(n => hay.includes(n)).length;
    }
  }
  out.attachCount = Math.max(attachImgs, removeBtns, nameHits);
  out.uploading = uploading;

  // Our newest sent message: user markers first, then a text search (newest match wins).
  let anchor = null, anchorVia = '';
  if (keys.length) {
    const userEls = Array.from(document.querySelectorAll(USER_SEL)).filter(el => !inComposer(el));
    for (const k of keys) {
      for (let i = userEls.length - 1; i >= 0 && !anchor; i--) {
        if (norm(userEls[i].textContent).includes(k)) { anchor = userEls[i]; anchorVia = 'marker'; }
      }
      if (anchor) break;
    }
    if (!anchor) {
      const root = document.querySelector('main') || document.body;
      for (const k of keys) {
        const lit = "'" + k + "'";
        try {
          const xp = ".//*[contains(normalize-space(.), " + lit + ") and not(ancestor-or-self::form) and " +
                     "not(*[contains(normalize-space(.), " + lit + ")])]";
          const res = document.evaluate(xp, root, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
          for (let i = res.snapshotLength - 1; i >= 0; i--) {
            const el = res.snapshotItem(i);
            if (!inComposer(el) && !/^(SCRIPT|STYLE|TITLE|TEMPLATE)$/.test(el.tagName)) { anchor = el; anchorVia = 'text'; break; }
          }
        } catch (e) {}
        if (anchor) break;
      }
    }
  }
  out.anchorFound = !!anchor;
  out.anchorVia = anchorVia;
  // The whole user turn (bubble + its attachments + Edit/Copy buttons) when the layout marks it.
  if (anchor) {
    const unit = anchor.closest('[data-content-search-unit-key$=":user"], [data-chatgpt-search-unit-key$=":user"], ' +
                                '[data-message-author-role="user"], [data-turn="user"]');
    if (unit && !inComposer(unit)) anchor = unit;
  }

  // Reply text = everything after our message up to the composer.
  let reply = '';
  if (anchor) {
    try {
      const range = document.createRange();
      range.setStartAfter(anchor);
      const mainEl = document.querySelector('main');
      if (composerRoot && after(anchor, composerRoot)) range.setEndBefore(composerRoot);
      else if (mainEl && mainEl.contains(anchor)) range.setEnd(mainEl, mainEl.childNodes.length);
      else { const p = anchor.parentElement || anchor; range.setEnd(p, p.childNodes.length); }
      reply = range.toString();
    } catch (e) { reply = ''; }
  } else {
    const units = Array.from(document.querySelectorAll(ASSIST_SEL)).filter(el => !inComposer(el));
    if (units.length) reply = units[units.length - 1].textContent || '';
  }
  reply = norm(reply);
  out.replyText = reply.length > 4000 ? reply.slice(-4000) : reply;

  const BUSY_SEL = '[data-testid="image-gen-loading-state-dots"], [data-testid*="loading" i], [data-test-id*="loading" i], ' +
    '[aria-busy="true"], [class*="animate-pulse"], [class*="shimmer"], [class*="animate-spin"], [role="progressbar"]';
  let domBusy = false;
  for (const el of document.querySelectorAll(BUSY_SEL)) {
    if (inComposer(el) || el.closest('nav, aside, header, [role="dialog"]')) continue;
    if (anchor && !after(anchor, el)) continue;
    if (!isShown(el)) continue;
    domBusy = true; break;
  }
  out.domBusy = domBusy;
  out.multigen = !!Array.from(document.querySelectorAll('[data-testid*="multigen" i], [data-testid*="paragen" i]'))
    .find(el => isShown(el) && (!anchor || after(anchor, el)));

  out.alerts = Array.from(document.querySelectorAll('[role="alert"], [role="alertdialog"], [data-sonner-toast], [data-testid*="toast" i]'))
    .filter(isShown).map(e => norm(e.innerText || e.textContent)).filter(Boolean).join('\n').slice(0, 3000);
  const dialogs = Array.from(document.querySelectorAll('[role="dialog"]')).filter(isShown);
  out.dialogOpen = dialogs.length > 0;
  out.dialogs = dialogs.map(e => norm(e.innerText || e.textContent)).filter(Boolean).join('\n').slice(0, 3000);

  // Image candidates: after our message, outside composer/nav/dialogs/user bubbles, grouped by file id.
  const ASSIST_MARK = ASSIST_SEL + ', [data-message-author-role="tool"]';
  const GEN_MARK = '[class*="imagegen" i], [id*="imagegen" i], [data-testid*="image-gen" i], [data-testid*="imagegen" i], [id^="image-"]';
  const groups = new Map();
  const allKeys = new Set();
  let order = 0;
  for (const img of Array.from(document.images)) {
    const src = img.currentSrc || img.src || '';
    if (!src || src.startsWith('data:image/svg')) continue;
    if (inComposer(img)) continue;
    const k = keyOf(src);
    allKeys.add(k);
    if (preKeys.has(k)) continue;
    if (img.closest('nav, aside, header, [role="dialog"], [role="menu"], [role="listbox"], [role="tooltip"]')) continue;
    const alt = img.getAttribute('alt') || '';
    if (/upload|attach|user image|your image/i.test(alt)) continue;
    const low = src.toLowerCase();
    if (!low.includes('estuary') && /avatar|favicon|emoji|gravatar|\/logo/.test(low)) continue;
    if (anchor && (anchor.contains(img) || !after(anchor, img))) continue;
    if (img.closest(USER_SEL)) continue;
    const r = img.getBoundingClientRect();
    if (r.width < 120 || r.height < 120) continue;
    const nw = img.naturalWidth || 0, nh = img.naturalHeight || 0;
    const loaded = !!(img.complete && nw > 0 && nh > 0);
    if (loaded && Math.min(nw, nh) < 512) continue;
    if (!loaded && img.loading === 'lazy') { try { img.loading = 'eager'; } catch (e) {} }
    let blurred = false, faded = false;
    for (let el = img, d = 0; el && el !== document.body && d < 7; el = el.parentElement, d++) {
      const cs = getComputedStyle(el);
      if ((cs.filter || '').includes('blur')) blurred = true;
      if (parseFloat(cs.opacity || '1') < 0.6 || cs.visibility === 'hidden' || cs.display === 'none') faded = true;
    }
    let score = 0;
    if (/^generated image/i.test(alt)) score += 4; else if (/generat|creat|image/i.test(alt)) score += 1;
    if (low.includes('estuary') || low.includes('oaiusercontent')) score += 1;
    if (img.closest(ASSIST_MARK)) score += 3;
    if (img.closest(GEN_MARK)) score += 2;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push({ src, alt: alt.slice(0, 140), nw, nh, w: Math.round(r.width), h: Math.round(r.height),
                         loaded, blurred, faded, score, order: order++ });
  }
  out.imageKeys = Array.from(allKeys);
  const cands = [];
  for (const [k, layers] of groups) {
    const sharp = layers.filter(l => l.loaded && !l.blurred && !l.faded && Math.min(l.nw, l.nh) >= 512);
    const rep = sharp.find(l => /^generated image/i.test(l.alt)) || sharp[sharp.length - 1] || layers[layers.length - 1];
    cands.push({ key: k, src: rep.src, alt: rep.alt, nw: rep.nw, nh: rep.nh, w: rep.w, h: rep.h, loaded: rep.loaded,
                 blurred: rep.blurred, faded: rep.faded, ready: sharp.length > 0,
                 score: Math.max.apply(null, layers.map(l => l.score)), order: rep.order, layers: layers.length,
                 srcs: Array.from(new Set(layers.map(l => l.src))).slice(0, 4) });
  }
  cands.sort((a, b) => a.order - b.order);
  out.candidates = cands;
  return out;
}"""

JS_MARK_EDITOR = "() => {" + JS_PRELUDE + r"""
  document.querySelectorAll('[data-wogali-editor]').forEach(e => e.removeAttribute('data-wogali-editor'));
  const ed = findEditor();
  if (!ed) return false;
  ed.setAttribute('data-wogali-editor', '1');
  return true;
}"""

JS_MARK_SEND = "() => {" + JS_PRELUDE + r"""
  document.querySelectorAll('[data-wogali-send]').forEach(e => e.removeAttribute('data-wogali-send'));
  const btn = findSends(composerRootOf(findEditor())).find(b => !b.disabled && b.getAttribute('aria-disabled') !== 'true');
  if (!btn) return false;
  btn.setAttribute('data-wogali-send', '1');
  return true;
}"""

JS_EXEC_INSERT = "(text) => {" + JS_PRELUDE + r"""
  const ed = document.querySelector('[data-wogali-editor="1"]') || findEditor();
  if (!ed) return false;
  ed.focus();
  if (ed.tagName === 'TEXTAREA') {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(ed, text);
    ed.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }
  document.execCommand('selectAll', false);
  document.execCommand('insertText', false, text);
  return true;
}"""

JS_REMOVE_ONE_ATTACHMENT = "() => {" + JS_PRELUDE + r"""
  const root = composerRootOf(findEditor());
  if (!root) return false;
  const btn = Array.from(root.querySelectorAll('button, [role="button"]')).filter(isShown).find(b => {
    const info = labelOf(b);
    if (!/remove|delete|discard/.test(info)) return false;
    if (/(remove|delete|discard) (file|attachment|image|upload|photo)/.test(info)) return true;
    for (let el = b.parentElement, d = 0; el && el !== root && d < 4; el = el.parentElement, d++) {
      if (el.querySelector('img')) return true;
    }
    return false;
  });
  if (!btn) return false;
  btn.click();
  return true;
}"""

JS_MARK_FILE_INPUT = "() => {" + JS_PRELUDE + r"""
  document.querySelectorAll('[data-wogali-file]').forEach(e => e.removeAttribute('data-wogali-file'));
  const root = composerRootOf(findEditor());
  const inputs = Array.from(document.querySelectorAll('input[type="file"]')).filter(i => !i.disabled);
  if (!inputs.length) return null;
  const score = (i) => {
    const acc = (i.getAttribute('accept') || '').toLowerCase();
    let s = 0;
    if (root && root.contains(i)) s += 2;
    if (!acc || acc.includes('image') || acc.includes('.png') || acc.includes('*')) s += 3;
    else s -= 5;
    if (i.multiple) s += 1;
    return s;
  };
  inputs.sort((a, b) => score(b) - score(a));
  inputs[0].setAttribute('data-wogali-file', '1');
  return { multiple: !!inputs[0].multiple, accept: inputs[0].getAttribute('accept') || '' };
}"""

JS_MARK_ATTACH_BUTTON = "() => {" + JS_PRELUDE + r"""
  document.querySelectorAll('[data-wogali-attach]').forEach(e => e.removeAttribute('data-wogali-attach'));
  const root = composerRootOf(findEditor());
  const scope = root ? Array.from(root.querySelectorAll('button, [role="button"]')) : [];
  const all = scope.concat(Array.from(document.querySelectorAll('button, [role="button"]')));
  const btn = all.filter(isShown).find(b => /composer-plus|attach|upload|add photos|add files|add attachment|photos & files/.test(labelOf(b)));
  if (!btn) return false;
  btn.setAttribute('data-wogali-attach', '1');
  return true;
}"""

JS_DROP_FILES = "async ({files, mode}) => {" + JS_PRELUDE + r"""
  const ed = findEditor();
  const target = mode === 'paste' ? ed : (composerRootOf(ed) || ed);
  if (!target) return false;
  const dt = new DataTransfer();
  for (const f of files) {
    const bin = atob(f.b64);
    const u8 = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    dt.items.add(new File([u8], f.name, { type: 'image/png' }));
  }
  if (mode === 'paste') {
    ed.focus();
    target.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt }));
  } else {
    for (const type of ['dragenter', 'dragover', 'drop']) {
      target.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt }));
    }
  }
  return true;
}"""

JS_FETCH_IMAGE = r"""async ({src}) => {
  const toB64 = (blob) => new Promise((resolve) => {
    const fr = new FileReader();
    fr.onloadend = () => { const s = String(fr.result || ''); const i = s.indexOf(','); resolve(i >= 0 ? s.slice(i + 1) : null); };
    fr.onerror = () => resolve(null);
    fr.readAsDataURL(blob);
  });
  let lastErr = 'fetch failed';
  for (const mode of ['force-cache', 'default', 'reload']) {
    try {
      const resp = await fetch(src, { credentials: 'include', cache: mode });
      if (!resp.ok) { lastErr = 'HTTP ' + resp.status; if (resp.status === 403 || resp.status === 404) break; continue; }
      const blob = await resp.blob();
      if (blob.size < 20000) { lastErr = 'too small: ' + blob.size; continue; }
      const b64 = await toB64(blob);
      if (b64) return { b64, type: blob.type || '', size: blob.size };
    } catch (e) { lastErr = String(e); }
  }
  return { error: lastErr };
}"""

JS_MARK_TARGET = "(key) => {" + JS_PRELUDE + r"""
  document.querySelectorAll('[data-wogali-target]').forEach(e => e.removeAttribute('data-wogali-target'));
  const imgs = Array.from(document.images).filter(i => keyOf(i.currentSrc || i.src || '') === key && !i.closest('[role="dialog"]'));
  const sharp = imgs.filter(i => i.complete && i.naturalWidth >= 512);
  const t = (sharp.length ? sharp : imgs).pop();
  if (!t) return false;
  t.setAttribute('data-wogali-target', '1');
  return true;
}"""

JS_CANVAS_PNG = r"""() => {
  const img = document.querySelector('img[data-wogali-target="1"]');
  if (!img || !img.complete || !img.naturalWidth) return null;
  try {
    const c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext('2d').drawImage(img, 0, 0);
    const d = c.toDataURL('image/png');
    return d.slice(d.indexOf(',') + 1);
  } catch (e) { return null; }
}"""

JS_MARK_NEAR_BUTTON = "(words) => {" + JS_PRELUDE + r"""
  document.querySelectorAll('[data-wogali-btn]').forEach(e => e.removeAttribute('data-wogali-btn'));
  const img = document.querySelector('img[data-wogali-target="1"]');
  if (!img) return false;
  for (let c = img.parentElement, d = 0; c && c !== document.body && d < 8; c = c.parentElement, d++) {
    if (c.querySelectorAll('img').length > 4) break;
    const hit = Array.from(c.querySelectorAll('button, a, [role="button"]')).filter(isShown).find(b => {
      const t = labelOf(b) + ' ' + norm(b.innerText || '').toLowerCase();
      return words.some(w => t.includes(w)) || (words.includes('download') && b.hasAttribute('download'));
    });
    if (hit) { hit.setAttribute('data-wogali-btn', '1'); return true; }
  }
  return false;
}"""

JS_MARK_DIALOG_BUTTON = "(words) => {" + JS_PRELUDE + r"""
  document.querySelectorAll('[data-wogali-btn]').forEach(e => e.removeAttribute('data-wogali-btn'));
  const dlg = Array.from(document.querySelectorAll('[role="dialog"], [role="menu"]')).filter(isShown).pop();
  if (!dlg) return false;
  const hit = Array.from(dlg.querySelectorAll('button, a, [role="button"], [role="menuitem"]')).filter(isShown).find(b => {
    const t = labelOf(b) + ' ' + norm(b.innerText || '').toLowerCase();
    return words.some(w => t.includes(w)) || b.hasAttribute('download');
  });
  if (!hit) return false;
  hit.setAttribute('data-wogali-btn', '1');
  return true;
}"""

JS_PICK_MULTIGEN = r"""() => {
  const mg = Array.from(document.querySelectorAll('[data-testid*="multigen" i], [data-testid*="paragen" i]')).pop();
  if (!mg) return false;
  const btns = Array.from(mg.querySelectorAll('button'));
  const b = btns.find(x => /image\s*1|first|prefer/i.test((x.innerText || '') + ' ' + (x.getAttribute('aria-label') || ''))) || btns[0];
  if (!b) return false;
  b.click();
  return true;
}"""


# =============================================================================
# Browser / tab helpers
# =============================================================================
class RunState:
    browser_gone = False


RUN = RunState()

_CONV_RE = re.compile(r"/c/([0-9A-Za-z][0-9A-Za-z-]{15,})")


def conv_id_of(url: str) -> Optional[str]:
    """Final ChatGPT conversation id from /c/<id> (temporary ids such as 'WEB:...' are ignored)."""
    try:
        m = _CONV_RE.search(urlparse(url or "").path or "")
    except Exception:
        return None
    return m.group(1) if m else None


def is_chatgpt_url(url: str, host: str) -> bool:
    try:
        netloc = urlparse(url or "").netloc.lower()
    except Exception:
        return False
    host = (host or "").lower()
    return bool(netloc) and (netloc == host or netloc.endswith("." + host) or netloc.replace("www.", "") == host.replace("www.", ""))


async def safe_eval(page: Page, js: str, arg=None, timeout: float = 20.0):
    """page.evaluate that never raises and never hangs (a frozen renderer cannot stall the batch)."""
    try:
        return await asyncio.wait_for(page.evaluate(js, arg), timeout)
    except Exception:
        return None


@dataclass
class EpisodeCtx:
    md_path: Path
    images_dir: Path
    ep_slug: str
    queue: List[Dict]
    ui_lock: asyncio.Lock
    cooldown: Cooldown
    timeout_sec: int
    save_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    seen_hashes: Dict[str, str] = field(default_factory=dict)  # SHA-256 -> saved file name
    dhashes: Dict[str, Optional[int]] = field(default_factory=dict)
    no_ref_items: List[str] = field(default_factory=list)


class TabSlot:
    """One ChatGPT tab. Replaces itself when closed/crashed and keeps track of its own chat."""

    def __init__(self, name: str, context, page: Page, cfg: Dict) -> None:
        self.name = name
        self.context = context
        self.page = page
        self.cfg = cfg
        self.host = urlparse(cfg["chatgpt_url"]).netloc
        self.conv_id: Optional[str] = None
        self.last_key: Optional[str] = None
        self.crashed = False
        self.last_front = 0.0
        self.upload_strategy: Optional[str] = None
        self._watch(page)

    def _watch(self, page: Page) -> None:
        def _on_crash(*_args, _page=page) -> None:
            if self.page is _page:
                self.crashed = True

        try:
            page.on("crash", _on_crash)
        except Exception:
            pass

    def alive(self) -> bool:
        try:
            return (not RUN.browser_gone) and self.page is not None and not self.page.is_closed() and not self.crashed
        except Exception:
            return False

    async def front(self) -> None:
        try:
            await asyncio.wait_for(self.page.bring_to_front(), 10)
        except Exception:
            pass
        self.last_front = time.monotonic()

    async def scan(self, keys=None, pre_keys=None, file_names=None, timeout: float = 20.0) -> Optional[Dict]:
        if not self.alive():
            return None
        args = {"keys": list(keys or []), "preKeys": list(pre_keys or []), "fileNames": list(file_names or [])}
        return await safe_eval(self.page, JS_SCAN, args, timeout)

    async def _new_page(self) -> None:
        self.page = await self.context.new_page()
        self.crashed = False
        self._watch(self.page)
        self.conv_id = None
        self.last_key = None

    async def wait_for_composer(self, patience: Optional[float] = None) -> bool:
        """Waits until the composer is usable. Login / Cloudflare pauses wait for you instead of failing."""
        patience = float(self.cfg.get("composer_wait_sec", 900)) if patience is None else float(patience)
        start = time.monotonic()
        next_hint = 20.0
        while True:
            if not self.alive():
                return False
            st = await self.scan(timeout=15)
            if st and st.get("hasEditor") and not st.get("challenge") and not st.get("loggedOut"):
                return True
            waited = time.monotonic() - start
            if waited >= patience:
                return False
            if waited >= next_hint:
                if st and st.get("challenge"):
                    reason = "Cloudflare 'Verify you are human' check"
                elif st and st.get("loggedOut"):
                    reason = "ChatGPT is logged out"
                else:
                    reason = "ChatGPT composer not visible yet"
                log(f"  [{self.name}] ⏸️ {reason} — Brave mein {self.name.split()[0]} check karo; script apne aap continue karega...")
                next_hint = waited + 60.0
            await asyncio.sleep(2.0)

    async def open_fresh_chat(self, why: str = "") -> bool:
        url = self.cfg["chatgpt_url"]
        for attempt in (1, 2, 3):
            if RUN.browser_gone:
                return False
            try:
                if not self.alive():
                    await self._new_page()
                await self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as exc:
                log(f"  [{self.name}] ⚠️ Fresh-chat navigation issue ({short_err(exc)}); retrying...")
                await asyncio.sleep(2.0 * attempt)
                continue
            if await self.wait_for_composer():
                self.conv_id = None
                self.last_key = None
                if why:
                    log(f"  [{self.name}] 🆕 Fresh chat ready ({why}).")
                return True
        log(f"  [{self.name}] ❌ Could not open a fresh ChatGPT chat.")
        return False

    async def recover(self, how: str = "reload") -> bool:
        """Closed/crashed -> new tab + fresh chat. Stuck -> reload the same chat, else fresh chat."""
        if RUN.browser_gone:
            return False
        try:
            if not self.alive():
                log(f"  [{self.name}] ♻️ Tab was closed or crashed — opening a replacement tab with a fresh chat...")
                await self._new_page()
                return await self.open_fresh_chat()
            if how == "reload" and conv_id_of(self.page.url):
                try:
                    await self.page.reload(wait_until="domcontentloaded", timeout=60_000)
                    if await self.wait_for_composer(120):
                        log(f"  [{self.name}] 🔄 Reloaded the same chat.")
                        return True
                except Exception:
                    pass
            return await self.open_fresh_chat("tab recovery")
        except Exception as exc:
            log(f"  [{self.name}] ⚠️ Recovery problem: {short_err(exc)}")
            return False

    async def prepare_for_episode(self, keep_if_fresh: bool) -> bool:
        """Every episode starts in a fresh chat. A tab already on an empty new-chat page is reused as-is."""
        if keep_if_fresh and self.alive() and is_chatgpt_url(self.page.url, self.host) and not conv_id_of(self.page.url):
            if await self.wait_for_composer():
                self.conv_id = None
                self.last_key = None
                return True
        return await self.open_fresh_chat()

    def note_success(self, image_key: str) -> None:
        cid = conv_id_of(self.page.url) if self.alive() else None
        if cid and cid != self.conv_id:
            if self.conv_id is None:
                log(f"  [{self.name}] 🔒 Same-chat session: /c/{cid}")
            self.conv_id = cid
        self.last_key = image_key

    async def ensure_same_chat(self) -> None:
        """Follows ChatGPT's temporary -> final chat id; never crashes and never deep-links to /c/<id>."""
        if not self.alive():
            return
        url = self.page.url or ""
        if not is_chatgpt_url(url, self.host):
            log(f"  [{self.name}] 🔁 Tab is no longer on ChatGPT — opening a fresh chat...")
            await self.open_fresh_chat()
            return
        cur = conv_id_of(url)
        if not self.conv_id or cur == self.conv_id:
            return
        if cur is None:
            log(f"  [{self.name}] 🔁 Tab is back on a new-chat page — continuing in a new chat (references keep the face-lock).")
            self.conv_id = None
            self.last_key = None
            return
        if self.last_key:
            st = await self.scan(timeout=15)
            if st and self.last_key in (st.get("imageKeys") or []):
                self.conv_id = cur
                return
        log(f"  [{self.name}] 🔁 Tab switched to a different chat — opening a fresh chat (references keep the face-lock)...")
        await self.open_fresh_chat()


# =============================================================================
# Composer actions
# =============================================================================
async def wait_until_idle(slot: TabSlot, timeout: float) -> None:
    """Do not type while the previous reply in this tab is still streaming (its Stop button is visible)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end and slot.alive():
        st = await slot.scan(timeout=10)
        if not st or not st.get("stopVisible"):
            return
        await asyncio.sleep(1.0)


async def clear_composer(slot: TabSlot) -> None:
    page = slot.page
    st = await slot.scan(timeout=10) or {}
    if st.get("dialogOpen"):
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except Exception:
            pass
    for _ in range(6):
        if not await safe_eval(page, JS_REMOVE_ONE_ATTACHMENT, None, 10):
            break
        await asyncio.sleep(0.4)
    if st.get("editorText") and await safe_eval(page, JS_MARK_EDITOR, None, 10):
        try:
            await page.locator('[data-wogali-editor="1"]').first.focus(timeout=5000)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
        except Exception:
            pass


async def _attach_count(slot: TabSlot, names: List[str]) -> int:
    st = await slot.scan(file_names=names, timeout=10) or {}
    return int(st.get("attachCount") or 0)


async def _confirm_attached(slot: TabSlot, names: List[str], base: int, want: int, timeout: float) -> int:
    end = time.monotonic() + timeout
    best = base
    while time.monotonic() < end:
        await asyncio.sleep(0.4)
        best = max(best, await _attach_count(slot, names))
        if best >= want:
            break
    return best - base


async def _upload_via_file_input(slot: TabSlot, refs: List[Path]) -> bool:
    page = slot.page
    paths = [str(p) for p in refs]
    info = await safe_eval(page, JS_MARK_FILE_INPUT, None, 10)
    if not info:
        return False
    if info.get("multiple") or len(paths) == 1:
        await page.locator('input[data-wogali-file="1"]').first.set_input_files(paths, timeout=20_000)
    else:
        for one in paths:
            await page.locator('input[data-wogali-file="1"]').first.set_input_files(one, timeout=20_000)
            await asyncio.sleep(0.8)
            await safe_eval(page, JS_MARK_FILE_INPUT, None, 10)
    return True


async def _upload_via_attach_menu(slot: TabSlot, refs: List[Path]) -> bool:
    page = slot.page
    paths = [str(p) for p in refs]
    if not await safe_eval(page, JS_MARK_ATTACH_BUTTON, None, 10):
        return False
    try:
        async with page.expect_file_chooser(timeout=8000) as fc_info:
            await page.locator('[data-wogali-attach="1"]').first.click(timeout=5000)
            await asyncio.sleep(0.7)
            item = page.locator('[role="menuitem"], [role="menuitemradio"], [role="option"], [role="menu"] button').filter(
                has_text=re.compile(r"(add|upload|attach)[^\n]{0,24}(photo|file|image)|photos?\s*(?:&|and)\s*files", re.I)
            ).first
            if await item.count():
                await item.click(timeout=5000)
        chooser = await fc_info.value
        await chooser.set_files(paths if chooser.is_multiple() or len(paths) == 1 else paths[:1])
        return True
    except Exception:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return False


async def _upload_via_event(slot: TabSlot, refs: List[Path], mode: str) -> bool:
    try:
        files = [{"name": p.name, "b64": base64.b64encode(p.read_bytes()).decode("ascii")} for p in refs]
    except Exception:
        return False
    return bool(await safe_eval(slot.page, JS_DROP_FILES, {"files": files, "mode": mode}, 30))


async def upload_references(slot: TabSlot, refs: List[Path], ui_lock: asyncio.Lock) -> bool:
    """Attaches the reference PNGs: file input, +/attach menu, drop event, paste event.

    Each action takes the UI lock only for the action itself; waiting for the preview runs unlocked.
    The strategy that worked last time on this tab is tried first.
    """
    names = [p.name for p in refs]
    order = ["input", "menu", "drop", "paste"]
    if slot.upload_strategy in order:
        order.remove(slot.upload_strategy)
        order.insert(0, slot.upload_strategy)
    base = await _attach_count(slot, names)
    want = base + len(refs)
    for strategy in order:
        async with ui_lock:
            await slot.front()
            try:
                if strategy == "input":
                    acted = await _upload_via_file_input(slot, refs)
                elif strategy == "menu":
                    acted = await _upload_via_attach_menu(slot, refs)
                else:
                    acted = await _upload_via_event(slot, refs, strategy)
            except Exception:
                acted = False
        if acted and await _confirm_attached(slot, names, base, want, ATTACH_CONFIRM_SEC) >= 1:
            slot.upload_strategy = strategy
            return True
    return False


async def type_prompt(slot: TabSlot, text: str, key: str) -> bool:
    """Types the full prompt and checks the composer really contains it (insert_text -> fill -> execCommand)."""
    page = slot.page
    expected_len = len(norm_text(text))
    for attempt in range(3):
        if not await safe_eval(page, JS_MARK_EDITOR, None, 10):
            await asyncio.sleep(1.0)
            continue
        editor = page.locator('[data-wogali-editor="1"]').first
        try:
            await editor.focus(timeout=5000)
            try:
                await editor.click(timeout=4000)
            except Exception:
                pass
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            if attempt == 0:
                await page.keyboard.insert_text(text)
            elif attempt == 1:
                await editor.fill(text, timeout=15_000)
            else:
                await safe_eval(page, JS_EXEC_INSERT, text, 20)
        except Exception:
            continue
        await asyncio.sleep(0.5)
        st = await slot.scan(timeout=10) or {}
        typed = st.get("editorText") or ""
        if key in typed and len(typed) >= int(expected_len * 0.9):
            return True
    return False


async def press_enter(slot: TabSlot) -> bool:
    page = slot.page
    try:
        if await safe_eval(page, JS_MARK_EDITOR, None, 10):
            await page.locator('[data-wogali-editor="1"]').first.focus(timeout=5000)
        await page.keyboard.press("Enter")
        return True
    except Exception:
        return False


async def click_send(slot: TabSlot) -> bool:
    page = slot.page
    if await safe_eval(page, JS_MARK_SEND, None, 10):
        btn = page.locator('[data-wogali-send="1"]').first
        for force in (False, True):
            try:
                await btn.click(timeout=5000, force=force)
                return True
            except Exception:
                continue
    return await press_enter(slot)


async def wait_upload_ready(slot: TabSlot, timeout: float) -> bool:
    end = time.monotonic() + timeout
    await asyncio.sleep(0.8)
    while time.monotonic() < end and slot.alive():
        st = await slot.scan(timeout=10) or {}
        if not st.get("uploading") and (st.get("sendEnabled") or not st.get("sendVisible")):
            return True
        await asyncio.sleep(0.5)
    return False


async def wait_until_sent(slot: TabSlot, key: str, timeout: float) -> bool:
    """Sent = our text has left the composer (ChatGPT clears it once the message is accepted)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end and slot.alive():
        await asyncio.sleep(0.5)
        st = await slot.scan(timeout=10)
        if st is None:
            continue
        if key not in (st.get("editorText") or ""):
            return True
    return False


# =============================================================================
# Saving (fetch the image's own file; UI download only as a last resort)
# =============================================================================
def save_png_sync(raw: bytes, out_path: Path, seen_hashes: Dict[str, str], dhashes: Dict[str, Optional[int]], ref_names: Set[str]) -> Tuple[str, Dict]:
    """Runs in a worker thread. Returns (status, info): saved / dup / copy (= matches a reference) / invalid."""
    png = ensure_true_png_bytes(raw)
    if not png:
        return "invalid", {}
    sha = bytes_sha256(png)
    if sha in seen_hashes:
        name = seen_hashes[sha]
        return ("copy" if name in ref_names else "dup"), {"match": name}
    dh = dhash_bits(png)
    if dh is not None:
        for name, other in dhashes.items():
            if other is not None and hamming(dh, other) <= DHASH_DUP_MAX_BITS:
                return ("copy" if name in ref_names else "dup"), {"match": name}
    atomic_write_bytes(out_path, png)
    if not is_valid_png_file(out_path):
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        return "invalid", {}
    w, h = png_size(png)
    return "saved", {"sha": sha, "dhash": dh, "bytes": len(png), "w": w, "h": h}


async def fetch_image_bytes(slot: TabSlot, cand: Dict) -> Tuple[Optional[bytes], str]:
    page = slot.page
    for src in [cand["src"]] + [s for s in cand.get("srcs", []) if s != cand["src"]]:
        res = await safe_eval(page, JS_FETCH_IMAGE, {"src": src}, 90)
        if res and res.get("b64"):
            try:
                return base64.b64decode(res["b64"]), "in-page fetch"
            except Exception:
                pass
    src = cand["src"]
    if src.startswith("http"):
        try:
            resp = await page.context.request.get(src, timeout=45_000)
            if resp.ok:
                body = await resp.body()
                if len(body) >= MIN_IMAGE_BYTES:
                    return body, "browser request"
        except Exception:
            pass
    if await safe_eval(page, JS_MARK_TARGET, cand["key"], 10):
        b64 = await safe_eval(page, JS_CANVAS_PNG, None, 60)
        if b64:
            try:
                return base64.b64decode(b64), "canvas"
            except Exception:
                pass
    return None, ""


async def ui_download_fallback(slot: TabSlot, ctx: EpisodeCtx, cand: Dict, tmp_path: Path) -> Optional[bytes]:
    """Last resort: Download / Share -> Download / image viewer -> Download, captured with expect_download."""
    page = slot.page
    async with ctx.ui_lock:
        await slot.front()
        if not await safe_eval(page, JS_MARK_TARGET, cand["key"], 10):
            return None
        target = page.locator('img[data-wogali-target="1"]').first
        try:
            await target.scroll_into_view_if_needed(timeout=5000)
            await target.hover(timeout=5000)
            await asyncio.sleep(0.5)
        except Exception:
            pass
        plans = [("near", ["download", "save image"], None), ("near", ["share"], ["download", "save"]), ("image", None, ["download", "save"])]
        for kind, first_words, dialog_words in plans:
            opened = False
            try:
                if kind == "near":
                    if not await safe_eval(page, JS_MARK_NEAR_BUTTON, first_words, 10):
                        continue
                    first = page.locator('[data-wogali-btn="1"]').first
                else:
                    first = target
                if dialog_words is None:
                    async with page.expect_download(timeout=20_000) as dl_info:
                        await first.click(timeout=5000)
                else:
                    await first.click(timeout=5000)
                    opened = True
                    await asyncio.sleep(1.0)
                    if not await safe_eval(page, JS_MARK_DIALOG_BUTTON, dialog_words, 10):
                        continue
                    async with page.expect_download(timeout=20_000) as dl_info:
                        await page.locator('[data-wogali-btn="1"]').first.click(timeout=5000)
                download = await dl_info.value
                await download.save_as(str(tmp_path))
                data = tmp_path.read_bytes()
                tmp_path.unlink(missing_ok=True)
                return data
            except Exception:
                continue
            finally:
                if opened:
                    for _ in range(2):
                        try:
                            await page.keyboard.press("Escape")
                            await asyncio.sleep(0.2)
                        except Exception:
                            pass
    return None


async def fetch_and_save(slot: TabSlot, ctx: EpisodeCtx, item: Dict, cand: Dict, ref_names: Set[str], started: float) -> Tuple[str, Dict]:
    out_path: Path = item["output_path"]
    raw, via = await fetch_image_bytes(slot, cand)
    if raw is None:
        raw = await ui_download_fallback(slot, ctx, cand, out_path.with_name(out_path.name + ".dl"))
        via = "Download button"
    if raw is None:
        return "fetch_error", {}
    async with ctx.save_lock:
        status, info = await asyncio.to_thread(save_png_sync, raw, out_path, dict(ctx.seen_hashes), dict(ctx.dhashes), ref_names)
        if status == "saved":
            ctx.seen_hashes[info["sha"]] = out_path.name
            ctx.dhashes[out_path.name] = info["dhash"]
    if status == "saved":
        mb = info["bytes"] / (1024 * 1024)
        log(
            f"  [{slot.name}] ✅ SAVED ORIGINAL FULL-SIZE PNG -> {out_path.name} "
            f"({mb:.2f} MB, {info['w']}x{info['h']}, {via}, {fmt_secs(time.monotonic() - started)})"
        )
    return status, info


def pick_best(cands: List[Dict]) -> Optional[Dict]:
    ready = [c for c in cands if c.get("ready")]
    if not ready:
        return None
    top = max(c.get("score", 0) for c in ready)
    return [c for c in ready if c.get("score", 0) == top][-1]


async def wait_and_save(slot: TabSlot, ctx: EpisodeCtx, item: Dict, keys: List[str], pre_keys: List[str], sent_at: float, ref_names: Set[str]) -> str:
    """Polls this tab (no UI lock) until the new image is final, then saves it. Rejected candidates are skipped."""
    code = item["img_code"]
    deadline = sent_at + ctx.timeout_sec
    stable_key: Optional[str] = None
    stable_dims: Tuple[int, int] = (0, 0)
    stable_n = 0
    stable_since = 0.0
    reply_prev: Optional[str] = None
    reply_since = time.monotonic()
    rejected: Set[str] = set()
    fetch_failures: Dict[str, int] = {}
    scan_failures = 0
    multigen_clicked = False
    copy_seen_at: Optional[float] = None
    copy_of = ""

    await asyncio.sleep(FIRST_POLL_DELAY_SEC)
    while time.monotonic() < deadline:
        if not slot.alive():
            return BROKEN
        st = await slot.scan(keys=keys, pre_keys=pre_keys, timeout=25)
        now = time.monotonic()
        if st is None:
            scan_failures += 1
            if scan_failures >= 6:
                log(f"  [{slot.name}] ⚠️ Tab stopped responding while waiting for {code}.")
                return BROKEN
            await asyncio.sleep(POLL_SEC)
            continue
        scan_failures = 0
        if st.get("challenge") or st.get("loggedOut"):
            log(f"  [{slot.name}] ⏸️ ChatGPT needs attention (login / Cloudflare) while generating {code}.")
            return BROKEN

        reply = st.get("replyText") or ""
        if reply != reply_prev:
            reply_prev = reply
            reply_since = now
        stop = bool(st.get("stopVisible"))
        dom_busy = bool(st.get("domBusy"))
        text_busy = bool(BUSY_TEXT_RE.search(reply[-300:]))
        cands = [c for c in (st.get("candidates") or []) if c["key"] not in rejected]
        pending = [c for c in cands if not c.get("ready")]

        if st.get("multigen") and not multigen_clicked and not stop:
            multigen_clicked = True
            if await safe_eval(slot.page, JS_PICK_MULTIGEN, None, 10):
                log(f"  [{slot.name}] 🖼️ ChatGPT offered two images — picked Image 1.")
                await asyncio.sleep(2.0)
                continue

        best = pick_best(cands)
        if best:
            dims = (int(best.get("nw") or 0), int(best.get("nh") or 0))
            if best["key"] == stable_key and dims == stable_dims:
                stable_n += 1
            else:
                stable_key, stable_dims, stable_n, stable_since = best["key"], dims, 1, now
            busy = stop or dom_busy or text_busy
            if stable_n >= 2 and (not busy or now - stable_since >= SETTLE_FALLBACK_SEC):
                status, info = await fetch_and_save(slot, ctx, item, best, ref_names, sent_at)
                if status == "saved":
                    slot.note_success(best["key"])
                    return OK
                if status == "fetch_error":
                    fetch_failures[best["key"]] = fetch_failures.get(best["key"], 0) + 1
                    if fetch_failures[best["key"]] >= 3:
                        rejected.add(best["key"])
                        log(f"  [{slot.name}] ⚠️ Could not download the image for {code} (3 tries).")
                elif status == "copy" and best.get("score", 0) >= 3:
                    log(f"  [{slot.name}] ⚠️ ChatGPT returned a copy of reference {info.get('match')} for {code} — retrying.")
                    return FAILED
                else:
                    rejected.add(best["key"])
                    if status == "copy":
                        copy_seen_at, copy_of = now, str(info.get("match") or "")
                    if status in ("dup", "copy"):
                        log(f"  [{slot.name}] ↪️ Ignored an image identical to {info.get('match')} (uploaded reference / old image); still waiting for {code}...")
                stable_key = None
                stable_n = 0
        else:
            stable_key = None
            stable_n = 0

        if not best and not stop:
            notice = "\n".join(x for x in (st.get("alerts") or "", reply[-1500:]) if x)
            dialog_text = st.get("dialogs") or ""
            if RATE_LIMIT_RE.search(notice) or RATE_LIMIT_DIALOG_RE.search(dialog_text):
                ctx.cooldown.mark("\n".join(x for x in (notice, dialog_text) if x), slot.name)
                if st.get("dialogOpen"):
                    try:
                        await slot.page.keyboard.press("Escape")
                    except Exception:
                        pass
                return RATE_LIMITED
            if TOO_LONG_RE.search(notice):
                log(f"  [{slot.name}] ⚠️ ChatGPT says this chat is too long — switching {slot.name.split()[0]} to a fresh chat.")
                return NEEDS_FRESH_CHAT
            quiet = now - reply_since
            if copy_seen_at and not dom_busy and not pending and now - max(copy_seen_at, reply_since) >= 10:
                log(f"  [{slot.name}] ⚠️ ChatGPT returned a copy of reference {copy_of} for {code} — retrying.")
                return FAILED
            if not dom_busy and quiet >= 8 and ERROR_RE.search(notice):
                log(f"  [{slot.name}] ⚠️ ChatGPT error on {code}: \"{snippet(reply or st.get('alerts', ''))}\" — will retry.")
                return FAILED
            if not dom_busy and not pending and quiet >= 8 and REFUSAL_RE.search(reply):
                log(f"  [{slot.name}] ⚠️ ChatGPT refused {code}: \"{snippet(reply, 200)}\" — will retry.")
                return FAILED
            if not dom_busy and not pending and len(reply) >= 20 and now - sent_at >= 45 and quiet >= (60 if text_busy else 20):
                log(f"  [{slot.name}] ⚠️ ChatGPT replied with text instead of an image for {code}: \"{snippet(reply)}\" — will retry.")
                return FAILED

        # A background tab may not render/lazy-load the finished image until it is visible: show it briefly.
        if st.get("hidden") and now - sent_at >= 40 and now - slot.last_front >= NUDGE_EVERY_SEC and (pending or not stop):
            async with ctx.ui_lock:
                await slot.front()
                await asyncio.sleep(1.2)
        await asyncio.sleep(POLL_SEC)

    log(f"  [{slot.name}] ⚠️ Timeout ({fmt_secs(ctx.timeout_sec)}) waiting for {code} to finish generating.")
    return FAILED


# =============================================================================
# One image = one attempt (compose under the UI lock, everything else in parallel)
# =============================================================================
async def generate_one(slot: TabSlot, item: Dict, ctx: EpisodeCtx, allow_no_ref: bool) -> str:
    out_path: Path = item["output_path"]
    code = item["img_code"]
    if is_valid_png_file(out_path):
        return OK
    await ctx.cooldown.wait(slot.name)
    if not slot.alive() and not await slot.recover():
        return BROKEN
    await slot.ensure_same_chat()
    if not await slot.wait_for_composer():
        return BROKEN
    await wait_until_idle(slot, 60)

    verbatim = re.sub(r"\s+", " ", item["prompt"]).strip()
    refs = select_reference_images_for_item(ctx.queue, item["index"])
    ref_names = {p.name for p in refs}

    # UI lock only around the short UI actions; the upload preview wait runs unlocked.
    async with ctx.ui_lock:
        await slot.front()
        base = await slot.scan(timeout=15) or {}
        pre_keys = list(base.get("imageKeys") or [])
        await clear_composer(slot)
    use_refs = False
    if refs:
        use_refs = await upload_references(slot, refs, ctx.ui_lock)
        if not use_refs:
            if not allow_no_ref:
                async with ctx.ui_lock:
                    await clear_composer(slot)
                log(f"  [{slot.name}] ⚠️ Reference upload failed for {code} — will retry (face-lock stays strict).")
                return FAILED
            log(f"  [{slot.name}] ⚠️ Reference upload failed again for {code} — last round, sending WITHOUT references.")
    prefix = REF_INSTRUCTION if use_refs else ANCHOR_PREFIX
    full_prompt = prefix + verbatim
    keys = anchor_keys(prefix, verbatim)
    async with ctx.ui_lock:
        await slot.front()
        typed = await type_prompt(slot, full_prompt, keys[0])
    if not typed:
        log(f"  [{slot.name}] ⚠️ Could not type the prompt for {code} into the ChatGPT composer.")
        return BROKEN

    if use_refs and not await wait_upload_ready(slot, UPLOAD_READY_SEC):
        log(f"  [{slot.name}] ⚠️ Reference upload still busy after {fmt_secs(UPLOAD_READY_SEC)} for {code}; trying to send anyway.")

    async with ctx.ui_lock:
        await slot.front()
        await click_send(slot)
    sent = await wait_until_sent(slot, keys[0], SEND_CONFIRM_SEC)
    if not sent:
        async with ctx.ui_lock:
            await slot.front()
            await click_send(slot)  # still unsent = our text is still in the composer, so this cannot double-send
        sent = await wait_until_sent(slot, keys[0], 12)
    if not sent:
        log(f"  [{slot.name}] ⚠️ ChatGPT did not accept the prompt for {code}; recovering the tab...")
        return BROKEN

    sent_at = time.monotonic()
    ref_note = f"  📎 refs: {', '.join(sorted(ref_names))}" if use_refs else ""
    log(f"  [{slot.name}] 🚀 Generating {code} -> {out_path.name}{ref_note}")
    if refs and not use_refs:
        ctx.no_ref_items.append(out_path.name)
    return await wait_and_save(slot, ctx, item, keys, pre_keys, sent_at, ref_names if use_refs else set())


async def run_item(slot: TabSlot, item: Dict, ctx: EpisodeCtx, attempts: int, allow_no_ref: bool) -> bool:
    """Rate-limit waits do not use up attempts; broken tabs are recovered between attempts."""
    tries = 0
    rate_waits = 0
    while tries < attempts and not RUN.browser_gone:
        if is_valid_png_file(item["output_path"]):
            return True
        try:
            res = await generate_one(slot, item, ctx, allow_no_ref)
        except Exception as exc:
            log(f"  [{slot.name}] ⚠️ {item['img_code']}: {short_err(exc)}")
            res = BROKEN if not slot.alive() else FAILED
        if res == OK:
            return True
        if res == RATE_LIMITED:
            rate_waits += 1
            if rate_waits > MAX_RATE_LIMIT_WAITS_PER_ITEM:
                return False
            continue
        tries += 1
        if res == BROKEN:
            await slot.recover("reload")
        elif res == NEEDS_FRESH_CHAT:
            await slot.open_fresh_chat("previous chat too long")
        else:
            await asyncio.sleep(2.0)
    return is_valid_png_file(item["output_path"])


async def tab_worker(slot: TabSlot, items: List[Dict], ctx: EpisodeCtx, attempts: int, allow_no_ref: bool) -> None:
    for item in items:
        if RUN.browser_gone:
            return
        if is_valid_png_file(item["output_path"]):
            log(f"  [{slot.name}] [SKIP] {item['output_path'].name} already saved.")
            continue
        try:
            await run_item(slot, item, ctx, attempts, allow_no_ref)
        except Exception as exc:
            log(f"  [{slot.name}] ⚠️ Unexpected error on {item['img_code']}: {short_err(exc)} — continuing.")
        await asyncio.sleep(0.8)


# =============================================================================
# Episode
# =============================================================================
def _hash_existing_sync(paths: List[Path]) -> List[Tuple[str, str, Optional[int]]]:
    out = []
    for p in paths:
        if is_valid_png_file(p):
            out.append((p.name, file_sha256(p), dhash_bits(p)))
    return out


async def process_one_story_in_dual_tabs(
    slot1: TabSlot,
    slot2: TabSlot,
    base_dir: Path,
    md_path: Path,
    cfg: Dict,
    ui_lock: asyncio.Lock,
    cooldown: Cooldown,
    is_first_episode: bool,
) -> Dict:
    started = time.monotonic()
    images_dir, ep_slug, queue = build_story_queue(base_dir, md_path, include_thumb=True)
    topic_name = extract_story_topic_name(md_path)
    ctx = EpisodeCtx(
        md_path=md_path,
        images_dir=images_dir,
        ep_slug=ep_slug,
        queue=queue,
        ui_lock=ui_lock,
        cooldown=cooldown,
        timeout_sec=int(cfg.get("generation_timeout_sec", 300)),
    )
    for name, sha, dh in await asyncio.to_thread(_hash_existing_sync, [it["output_path"] for it in queue]):
        ctx.seen_hashes[sha] = name
        ctx.dhashes[name] = dh

    log("\n" + "=" * 100)
    log(f"🎬 STARTING STORY: {md_path.name}  ({len(queue)} Images)")
    log(f"   Topic Name    : {topic_name}")
    log(f"   Save Folder   : {images_dir}")
    log(f"   Naming Format : IMG_001_{ep_slug}.png .. {queue[-1]['output_path'].name}")
    log("=" * 100)

    summary = {"story": md_path.name, "slug": ep_slug, "total": len(queue), "saved": 0, "missing": [], "no_refs": []}
    pending = [it for it in queue if not is_valid_png_file(it["output_path"])]
    if not pending:
        log(f"✅ All {len(queue)} images for {md_path.name} are already saved! Moving to next story...")
        summary["saved"] = len(queue)
        return summary
    log(f"   Already saved : {len(queue) - len(pending)}/{len(queue)} (resuming from the PNG files on disk)")

    log(f"\n🆕 Opening fresh ChatGPT chats on TAB-1 & TAB-2 for {md_path.name} (zero character bleed)...")
    ready1, ready2 = await asyncio.gather(slot1.prepare_for_episode(is_first_episode), slot2.prepare_for_episode(is_first_episode))
    if not (ready1 or ready2):
        raise RuntimeError("Neither ChatGPT tab became ready")

    # PHASE 1: IMG_001 master anchor first, on TAB-1
    anchor_item = next((it for it in queue if it["index"] == 1 and not is_valid_png_file(it["output_path"])), None)
    if anchor_item is not None:
        log(f"\n🎯 [PHASE 1 — MASTER ANCHOR] Generating {anchor_item['output_path'].name} first on TAB-1...")
        if not await run_item(slot1, anchor_item, ctx, ANCHOR_ATTEMPTS, allow_no_ref=False):
            log("  ⚠️ IMG_001 anchor failed after all attempts — continuing so the batch does not stall "
                "(later images use the nearest saved scene as reference; IMG_001 is retried in the retry rounds).")

    # PHASE 2: TAB-1 ODD + TAB-2 EVEN in parallel, each in its own continuous chat
    remaining = [it for it in queue if not is_valid_png_file(it["output_path"])]
    tab1_items = [it for it in remaining if it["index"] % 2 == 1]
    tab2_items = [it for it in remaining if it["index"] % 2 == 0]
    log(f"\n  [TAB-1 ODD  QUEUE] -> {[it['output_path'].name for it in tab1_items]}")
    log(f"  [TAB-2 EVEN QUEUE] -> {[it['output_path'].name for it in tab2_items]}\n")
    await asyncio.gather(
        tab_worker(slot1, tab1_items, ctx, attempts=1, allow_no_ref=False),
        tab_worker(slot2, tab2_items, ctx, attempts=1, allow_no_ref=False),
    )

    # 2 automatic retry rounds, still parallel. The last round may send without references if upload keeps failing.
    for retry_round in (1, 2):
        if RUN.browser_gone:
            break
        still_missing = [it for it in queue if not is_valid_png_file(it["output_path"])]
        if not still_missing:
            break
        log(f"\n🔄 [AUTO-RETRY ROUND {retry_round}/2] Recovering {len(still_missing)} image(s) for {md_path.name}: "
            f"{[it['output_path'].name for it in still_missing]}")
        for slot in (slot1, slot2):
            if not slot.alive():
                await slot.recover()
        await asyncio.gather(
            tab_worker(slot1, [it for it in still_missing if it["index"] % 2 == 1], ctx, 1, allow_no_ref=(retry_round == 2)),
            tab_worker(slot2, [it for it in still_missing if it["index"] % 2 == 0], ctx, 1, allow_no_ref=(retry_round == 2)),
        )

    missing = [it["output_path"].name for it in queue if not is_valid_png_file(it["output_path"])]
    summary.update(saved=len(queue) - len(missing), missing=missing, no_refs=list(ctx.no_ref_items))
    log("\n" + "=" * 100)
    log(f"✅ STORY COMPLETE [{md_path.name}]: {summary['saved']}/{len(queue)} Original PNGs saved in '{images_dir.name}' "
        f"({fmt_secs(time.monotonic() - started)})")
    if missing:
        log(f"   ⚠️ Missing ({len(missing)}): {missing} — run the same command again to resume only these.")
    if ctx.no_ref_items:
        log(f"   ⚠️ Generated WITHOUT reference upload (check faces; delete + rerun to regenerate): {ctx.no_ref_items}")
    log("=" * 100)
    return summary


# =============================================================================
# Brave: attach over CDP (never closed by this script) or start it detached
# =============================================================================
def cdp_endpoint_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def launch_brave_detached(brave_exe: str, port: int, profile_dir: Path, url: str) -> None:
    args = [
        brave_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--disable-blink-features=AutomationControlled",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    kwargs: Dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        # Detached: Ctrl+C in PowerShell can never reach (and close) Brave.
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)


async def connect_browser(p, cfg: Dict, profile_dir: Path, port: int, brave_exe: Optional[str]):
    """Returns (browser, context, attached_over_cdp)."""
    endpoint = f"http://127.0.0.1:{port}"

    async def _attach():
        browser = await p.chromium.connect_over_cdp(endpoint, timeout=30_000)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        return browser, context

    if await asyncio.to_thread(cdp_endpoint_alive, port):
        try:
            browser, context = await _attach()
            log(f"🔌 Attached to the running Brave on {endpoint} (it stays open after the script ends).")
            return browser, context, True
        except Exception as exc:
            log(f"⚠️ CDP attach failed: {short_err(exc)}")

    if brave_exe:
        log(f"🚀 Starting Brave with remote debugging on port {port} (profile: {profile_dir})...")
        try:
            launch_brave_detached(brave_exe, port, profile_dir, cfg["chatgpt_url"])
        except Exception as exc:
            log(f"⚠️ Could not start Brave: {short_err(exc)}")
        for _ in range(60):
            if await asyncio.to_thread(cdp_endpoint_alive, port):
                break
            await asyncio.sleep(0.5)
        if await asyncio.to_thread(cdp_endpoint_alive, port):
            try:
                browser, context = await _attach()
                log(f"🔌 Attached to Brave on {endpoint} (it stays open after the script ends).")
                return browser, context, True
            except Exception as exc:
                log(f"⚠️ CDP attach failed: {short_err(exc)}")
        else:
            log("⚠️ Brave did not open the debugging port. If Brave is already running with this profile but WITHOUT "
                f"--remote-debugging-port={port}, close those Brave windows and run the script again.")
    else:
        log("⚠️ Brave executable not found — set \"brave_executable_path\" in config.json.")

    try:
        kwargs = {
            "user_data_dir": str(profile_dir),
            "headless": False,
            "viewport": {"width": 1440, "height": 900},
            "accept_downloads": True,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if brave_exe:
            kwargs["executable_path"] = brave_exe
        context = await p.chromium.launch_persistent_context(**kwargs)
        log("⚠️ Using a Playwright-launched browser window (this one closes when the script ends).")
        return None, context, False
    except Exception as exc:
        log(f"❌ Could not start or attach to Brave: {short_err(exc, 300)}")
        return None, None, False


def _is_blank(url: str) -> bool:
    url = url or ""
    return url in ("", "about:blank") or url.startswith(("chrome://newtab", "chrome://new-tab-page", "brave://newtab", "edge://newtab"))


async def open_tab1(context, cfg: Dict) -> Page:
    host = urlparse(cfg["chatgpt_url"]).netloc
    pages = [pg for pg in context.pages if not pg.is_closed()]
    chat_pages = [pg for pg in pages if is_chatgpt_url(pg.url, host)]
    blank_pages = [pg for pg in pages if _is_blank(pg.url)]
    tab1 = chat_pages[0] if chat_pages else (blank_pages[0] if blank_pages else await context.new_page())
    if not is_chatgpt_url(tab1.url, host) or conv_id_of(tab1.url):
        try:
            await tab1.goto(cfg["chatgpt_url"], wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            log(f"⚠️ TAB-1 navigation issue ({short_err(exc)}) — you can open {cfg['chatgpt_url']} in it manually.")
    try:
        await tab1.bring_to_front()
    except Exception:
        pass
    return tab1


async def open_tab2(context, cfg: Dict, tab1: Page) -> Page:
    host = urlparse(cfg["chatgpt_url"]).netloc
    others = [pg for pg in context.pages if pg is not tab1 and not pg.is_closed() and is_chatgpt_url(pg.url, host)]
    tab2 = others[0] if others else await context.new_page()
    if not is_chatgpt_url(tab2.url, host) or conv_id_of(tab2.url):
        try:
            await tab2.goto(cfg["chatgpt_url"], wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            log(f"⚠️ TAB-2 navigation issue ({short_err(exc)}) — it will be retried automatically.")
    return tab2


# =============================================================================
# Main
# =============================================================================
async def run_agent_2() -> None:
    setup_console()
    prevent_windows_sleep(True)
    try:
        base_dir = Path.cwd()
        cfg = load_config("config.json")
        cli_story_args = [a for a in sys.argv[1:] if not a.startswith("--")]
        try:
            story_batch = await resolve_story_batch(base_dir, cli_story_args)
        except FileNotFoundError as exc:
            log(f"❌ {exc}")
            return

        brave_exe = resolve_brave_executable(cfg.get("brave_executable_path", ""))
        profile_dir = Path(cfg.get("brave_chatgpt_profile_dir", "./brave_profiles/chatgpt_profile")).resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        debug_port = int(cfg.get("remote_debugging_port", 9222))
        ui_lock = asyncio.Lock()
        cooldown = Cooldown()
        run_started = time.monotonic()

        log("\n" + "=" * 100)
        log(f"AGENT 2 {VERSION} (NEW-UI HARDENED DUAL-TAB + AUTO REFERENCE FACE-LOCK)")
        log(f"  Batch Queue ({len(story_batch)} stories): {[p.name for p in story_batch]}")
        log("=" * 100)

        async with async_playwright() as p:
            browser, context, attached = await connect_browser(p, cfg, profile_dir, debug_port, brave_exe)
            if context is None:
                return
            if browser is not None:
                browser.on("disconnected", lambda *_: setattr(RUN, "browser_gone", True))
            else:
                context.on("close", lambda *_: setattr(RUN, "browser_gone", True))

            tab1 = await open_tab1(context, cfg)
            log("\n👉 [DUAL-TAB SETUP]:")
            log("   TAB-1 par ChatGPT logged-in & fresh chat par ready rakho (TAB-2 apne aap khulega).")
            await asyncio.to_thread(input, "   Ready hone par PowerShell mein [ENTER] dabao... ")
            if tab1.is_closed():
                tab1 = await open_tab1(context, cfg)
            tab2 = await open_tab2(context, cfg, tab1)
            log("   ✅ TAB-2 opened. Starting the batch...")

            slot1 = TabSlot("TAB-1 (ODD)", context, tab1, cfg)
            slot2 = TabSlot("TAB-2 (EVEN)", context, tab2, cfg)
            results: List[Dict] = []
            for s_idx, md_path in enumerate(story_batch):
                if RUN.browser_gone:
                    log("❌ Brave was closed or disconnected — stopping. Run the same command again to resume.")
                    break
                try:
                    results.append(
                        await process_one_story_in_dual_tabs(
                            slot1=slot1,
                            slot2=slot2,
                            base_dir=base_dir,
                            md_path=md_path,
                            cfg=cfg,
                            ui_lock=ui_lock,
                            cooldown=cooldown,
                            is_first_episode=(s_idx == 0),
                        )
                    )
                except Exception as ep_exc:
                    log(f"⚠️ Story error on {md_path.name}: {short_err(ep_exc, 300)} — recovering tabs and continuing batch...")
                    results.append({"story": md_path.name, "slug": build_short_ep_slug(md_path.stem), "total": 0, "saved": 0,
                                    "missing": ["(episode error)"], "no_refs": []})
                    try:
                        await asyncio.gather(slot1.recover("fresh"), slot2.recover("fresh"))
                    except Exception:
                        pass

            log("\n" + "=" * 100)
            log(f"🎉 ALL REQUESTED EPISODES FINISHED IN AGENT 2 {VERSION}! ({fmt_secs(time.monotonic() - run_started)})")
            for r in results:
                mark = "✅" if not r["missing"] else f"⚠️ missing {len(r['missing'])}"
                log(f"   {r['slug']:<36} {r['saved']:>3}/{r['total']:<3} {mark}")
            log("=" * 100)
            if not attached:
                try:
                    await context.close()
                except Exception:
                    pass
    finally:
        prevent_windows_sleep(False)


if __name__ == "__main__":
    try:
        asyncio.run(run_agent_2())
    except KeyboardInterrupt:
        log("\n[STOPPED BY USER]")
