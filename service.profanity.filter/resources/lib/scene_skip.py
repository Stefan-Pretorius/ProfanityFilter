"""
scene_skip.py
-------------
Scene-skipping for the Profanity Filter Kodi add-on.

When enabled, the add-on can jump past unwanted scenes (scary / intense /
mature) instead of just muting audio. Scene windows are read from timed
skip lists so parents can curate their own safe cutting points, entirely
offline and without any external service.

Skip list format (one start/end per line, `#` = comment):

    00:05:30 00:06:15
    1:23:45 1:24:30      # m:ss or h:mm:ss
    83.5 84.2            # plain seconds

Times are treated as whole-video seconds. The controller seeks forward to
the end of a scene window as playback approaches the start, so the viewer
never sees the flagged moment.
"""

import json
import os
import re

try:
    import xbmc
    import xbmcvfs
    _IN_KODI = True
except ImportError:
    _IN_KODI = False


def _log(msg):
    if _IN_KODI:
        xbmc.log("[ProfanityFilter] " + msg, xbmc.LOGINFO)


_TS_RE = re.compile(r"^\s*(\d+):(\d{1,2}):(\d{1,2}(?:[.,]\d+)?)\s*$")
_MS_RE = re.compile(r"^\s*(\d+):(\d{1,2}(?:[.,]\d+)?)\s*$")
_SEC_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")


def _to_seconds(token):
    """Convert one time token (mm:ss, hh:mm:ss, or bare seconds) to float."""
    token = token.strip()
    match = _TS_RE.match(token)
    if match and token.count(":") == 2:
        h, m, s = match.groups()
        return float(h) * 3600.0 + float(m) * 60.0 + float(s.replace(",", "."))
    match = _MS_RE.match(token)
    if match and token.count(":") == 1:
        m, s = match.groups()
        return float(m) * 60.0 + float(s.replace(",", "."))
    match = _SEC_RE.match(token)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def parse_skip_content(content):
    # type: (str) -> list
    """
    Parse skip-list text into a list of (start, end) tuples in seconds.
    Malformed lines are skipped, and any start > end pair is dropped.
    """
    intervals = []
    for raw in content.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        start = _to_seconds(parts[0])
        end = _to_seconds(parts[1])
        if start is None or end is None:
            continue
        if end > start:
            intervals.append((start, end))
    return intervals


def parse_skip_file(filepath):
    # type: (str) -> list
    """Read a skip list from *filepath* and return (start, end) tuples."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            return parse_skip_content(fh.read())
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Remote (hosted JSON) skip data
#
# Skip timestamps can be published as a single JSON document on a web URL
# (e.g. the add-on's GitHub Pages site) instead of being copied onto the Kodi
# device. This is what makes automated scene-skipping work on devices where
# you can't easily add files, such as a Google Streamer / Android TV box.
#
# Hosted document format (skipdata.json):
#
#   {
#     "version": 1,
#     "skipdata": {
#       "avatar (2009)": [
#           {"start": "1:03:45", "end": "1:03:56"},
#           {"start": "1:20:28", "end": "1:20:42"}
#       ],
#       "default": [
#           {"start": "00:15:00", "end": "00:15:30"}
#       ]
#     }
#   }
#
# Keys are lowercase movie titles (same rule as local .skip.txt files) plus an
# optional "default" key that applies to every video.
# ---------------------------------------------------------------------------


def _ts_to_seconds(value):
    """Convert a JSON timestamp (seconds, mm:ss, or h:mm:ss) to float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return _to_seconds(value)
    return None


def parse_skip_json(content):
    # type: (str) -> dict
    """
    Parse the hosted skip JSON into {title_key: [(start, end), ...]}.
    Returns {} if the document is missing/empty/malformed.
    """
    try:
        doc = json.loads(content)
    except (ValueError, TypeError):
        return {}
    skipdata = doc.get("skipdata") if isinstance(doc, dict) else None
    if not isinstance(skipdata, dict):
        return {}
    result = {}
    for title, entries in skipdata.items():
        if not isinstance(entries, list):
            continue
        intervals = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            start = _ts_to_seconds(entry.get("start"))
            end = _ts_to_seconds(entry.get("end"))
            if start is not None and end is not None and end > start:
                intervals.append((start, end))
        if intervals:
            result.setdefault(title.strip().lower(), []).extend(intervals)
    return result


def _download_text(url, timeout=15):
    # type: (str, int) -> str
    """Fetch *url* and return its text content ("" on failure)."""
    if _IN_KODI:
        # Method 1: xbmcvfs handles Kodi's internal URL stack.
        try:
            f = xbmcvfs.File(url)
            try:
                content = f.read()
            finally:
                f.close()
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            if content:
                return content
        except Exception:
            pass
    # Method 2: Python stdlib urllib.
    try:
        import urllib.request
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Kodi/21.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        return content
    except Exception:
        return ""


def get_remote_skip_data(url):
    # type: (str) -> dict
    """
    Fetch and parse the hosted skip JSON from *url*.
    Returns {title_key: [(start, end), ...]} or {} on any failure.
    """
    if not url:
        return {}
    try:
        content = _download_text(url)
    except Exception:
        return {}
    if not content:
        _log("No remote skip data fetched from {}".format(url))
        return {}
    return parse_skip_json(content)


def match_remote_intervals(data, *title_keys):
    # type: (dict, *str) -> list
    """
    Extract the skip intervals that apply to a video from hosted *data*.
    *title_keys* is one or more lowercase lookup keys for the video (e.g. the
    clean URL title and/or the metadata title from Player.GetItem). Each key
    that has an entry in *data* contributes its windows; the "default" entry
    is always added.
    """
    intervals = []
    seen = set()
    for key in title_keys:
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        exact = data.get(key)
        if exact:
            intervals.extend(exact)
    fallback = data.get("default")
    if fallback:
        intervals.extend(fallback)
    return intervals


def get_skip_dir():
    # type: () -> str
    """Return the add-on's skip-list directory path (as a real OS path)."""
    if _IN_KODI:
        base = xbmcvfs.translatePath(
            "special://profile/addon_data/service.profanity.filter/"
        )
    else:
        base = os.path.join(os.path.expanduser("~"), "profanity_filter_skip")
    skip_dir = os.path.join(base, "skiplists")
    if not os.path.isdir(skip_dir):
        try:
            os.makedirs(skip_dir)
        except OSError:
            pass
    return skip_dir


def _clean_title(video_path):
    """Derive a lookup key from a video path/URL (lowercase, no extension)."""
    import re as _re
    clean = _re.sub(r"[?#].*$", "", video_path)
    clean = clean.rstrip("/\\")
    base = clean.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # Drop file extensions (keep known multi-part bases intact implicitly).
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return base.lower()


def _scan_dir(skip_dir, base):
    """Look for a matching or global skip file inside *skip_dir*."""
    if not os.path.isdir(skip_dir):
        return ""
    try:
        names = os.listdir(skip_dir)
    except OSError:
        return ""
    candidates = []
    for fname in names:
        if not fname.lower().endswith(".skip.txt"):
            continue
        stem = fname[:-len(".skip.txt")]
        candidates.append(stem.lower())
        if stem.lower() == base:
            return os.path.join(skip_dir, fname)
    if "global" in candidates:
        return os.path.join(skip_dir, "global.skip.txt")
    return ""


def find_skip_file(video_path):
    # type: (str) -> str
    """
    Find the most specific skip list for *video_path*, if any.

    Search order:
      1. A file matching the video's base name (case-insensitive), e.g.
         "Avatar (2009).skip.txt"
      2. "global.skip.txt"  (applies to every video)

    Two folders are checked: the user's profile skip folder first
    (special://profile/addon_data/service.profanity.filter/skiplists/),
    then skip lists bundled with the add-on itself
    (resources/skiplists/).

    Returns the path, or "" if none matched.
    """
    base = _clean_title(video_path).lower()

    # User's profile folder (writable — this is where to add/edit lists).
    found = _scan_dir(get_skip_dir(), base)
    if found:
        return found

    # Bundled lists shipped inside the add-on (read-only).
    addon_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled = os.path.join(addon_path, "skiplists")
    found = _scan_dir(bundled, base)
    if found:
        return found

    return ""


class SceneSkipController(object):
    """
    Jumps the player past scene windows as it approaches them.

    The controller watches a monotonic advance of playback time. When the
    current time enters the lookahead zone of the next unsought scene
    (start - lookahead), it seeks the player to that scene's end (+ a small
    tail buffer) and marks the scene as handled so it only happens once.

    Parameters
    ----------
    player : xbmc.Player
        The active player instance used to read time and seek.
    intervals : list of (float, float)
        Sorted, merged (start, end) scene windows in seconds.
    lookahead : float
        How many seconds *before* a scene start to trigger the jump.
    tail_buffer : float
        Seconds to add after a scene's end so the action is fully past.
    """

    def __init__(self, player, intervals, lookahead=10.0, tail_buffer=1.0):
        self._player = player
        self._intervals = sorted(intervals, key=lambda iv: iv[0])
        self._lookahead = lookahead
        self._tail_buffer = tail_buffer
        self._idx = 0
        self._last_seek_time = None

    @property
    def count(self):
        # type: () -> int
        return len(self._intervals)

    def update(self, current_time):
        # type: (float) -> None
        """
        Call periodically with the current playback time (seconds).
        Triggers a forward seek when a scene window is about to start.
        """
        if self._idx >= len(self._intervals):
            return

        idx = self._idx
        while idx < len(self._intervals):
            start, end = self._intervals[idx]
            if current_time < start - self._lookahead:
                # Still too far from this scene to act.
                break
            if current_time < end:
                # Approaching or inside the scene — jump past it, then stop.
                self._seek(end + self._tail_buffer)
                self._idx = idx + 1
                return
            # Already past this scene; move on to the next window.
            idx += 1
            self._idx = idx

    def _seek(self, target_seconds):
        # type: (float) -> None
        """Seek the player to *target_seconds*, guarding against re-entry."""
        if self._last_seek_time is not None and target_seconds == self._last_seek_time:
            return
        try:
            self._player.seekTime(target_seconds)
            self._last_seek_time = target_seconds
            _log("Scene skip -> seek to {:.1f}s".format(target_seconds))
        except RuntimeError:
            pass
