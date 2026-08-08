"""
subtitle_parser.py
------------------
Parses SRT and WebVTT subtitle files into a list of cue dictionaries.

Each cue has the form:
    {
        "start": float,   # start time in seconds
        "end":   float,   # end time in seconds
        "text":  str      # plain-text content of the cue
    }

NOTE: Return-type annotations use the typing module rather than the
      Python 3.10+ 'X | Y' union syntax, for compatibility with Kodi's
      embedded Python sub-interpreter.
"""

import re


# ---------------------------------------------------------------------------
# Time-string helpers
# ---------------------------------------------------------------------------

def _srt_time_to_seconds(ts):
    # type: (str) -> float
    """Convert SRT timestamp  HH:MM:SS,mmm  to seconds (float)."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    hours = float(parts[0])
    minutes = float(parts[1])
    seconds = float(parts[2])
    return hours * 3600.0 + minutes * 60.0 + seconds


def _vtt_time_to_seconds(ts):
    # type: (str) -> float
    """Convert VTT timestamp  [HH:]MM:SS.mmm  to seconds (float)."""
    ts = ts.strip()
    # Normalise separator: VTT uses '.' but some files use ':'
    # Split on ':' to get components
    parts = ts.split(":")
    if len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
    else:
        hours = 0.0
        minutes = float(parts[0])
        seconds = float(parts[1])
    return hours * 3600.0 + minutes * 60.0 + seconds


# ---------------------------------------------------------------------------
# Tag / formatting strippers
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_VTT_CUE_SETTING_RE = re.compile(
    r"\s+(align|line|position|region|size|vertical):\S+"
)


def _strip_tags(text):
    # type: (str) -> str
    """Remove HTML/XML tags and normalise whitespace."""
    text = _HTML_TAG_RE.sub("", text)
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# SRT parser
# ---------------------------------------------------------------------------

def parse_srt(content):
    # type: (str) -> list
    """
    Parse the text content of an SRT file.

    Returns a list of cue dicts.
    """
    cues = []
    # Normalise line endings
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Split on blank lines (cue separator)
    blocks = re.split(r"\n{2,}", content.strip())

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue

        # First line: sequence number (ignored)
        # Second line: timestamps
        ts_line = lines[1]
        ts_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            ts_line,
        )
        if not ts_match:
            continue

        start = _srt_time_to_seconds(ts_match.group(1))
        end = _srt_time_to_seconds(ts_match.group(2))
        text = _strip_tags(" ".join(lines[2:]))

        if text:
            cues.append({"start": start, "end": end, "text": text})

    return cues


# ---------------------------------------------------------------------------
# WebVTT parser
# ---------------------------------------------------------------------------

def parse_vtt(content):
    # type: (str) -> list
    """
    Parse the text content of a WebVTT file.

    Returns a list of cue dicts.
    """
    cues = []
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Remove the WEBVTT header block (everything up to the first blank line)
    content = re.sub(r"^WEBVTT[^\n]*\n+", "", content)

    blocks = re.split(r"\n{2,}", content.strip())

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        # Skip optional cue identifier line (it has no '-->' in it)
        ts_line_idx = 0
        if "-->" not in lines[0]:
            ts_line_idx = 1

        if ts_line_idx >= len(lines):
            continue

        ts_line = _VTT_CUE_SETTING_RE.sub("", lines[ts_line_idx])
        ts_match = re.match(
            r"(\d{1,2}:\d{2}:\d{2}[\.]\d{1,3}|\d{2}:\d{2}[\.]\d{1,3})"
            r"\s*-->\s*"
            r"(\d{1,2}:\d{2}:\d{2}[\.]\d{1,3}|\d{2}:\d{2}[\.]\d{1,3})",
            ts_line,
        )
        if not ts_match:
            continue

        start = _vtt_time_to_seconds(ts_match.group(1))
        end = _vtt_time_to_seconds(ts_match.group(2))

        text_lines = lines[ts_line_idx + 1:]
        text = _strip_tags(" ".join(text_lines))

        if text:
            cues.append({"start": start, "end": end, "text": text})

    return cues


# ---------------------------------------------------------------------------
# Auto-detect and dispatch
# ---------------------------------------------------------------------------

def parse_subtitle_content(content, format_hint="vtt"):
    # type: (str, str) -> list
    """
    Parse subtitle text content directly (without reading from a file).

    Parameters
    ----------
    content : str
        The raw subtitle text (SRT or VTT format).
    format_hint : str
        Either 'vtt' or 'srt' to indicate the format.
    """
    if not content:
        return []
    if format_hint == "vtt" or content.strip().startswith("WEBVTT"):
        return parse_vtt(content)
    return parse_srt(content)


def parse_subtitle_file(filepath):
    # type: (str) -> list
    """
    Read a subtitle file from *filepath* and return a list of cue dicts.

    Supports .srt and .vtt extensions. Falls back to SRT parsing for
    unknown extensions.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return []

    ext = filepath.rsplit(".", 1)[-1].lower()
    if ext == "vtt":
        return parse_vtt(content)
    else:
        return parse_srt(content)
