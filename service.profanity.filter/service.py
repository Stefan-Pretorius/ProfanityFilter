"""
service.py
----------
Kodi service add-on entry point for the Profanity Filter.

What this service does, in order, for every video that starts playing:

  1. Asks the source to deliver its subtitle (this is what makes streaming
     add-ons such as ororo.tv actually hand the subtitle over to Kodi).
  2. Waits for that subtitle to arrive, then reads/parses it.
  3. Hides the subtitle from the screen, so subtitle text - including
     profanity - is never displayed.
  4. Matches the subtitle cues against the bad-word list and mutes the audio
     in real time for the whole video.

The subtitle is used purely as a *data source* for timing. Once it has been
read, the display is switched off and stays off for the rest of the session.

Every run ends in an on-screen report, so it is always visible whether the
filter engaged or why it did not.

Compatible with Kodi 19 (Matrix), 20 (Nexus), and 21 (Omega).
"""

import os
import sys
import re
import json
import time
import threading

import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs

# ---------------------------------------------------------------------------
# Addon paths
# ---------------------------------------------------------------------------

_ADDON = xbmcaddon.Addon()
_ADDON_PATH = _ADDON.getAddonInfo("path")
_LIB_PATH = os.path.join(_ADDON_PATH, "resources", "lib")
_LOG_PATH = xbmcvfs.translatePath(
    "special://profile/addon_data/service.profanity.filter/report.txt")

if _LIB_PATH not in sys.path:
    sys.path.insert(0, _LIB_PATH)

from subtitle_parser import parse_subtitle_file, parse_subtitle_content
from word_matcher import load_word_list, build_patterns, find_matching_cues
from edl_generator import _build_intervals, _merge_intervals
from mute_controller import MuteController

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORD_LIST_PATH = os.path.join(_ADDON_PATH, "resources", "filter.txt")
LOG_TAG = "[ProfanityFilter]"

# How often (seconds) to poll the playback position for mute decisions
POLL_INTERVAL = 0.15  # 150ms

# How often (seconds) to double-check that subtitles are still hidden. Some
# streaming sources (ororo.tv) switch them back on by themselves shortly after
# they are turned off.
SUBS_CHECK_INTERVAL = 2.0

# Maximum amount of the Kodi log to read when hunting for a subtitle URL.
LOG_SCAN_BYTES = 400000

# Longest report we will try to show in a dialog before writing the rest to
# the log file. Keeps the on-screen text readable on a TV.
REPORT_MAX_LINES = 14


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(message, level=xbmc.LOGINFO):
    xbmc.log("{} {}".format(LOG_TAG, message), level=level)


def _get_setting(key, default=""):
    """Return a setting value as a string (falls back to *default*)."""
    try:
        val = _ADDON.getSetting(key)
        return val if val else default
    except (AttributeError, TypeError):
        return default


def _get_setting_float(key, default):
    try:
        val = _ADDON.getSetting(key)
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _get_setting_int(key, default):
    try:
        val = _ADDON.getSetting(key)
        return int(float(val)) if val else default
    except (ValueError, TypeError):
        return default


def _get_setting_bool(key, default):
    try:
        val = _ADDON.getSetting(key)
        if isinstance(val, bool):
            return val
        return val.lower() == "true"
    except (AttributeError, TypeError):
        return default


def _kodi_version():
    try:
        return xbmc.getInfoLabel("System.BuildVersion") or "unknown"
    except Exception:
        return "unknown"


def notify(message):
    """Show a brief Kodi notification bubble (if enabled in settings)."""
    if _get_setting_bool("show_notifications", True):
        xbmcgui.Dialog().notification(
            "Profanity Filter",
            message,
            xbmcgui.NOTIFICATION_INFO,
            3000,
        )


class Report(object):
    """
    Collects what happened during one playback so it can be shown on screen
    and written to a file. The add-on is often used on a box where getting at
    Kodi's log is impractical, so this is the primary way to find out why
    filtering did or did not happen.
    """

    def __init__(self):
        self.lines = []

    def add(self, line):
        self.lines.append(str(line))

    def text(self):
        return "\n".join(self.lines)


# ---------------------------------------------------------------------------
# Player monitor
# ---------------------------------------------------------------------------

class ProfanityFilterPlayer(xbmc.Player):
    """
    Subclass of xbmc.Player that reacts to playback events and performs
    real-time audio muting based on subtitle analysis.
    """

    def __init__(self, monitor):
        super(ProfanityFilterPlayer, self).__init__()
        self._monitor = monitor
        self._mute_controller = None
        self._processing_thread = None
        self._filter_thread = None
        self._log_offset = 0
        self._lock = threading.Lock()
        # Current playback session. Every new item gets its own stop event, so
        # stopping and starting playback can never leave an old scan thread
        # running against the new video (or silently skip the new one).
        self._generation = 0
        self._stop_event = None

    # ------------------------------------------------------------------
    # Kodi callbacks
    # ------------------------------------------------------------------
    #
    # These run on Kodi's own thread. They must stay free of JSON-RPC and GUI
    # work: re-entering the player from inside its own callback is unsafe, and
    # it is what stopped this add-on from working at all in v1.9.0. All of that
    # happens in the worker thread instead.

    def onPlayBackStarted(self):
        self._stop_current_muting()
        try:
            self._log_offset = _log_size()
        except Exception:
            self._log_offset = 0
        log("Playback started - scheduling subtitle scan.")
        generation, stop = self._begin_session()
        self._start_processing(generation, stop)

    def onAVStarted(self):
        log("AV started.", xbmc.LOGDEBUG)

    def onPlayBackStopped(self):
        log("Playback stopped.")
        self._stop_current_muting()

    def onPlayBackEnded(self):
        log("Playback ended.")
        self._stop_current_muting()

    def onPlayBackError(self):
        log("Playback error.")
        self._stop_current_muting()

    # ------------------------------------------------------------------
    # Playback session bookkeeping
    # ------------------------------------------------------------------

    def _begin_session(self):
        """
        Start a new playback session.

        Returns (generation, stop_event). The previous session's stop event is
        set first, so its threads wind down while the new ones run cleanly.
        """
        with self._lock:
            self._generation += 1
            generation = self._generation
            stop_event = threading.Event()
            previous = self._stop_event
            self._stop_event = stop_event
        if previous is not None:
            previous.set()
        return generation, stop_event

    def _stop_current_muting(self):
        """Signal the active session's threads to stop and unmute audio."""
        with self._lock:
            stop_event = self._stop_event
            self._stop_event = None
        if stop_event is not None:
            stop_event.set()
        if self._mute_controller:
            # Unmuting talks to Kodi, so do it off the callback thread.
            controller = self._mute_controller
            self._mute_controller = None
            unmuter = threading.Thread(target=controller.cleanup)
            unmuter.daemon = True
            unmuter.start()

    def _is_stale(self, stop_event, generation=None):
        """
        True if this session was superseded or the add-on is shutting down.

        *generation* is checked as well, so a session can never act on the
        player even if its own stop event has not been raised yet.
        """
        if stop_event.is_set() or self._monitor.abortRequested():
            return True
        return generation is not None and generation != self._generation

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _start_processing(self, generation, stop_event):
        """Spawn a background thread so we don't block Kodi's main thread."""
        self._processing_thread = threading.Thread(
            target=self._process_playback,
            args=(generation, stop_event),
        )
        self._processing_thread.daemon = True
        self._processing_thread.start()

    def _process_playback(self, generation, stop_event):
        """
        Core logic: get the subtitle -> hide it -> match bad words -> mute.

        Whatever happens, a report is shown on screen at the end so the outcome
        is never in doubt.
        """
        report = Report()
        report.add("Version {}".format(_ADDON.getAddonInfo("version")))
        report.add("Kodi {}".format(_kodi_version()))

        try:
            self._process(report, generation, stop_event)
        except Exception as e:
            log("Unexpected error: {}".format(str(e)), xbmc.LOGERROR)
            report.add("Unexpected error: {}".format(str(e)[:110]))
        finally:
            self._show_report(report)

    def _process(self, report, generation, stop_event):
        """The actual scan. Fills *report* as it goes."""
        subtitle_wait = _get_setting_int("subtitle_wait", 10)
        subtitle_retries = _get_setting_int("subtitle_retries", 10)
        retry_interval = 3  # seconds between retries

        # Tell the user straight away that the add-on is alive and working,
        # because "nothing happened" is otherwise indistinguishable from
        # "the add-on never ran".
        notify("Reading subtitles, starting filter...")

        # Wait a few seconds for the player to initialise and register itself.
        log("Waiting 3s for player to initialise...")
        for _ in range(3):
            if self._is_stale(stop_event, generation):
                return
            time.sleep(1)

        if not self.isPlaying():
            log("No longer playing - aborting scan.", xbmc.LOGDEBUG)
            return

        # Only now is it safe to ask Kodi what is playing. A video player is not
        # necessarily registered at the instant playback starts, so retry
        # before concluding this is not a video.
        if not self._wait_for_video_player(6, stop_event, generation):
            report.add("No video player active - nothing to filter (music?)")
            report.add("Result: SKIPPED (not a video)")
            log("No active video player - ignoring this item.", xbmc.LOGWARNING)
            return

        player_id = self._get_player_id()
        video_path = self._get_video_path()
        report.add("Video player id {}".format(player_id))
        if not video_path:
            report.add("Could not read the playing file path")
            report.add("Result: FAILED")
            log("Could not determine video path.", xbmc.LOGWARNING)
            return
        report.add("Source {}".format(
            "streaming" if video_path.startswith(
                ("http://", "https://", "plugin://")) else "local file"))

        # --- Load word list ---
        word_list = load_word_list(WORD_LIST_PATH)
        if not word_list:
            report.add("Word list filter.txt is empty")
            report.add("Result: FAILED")
            log("Bad-word list is empty - nothing to filter.", xbmc.LOGWARNING)
            notify("Bad-word list is empty. Add words to filter.txt.")
            return
        patterns = build_patterns(word_list)
        report.add("Word list: {} pattern(s)".format(len(patterns)))

        # --- Make the source hand us its subtitle ---
        # This is the step that makes streaming add-ons (ororo.tv) work: the
        # subtitle is only requested/opened once subtitles are switched on, so
        # we always ask for it, then give the source time to deliver it.
        #
        # A failed/"no track" result here is NOT a reason to give up. Streaming
        # add-ons commonly serve the subtitle as an external URL that Kodi
        # fetches without ever reporting it as a track, which is precisely why
        # we can find it in Kodi's log. Gating on this value (as 1.9.0 did)
        # skipped the search that actually works, so we only note it.
        enabled, exposed_tracks = self._ensure_subtitles_enabled()
        report.add("Subtitles: {}, {} track(s) exposed".format(
            "on" if enabled else "not on", exposed_tracks))
        if not enabled and exposed_tracks == 0:
            report.add("  (no track reported - will still look for a "
                       "subtitle URL)")

        if subtitle_wait:
            log("Waiting {}s for subtitle to load...".format(subtitle_wait))
            report.add("Waiting {}s for the subtitle".format(subtitle_wait))
            self._wait_for_subtitle(subtitle_wait, stop_event, generation)
            if self._is_stale(stop_event, generation) or not self.isPlaying():
                return

        # --- Locate and parse the subtitle (with retries) ---
        cues = None
        last_reason = []
        for attempt in range(1, subtitle_retries + 1):
            if self._is_stale(stop_event, generation):
                return

            # Re-request the subtitle each round: enabling it is asynchronous,
            # so a source may only expose/serve a track after a delay.
            if not self._subtitles_enabled():
                self._ensure_subtitles_enabled()

            cues, reason_a = self._try_get_subtitle_from_url()
            if cues:
                log("Got {} cues from subtitle URL (attempt {}).".format(
                    len(cues), attempt))
                last_reason = [reason_a]
                break
            last_reason.append(reason_a)

            cues, reason_b = self._try_get_subtitle_from_file(video_path)
            if cues:
                log("Got {} cues from local file (attempt {}).".format(
                    len(cues), attempt))
                last_reason = [reason_b]
                break
            last_reason.append(reason_b)

            log("Subtitle not found (attempt {}/{}): {}".format(
                attempt, subtitle_retries, " | ".join(last_reason[-2:])))
            if attempt < subtitle_retries:
                time.sleep(retry_interval)

        if not cues:
            log("No subtitle found or parsed - profanity filter inactive.",
                xbmc.LOGWARNING)
            # De-duplicate, but keep the order and cap the length so the
            # on-screen report stays readable.
            seen = []
            for reason in last_reason:
                if reason not in seen:
                    seen.append(reason)
            for reason in seen[-3:]:
                report.add("  " + reason[:70])
            report.add("Result: NO SUBTITLE (filter inactive)")
            notify("No subtitle found. Filter inactive for this video.")
            # We asked the source for subtitles, so switch the display back off
            # and keep it off, rather than leaving the source's subtitle on
            # screen for the rest of the video.
            self._hide_subtitles()
            self._mute_controller = MuteController([])
            self._start_filter_loop(stop_event, generation)
            return

        log("Parsed {} subtitle cue(s).".format(len(cues)))
        report.add("Subtitle read: {} cue(s)".format(len(cues)))

        # --- Read done: hide the subtitle text from the screen ---
        # Everything below only needs the parsed timings, never the display.
        self._hide_subtitles()

        if self._is_stale(stop_event, generation):
            return

        # --- Match bad words ---
        matched = find_matching_cues(cues, patterns)
        log("Found {} cue(s) containing bad words.".format(len(matched)))
        report.add("Profanity: {} of those cue(s) matched".format(len(matched)))

        if not matched:
            log("No bad words found in subtitles.")
            report.add("Result: CLEAN (subtitles hidden, nothing to mute)")
            notify("No bad words found. Subtitles hidden, nothing to mute.")
            # Nothing to mute, but still keep the subtitles hidden for the
            # whole video.
            self._mute_controller = MuteController([])
            self._start_filter_loop(stop_event, generation)
            return

        # --- Build mute intervals ---
        pre_buf = _get_setting_float("pre_buffer", 0.3)
        post_buf = _get_setting_float("post_buffer", 0.3)
        intervals = _build_intervals(matched, pre_buffer=pre_buf, post_buffer=post_buf)
        merged = _merge_intervals(intervals)

        log("Created {} mute interval(s). Starting real-time monitor.".format(
            len(merged)))
        report.add("Mute windows: {} ({}s before, {}s after)".format(
            len(merged), pre_buf, post_buf))
        report.add("Result: FILTER ACTIVE - subtitles hidden")
        notify("{} word(s) will be muted.".format(len(matched)))

        # --- Start the real-time filter loop ---
        self._mute_controller = MuteController(merged)
        self._start_filter_loop(stop_event, generation)

    def _show_report(self, report):
        """
        Put the outcome on screen and in the log.

        The whole report is always written to the add-on's own report.txt so
        it survives, and the first few lines are shown on screen. When the
        report is a dialog the user has to acknowledge, it cannot be missed
        while watching a video.
        """
        text = report.text()
        log("---- report ----\n{}".format(text))

        try:
            directory = os.path.dirname(_LOG_PATH)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(_LOG_PATH, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.write("\n")
        except OSError as e:
            log("Could not write report file: {}".format(str(e)))

        if not _get_setting_bool("show_report", True):
            return

        lines = report.lines
        if len(lines) > REPORT_MAX_LINES:
            extra = len(lines) - REPORT_MAX_LINES
            lines = lines[:REPORT_MAX_LINES - 1] + ["... +{} line(s), see report.txt".format(extra)]
        text = "\n".join(lines)

        try:
            if _get_setting_bool("report_modal", True):
                # Stays on screen until dismissed - a timed bubble disappears
                # long before you can read it on a TV.
                xbmcgui.Dialog().ok("Profanity Filter", text)
            else:
                xbmcgui.Dialog().notification(
                    "Profanity Filter", text,
                    xbmcgui.NOTIFICATION_WARNING, 10000)
        except Exception as e:
            log("Could not show report: {}".format(str(e)))

    def _wait_for_video_player(self, seconds, stop_event, generation):
        """
        Wait for a video player to register itself.

        Playback can start before Kodi lists the player, so a single immediate
        check is not enough - that is what made the add-on skip videos while
        still appearing to run. Returns True once a video player is active.
        """
        for _ in range(seconds):
            if self._is_stale(stop_event, generation):
                return False
            if self._is_video_playing():
                return True
            time.sleep(1)
        return self._is_video_playing()

    def _wait_for_subtitle(self, seconds, stop_event, generation):
        """
        Give the source *seconds* to deliver the subtitle, re-requesting it
        every few seconds in case the first request was too early.
        """
        requested_again_at = 3
        for elapsed in range(1, seconds + 1):
            if self._is_stale(stop_event, generation):
                return
            time.sleep(1)
            if elapsed == requested_again_at:
                requested_again_at += 3
                if not self._subtitles_enabled():
                    self._ensure_subtitles_enabled()

    # ------------------------------------------------------------------
    # Subtitle acquisition strategies
    # ------------------------------------------------------------------

    def _try_get_subtitle_from_url(self):
        """
        Try to find the subtitle URL and download/parse it.
        Returns (list_of_cues, reason_str) - cues is None if not found.
        """
        url = self._find_subtitle_url()
        if not url:
            return None, "no subtitle URL found (JSON-RPC and log scan)"

        content = self._download_subtitle(url)
        if not content:
            return None, "subtitle URL found but download failed"

        fmt = "vtt" if ".vtt" in url.lower() else "srt"
        cues = parse_subtitle_content(content, format_hint=fmt)
        if cues:
            return cues, "read {} cues from the subtitle URL".format(len(cues))
        return None, "subtitle URL downloaded but parsed to 0 cues"

    def _try_get_subtitle_from_file(self, video_path):
        """
        Try to find a local subtitle file and parse it.
        Returns (list_of_cues, reason_str) - cues is None if not found.
        """
        from subtitle_locator import find_subtitle_for_video
        subtitle_path = find_subtitle_for_video(video_path)
        if not subtitle_path:
            return None, "no subtitle file found on the device"
        cues = parse_subtitle_file(subtitle_path)
        if cues:
            return cues, "read {} cues from a local file".format(len(cues))
        return None, "local subtitle file parsed to 0 cues"

    def _find_subtitle_url(self):
        """
        Find the subtitle URL using multiple strategies:
        1. Check Kodi JSON-RPC for current subtitle info
        2. Parse the Kodi log file for the subtitle URL
        """
        # Strategy 1: JSON-RPC
        url = self._get_subtitle_url_from_jsonrpc()
        if url:
            log("Subtitle URL found via JSON-RPC.")
            return url

        # Strategy 2: Parse the Kodi log (most reliable for ororo.tv)
        url = self._find_subtitle_url_in_log()
        if url:
            log("Subtitle URL found via log scan.")
            return url

        return ""

    def _get_subtitle_url_from_jsonrpc(self):
        """
        Use Kodi JSON-RPC to check if the current subtitle has a URL.
        """
        try:
            result = self._player_properties(
                ["currentsubtitle", "subtitles", "subtitleenabled"])
            if not result:
                return ""

            if not result.get("subtitleenabled", False):
                log("Subtitles not enabled yet.")
                return ""

            current_sub = result.get("currentsubtitle", {})
            if not isinstance(current_sub, dict):
                current_sub = {}

            sub_name = current_sub.get("name", "")
            sub_index = current_sub.get("index", -1)
            log("Current subtitle: index={}, name='{}'".format(sub_index, sub_name))

            # Check if the name contains a URL
            if sub_name and ("http://" in sub_name or "https://" in sub_name):
                log("Subtitle name is a URL!")
                return sub_name

            # Log available subtitles for debugging
            subtitles = result.get("subtitles", [])
            if isinstance(subtitles, list):
                log("Available subtitle streams: {}".format(len(subtitles)))
                for sub in subtitles:
                    if not isinstance(sub, dict):
                        continue
                    sname = sub.get("name", "")
                    log("  Sub: name='{}' lang='{}'".format(
                        sname, sub.get("language", "")))
                    if "http://" in sname or "https://" in sname:
                        return sname

        except Exception as e:
            log("JSON-RPC subtitle check error: {}".format(str(e)))

        return ""

    def _find_subtitle_url_in_log(self):
        """
        Parse Kodi's log file to find the most recent subtitle URL.
        Kodi logs the subtitle URL when it opens it for streaming, which is
        the most reliable way to get at it for ororo.tv.

        Only entries written since this video started playing are considered
        first, so a subtitle URL left over from a *previous* video can never be
        mistaken for this one. If that yields nothing, the whole log is scanned
        as a fallback.
        """
        pattern = re.compile(
            r"(https?://[^\s\"'<>)\]]+?\.(?:vtt|srt|ass|ssa|sub)"
            r"(?:[^\s\"'<>)\]]*))",
            re.IGNORECASE,
        )

        for label, start_at in (("new log entries", self._log_offset), ("log tail", None)):
            matches = self._scan_log_for(pattern, start_at)
            if matches:
                url = matches[-1].rstrip(">'\")")
                log("Found subtitle URL in {}: {}".format(label, url[:150]))
                return url

        log("No subtitle URL found in the log.")
        return ""

    def _scan_log_for(self, pattern, start_at=None):
        """
        Return every subtitle URL in kodi.log.

        *start_at* limits the read to bytes written from that offset onwards
        (None means "read the last LOG_SCAN_BYTES bytes").
        """
        log_path = _log_path()
        if not log_path:
            return []

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)  # Seek to end
                file_size = f.tell()

                if start_at is None or start_at >= file_size:
                    # No new entries to read (log rotated or nothing happened
                    # yet) - fall back to the recent tail.
                    begin = max(0, file_size - LOG_SCAN_BYTES)
                else:
                    begin = start_at

                f.seek(begin)
                content = f.read()

            return pattern.findall(content)
        except OSError as e:
            log("Error reading log for subtitle URL: {}".format(str(e)))
            return []

    def _download_subtitle(self, url):
        """
        Download a subtitle file from a URL and return its text content.
        """
        try:
            log("Downloading subtitle from: {}".format(url[:120]))

            # Method 1: xbmcvfs.File (handles Kodi's internal URL schemes)
            try:
                f = xbmcvfs.File(url)
                content = f.read()
                f.close()

                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")

                if content and len(content) > 50:
                    log("Downloaded {} bytes via xbmcvfs.".format(len(content)))
                    return content
                else:
                    log("xbmcvfs returned {} bytes - trying urllib.".format(
                        len(content) if content else 0))
            except Exception as e:
                log("xbmcvfs.File error: {}".format(str(e)))

            # Method 2: Python urllib
            try:
                import urllib.request
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "Kodi/21.0")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read().decode("utf-8", errors="replace")
                if content and len(content) > 50:
                    log("Downloaded {} bytes via urllib.".format(len(content)))
                    return content
            except Exception as e:
                log("urllib error: {}".format(str(e)))

        except Exception as e:
            log("Download error: {}".format(str(e)))

        return ""

    # ------------------------------------------------------------------
    # JSON-RPC helpers
    # ------------------------------------------------------------------

    def _player_properties(self, properties):
        """Return Player.GetProperties for the active video player (or {})."""
        try:
            request = json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.GetProperties",
                "params": {
                    "playerid": self._get_player_id(),
                    "properties": properties,
                },
                "id": 1,
            })
            response = json.loads(xbmc.executeJSONRPC(request))
            result = response.get("result", {})
            return result if isinstance(result, dict) else {}
        except Exception as e:
            log("Could not read player properties: {}".format(str(e)))
            return {}

    def _set_subtitle(self, value, enable=None):
        """Send Player.SetSubtitle for the active video player."""
        params = {"playerid": self._get_player_id(), "subtitle": value}
        if enable is not None:
            params["enable"] = enable
        try:
            xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.SetSubtitle",
                "params": params,
                "id": 2,
            }))
            return True
        except Exception as e:
            log("Error setting subtitle ({}): {}".format(value, str(e)))
            return False

    def _get_player_id(self, default=1):
        """
        Return the playerid of the active video player (or *default*).
        Hardcoding playerid 1 fails when other players (e.g. audio) are
        active, so we ask Kodi which player is currently playing video.
        """
        try:
            for player in self._active_players():
                if player.get("type") == "video":
                    return player.get("playerid", default)
        except Exception as e:
            log("Could not resolve active player id: {}".format(str(e)))
        return default

    def _active_players(self):
        """Return Kodi's list of active players."""
        request = json.dumps({
            "jsonrpc": "2.0",
            "method": "Player.GetActivePlayers",
            "id": 0,
        })
        response = json.loads(xbmc.executeJSONRPC(request))
        players = response.get("result", [])
        return players if isinstance(players, list) else []

    def _is_video_playing(self):
        """
        True when a video player is active.

        If the call itself fails we assume video: better to try to filter than
        to silently skip.
        """
        try:
            for player in self._active_players():
                if player.get("type") == "video":
                    return True
        except Exception as e:
            log("Could not list active players: {}".format(str(e)))
            return True
        return False

    # ------------------------------------------------------------------
    # Subtitle visibility control
    # ------------------------------------------------------------------

    def _subtitles_enabled(self):
        """Return True if the active video player currently has subtitles on."""
        return bool(self._player_properties(["subtitleenabled"]).get(
            "subtitleenabled", False))

    def _get_subtitle_track_list(self):
        """
        Return the list of subtitle tracks currently exposed by the player.
        For external-URL streaming add-ons this list is often empty until the
        source actually delivers a subtitle; enabling subs is an asynchronous
        negotiation with the source, so the list can also grow after we send
        the enable request.
        """
        result = self._player_properties(
            ["subtitleenabled", "subtitles", "currentsubtitle"])
        tracks = result.get("subtitles", [])
        if not isinstance(tracks, list):
            tracks = []
        return tracks, bool(result.get("subtitleenabled", False))

    def _ensure_subtitles_enabled(self, attempts=3, wait=1.0):
        """
        Ask the source to deliver its subtitle, and wait for it to become
        active.

        Streaming add-ons often expose zero subtitle tracks while subtitles are
        disabled; the source only starts delivering one after the enable
        request, and that delivery is asynchronous. We therefore:
          1. Enable the currently-active subtitle with the "on" enum (asks the
             source to start delivering whatever it has), and
          2. Also explicitly select any exposed track by index with
             'enable': true (the index+enable form sticks more reliably than
             a bare "on"), and
          3. Re-query the exposed track list a few times, since a track can
             appear after a short delay.

        Returns (enabled, track_count) so callers can tell whether a real
        subtitle track ended up active or whether the source simply exposes
        no subtitle for this title.
        """
        try:
            tracks, enabled_now = self._get_subtitle_track_list()
            if enabled_now:
                log("Subtitles already enabled ({} track(s) exposed).".format(
                    len(tracks)))
                return True, len(tracks)

            # Ask the source to start delivering whatever subtitle it has.
            self._set_subtitle("on")
            log("Requested subtitles ON ({} track(s) exposed initially).".format(
                len(tracks)))

            for attempt in range(1, attempts + 1):
                time.sleep(wait)

                # Re-read the exposed list - it may have grown since enabling.
                tracks, enabled_now = self._get_subtitle_track_list()

                # Explicitly select the currently-exposed track with enable=true.
                # This is the form that sticks most reliably on streaming.
                if not enabled_now and tracks:
                    index = tracks[0].get("index", 0)
                    self._set_subtitle(index, enable=True)
                    log("Selected enabled subtitle index {} (attempt {}).".format(
                        index, attempt))

                if enabled_now:
                    log("Subtitles became active after {} attempt(s) ({} track(s)).".format(
                        attempt, len(tracks)))
                    return True, len(tracks)

            return False, len(tracks)

        except Exception as e:
            log("Error requesting subtitles: {}".format(str(e)))
            return False, 0

    def _hide_subtitles(self):
        """
        Hide subtitle display without fully disabling the subtitle stream.
        Uses Player.SetSubtitle with "off" to stop rendering subtitles
        on screen. The subtitle data has already been parsed so we no
        longer need it visible.
        """
        if self._set_subtitle("off"):
            log("Subtitle display turned OFF.")

    # ------------------------------------------------------------------
    # Real-time filter loop
    # ------------------------------------------------------------------

    def _start_filter_loop(self, stop_event, generation):
        """
        Start the real-time loop in a background thread.

        A single loop drives both jobs so they cannot fight each other:
          - mute/unmute the audio as playback crosses a bad-word window, and
          - make sure subtitles stay hidden (some sources switch them back on).
        """
        self._filter_thread = threading.Thread(
            target=self._filter_loop, args=(stop_event, generation))
        self._filter_thread.daemon = True
        self._filter_thread.start()

    def _filter_loop(self, stop_event, generation):
        """
        Poll the playback position and mute/unmute as needed, and re-hide the
        subtitles if the source turns them back on.
        Runs until playback stops or the stop event is set.
        """
        controller = self._mute_controller
        if not controller:
            return

        log("Filter loop started ({} mute interval(s)).".format(
            controller.interval_count))

        next_subs_check = 0.0
        subs_reenabled = 0

        while not self._is_stale(stop_event, generation):
            try:
                if not self.isPlaying():
                    break
                controller.update(self.getTime())
            except RuntimeError:
                break
            except Exception as e:
                log("Filter loop error: {}".format(str(e)))
                break

            # Keep the subtitle text off the screen for the whole session.
            now = time.time()
            if now >= next_subs_check:
                next_subs_check = now + SUBS_CHECK_INTERVAL
                try:
                    if self.isPlaying() and self._subtitles_enabled():
                        self._hide_subtitles()
                        subs_reenabled += 1
                        if subs_reenabled <= 3:
                            log("Subtitles switched back on by the source - "
                                "hiding again (#{}).".format(subs_reenabled))
                except Exception as e:
                    log("Subtitle check error: {}".format(str(e)))

            time.sleep(POLL_INTERVAL)

        controller.cleanup()
        log("Filter loop ended ({} re-hide(s) needed).".format(subs_reenabled))

    def _get_video_path(self):
        """Return the path/URL of the currently playing item."""
        try:
            return self.getPlayingFile()
        except RuntimeError:
            return ""


# ---------------------------------------------------------------------------
# Kodi log helpers
# ---------------------------------------------------------------------------

def _log_path():
    """Return the path to kodi.log, or "" if it cannot be found."""
    try:
        path = xbmcvfs.translatePath("special://logpath/kodi.log")
        if os.path.isfile(path):
            return path
        log_dir = xbmcvfs.translatePath("special://logpath/")
        path = os.path.join(log_dir, "kodi.log")
        return path if os.path.isfile(path) else ""
    except Exception as e:
        log("Could not locate kodi.log: {}".format(str(e)))
        return ""


def _log_size():
    """
    Current size of kodi.log in bytes (0 if unavailable).

    Recorded when playback starts so only log lines written for *this* video
    are considered when hunting for its subtitle URL.
    """
    path = _log_path()
    if not path:
        return 0
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Service main loop
# ---------------------------------------------------------------------------

def main():
    log("Service started (version {}).".format(
        _ADDON.getAddonInfo("version")
    ))

    monitor = xbmc.Monitor()
    player = ProfanityFilterPlayer(monitor)

    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break

    player._stop_current_muting()
    log("Service stopped.")


if __name__ == "__main__":
    main()
