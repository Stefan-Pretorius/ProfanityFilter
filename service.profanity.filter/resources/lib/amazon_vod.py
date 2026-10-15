"""
amazon_vod.py
-------------
Subtitle discovery helpers for the Amazon VOD add-on
(plugin.video.amazon-test).

Why this exists
---------------
The Amazon VOD add-on never hands Kodi a subtitle URL. It fetches the
subtitle list from Amazon, then rewrites every entry to point at a small
local HTTP proxy of its own:

    http://127.0.0.1:<port>/subtitles/<quote_plus(ttml_url)>/<name>.srt

Kodi receives those local URLs through ``ListItem.setSubtitles()``, so all
JSON-RPC ever reports is an opaque "(External)" track with no URL - and a
generic "find a URL ending in .srt in the log" search finds nothing either,
because the add-on logs each proxy request as a *list* of path segments:

    [PS] Requested GET path ['subtitles', 'https%3A%2F%2F...ttml2', 'en.srt']

Two facts make the subtitle reachable anyway:

  * the proxy's address is written to the add-on's
    ``config/proxyaddress`` file (for example ``127.0.0.1:61049``), and
  * every proxied request is logged as above, so the escaped upstream URL
    and the local file name can be recovered from the log.

The proxy does the Amazon authentication and the TTML to SRT conversion
itself, so fetching ``http://127.0.0.1:<port>/subtitles/<escaped>/<name>``
needs no credentials at all.

The name the add-on gives each subtitle encodes its language and whether it
is a forced/SDH track, which is how the wanted track is chosen here. See
``_AdjustLocale()`` and ``_AlterGPR()`` in the add-on's
``resources/lib/proxy.py``.

Everything in this module is pure Python (no Kodi imports), so it can be
unit tested on an ordinary interpreter.
"""

import re

# The add-on's proxyaddress file holds exactly "127.0.0.1:61049".
_PROXY_ADDRESS_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3}:\d{1,5})\s*$")

# One line per proxied request, e.g.
#   [PS] Requested GET path ['subtitles', 'https%3A%2F%2F...ttml2', 'en.srt']
# The list is matched to the end of the line rather than to its closing
# bracket, because a subtitle name may itself contain one ("en-[CC].srt").
_SUBTITLE_REQUEST_RE = re.compile(
    r"Requested\s+(?:GET|POST)\s+path\s+(\[[^\n]*)")

# The individual quoted segments inside that list.
_PATH_ITEM_RE = re.compile(r"'([^']*)'")

# Suffixes the add-on appends so Kodi can work out the locale:
# '<lang>.srt', '<lang>-[CC].srt' (SDH), '<lang>.Forced.srt', ...
_FORCED_SUFFIX = ".Forced"
_SDH_SUFFIX = "-[CC]"

_MEDIA_SUFFIXES = (".srt", ".vtt", ".ass", ".ssa", ".sub")


def parse_proxy_address(text):
    """
    Return "host:port" from the contents of the add-on's proxyaddress file.

    Returns "" when the file is missing, empty or malformed. The add-on
    listens on an ephemeral port that changes per Kodi session, so this has
    to be re-read rather than cached.
    """
    if not text:
        return ""
    match = _PROXY_ADDRESS_RE.match(text.strip())
    return match.group(1) if match else ""


def parse_subtitle_requests(log_text):
    """
    Return the subtitle requests found in *log_text*, oldest first.

    Each entry is a dict with the percent-encoded upstream TTML URL and the
    local file name the add-on serves it as, for example
    ``{'escaped': 'https%3A%2F%2F...', 'filename': 'en-[CC].srt'}``.
    """
    requests = []
    for path_repr in _SUBTITLE_REQUEST_RE.findall(log_text or ""):
        items = _PATH_ITEM_RE.findall(path_repr)
        if len(items) < 3 or items[0] != "subtitles":
            continue
        escaped, filename = items[1], items[2]
        if escaped and filename:
            requests.append({"escaped": escaped, "filename": filename})
    return requests


def language_of(filename):
    """
    Return the ISO language code the add-on encoded in a subtitle file name.

    The add-on builds names as ``<lang>`` plus an optional ``-[CC]`` (SDH)
    and an optional ``.Forced``, so ``en-[CC].Forced.srt`` is English and
    ``da.srt`` is Danish. Regional variants (``fr-Canada``) fold back to
    their base code (``fr``).
    """
    name = (filename or "").strip()
    lowered = name.lower()
    for suffix in _MEDIA_SUFFIXES:
        if lowered.endswith(suffix):
            name = name[: -len(suffix)]
            break
    for suffix in (_FORCED_SUFFIX, _SDH_SUFFIX):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return re.split(r"[-_.]", name, 1)[0].lower()


def is_forced(filename):
    """True for a forced subtitle, which only translates the odd foreign line."""
    return _FORCED_SUFFIX in (filename or "")


def choose_subtitle(requests, preferred=("en",)):
    """
    Pick the best subtitle request out of *requests*, or None if there are none.

    The preferred language wins, then a non-forced track over a forced one,
    and among otherwise equal candidates the newest (last) one is used, since
    the add-on rewrites and re-serves a subtitle whenever the track changes.
    """
    if not requests:
        return None

    wanted = tuple(str(code).lower() for code in (preferred or ()))
    best = None
    best_rank = None
    for request in requests:
        filename = request.get("filename", "")
        rank = (
            0 if language_of(filename) in wanted else 1,
            1 if is_forced(filename) else 0,
        )
        # "<=" so that the newest of several equally good requests wins.
        if best_rank is None or rank <= best_rank:
            best, best_rank = request, rank
    return best


def build_subtitle_url(proxy_address, escaped_url, filename):
    """
    Assemble the local .srt URL served by the add-on's proxy.

    Returns "" if any part is missing. *escaped_url* is already
    percent-encoded, exactly as it appears in the add-on's log.
    """
    if not (proxy_address and escaped_url and filename):
        return ""
    return "http://{}/subtitles/{}/{}".format(
        proxy_address, escaped_url, filename)


def is_proxied_path(video_path, proxy_address):
    """
    True when *video_path* is being played through the Amazon VOD add-on.

    With its Android/inputstream playback the player's file is the proxied
    MPD, for example ``http://127.0.0.1:61049/mpd/https%3A%2F%2F...``.
    Matching the proxy address (not just the add-on id) means a video from
    another add-on can never be mistaken for one of Amazon's.
    """
    if not video_path or not proxy_address:
        return False
    lowered = video_path.lower()
    return (lowered.startswith("http://" + proxy_address.lower() + "/")
            or "plugin.video.amazon-test" in lowered)
