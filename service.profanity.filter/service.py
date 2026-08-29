"""
service.py
----------
Kodi service add-on entry point for the Profanity Filter.

This service monitors video playback, locates the active subtitle
(from streaming URLs or local files), matches bad words against the
subtitle cues, and mutes audio in real-time during profanity.

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

if _LIB_PATH not in sys.path:
    sys.path.insert(0, _LIB_PATH)

from subtitle_parser import parse_subtitle_file, parse_subtitle_content
from word_matcher import load_word_list, build_patterns, find_matching_cues
from edl_generator import _build_intervals, _merge_intervals
from mute_controller import MuteController
from scene_skip import (
    SceneSkipController,
    find_skip_file,
    parse_skip_file,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORD_LIST_PATH = os.path.join(_ADDON_PATH, "resources", "filter.txt")
LOG_TAG = "[ProfanityFilter]"

# How often (seconds) to poll the playback position for mute decisions
POLL_INTERVAL = 0.15  # 150ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(message, level=xbmc.LOGINFO):
    xbmc.log("{} {}".format(LOG_TAG, message), level=level)


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


def notify(message):
    """Show a brief Kodi notification bubble (if enabled in settings)."""
    if _get_setting_bool("show_notifications", True):
        xbmcgui.Dialog().notification(
            "Profanity Filter",
            message,
            xbmcgui.NOTIFICATION_INFO,
            3000,
        )


def notify_debug(message):
    """Show a diagnostics bubble that includes the specific failure stage.
    Only shown when the 'show_diagnostics' setting is enabled — used to
    troubleshoot subtitle discovery without needing to read Kodi's log."""
    if _get_setting_bool("show_diagnostics", False):
        xbmcgui.Dialog().notification(
            "PF Diagnose",
            message,
            xbmcgui.NOTIFICATION_WARNING,
            5000,
        )
    log(message)


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
        self._skip_controller = None
        self._processing_thread = None
        self._mute_thread = None
        self._skip_thread = None
        self._stop_muting = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Kodi callbacks
    # ------------------------------------------------------------------

    def onPlayBackStarted(self):
        log("Playback started — scheduling subtitle scan.")
        self._stop_current_muting()
        self._start_processing()

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
    # Processing
    # ------------------------------------------------------------------

    def _stop_current_muting(self):
        """Signal the mute/skip threads to stop and clean up."""
        self._stop_muting.set()
        if self._mute_controller:
            self._mute_controller.cleanup()
            self._mute_controller = None
        self._skip_controller = None

    def _start_processing(self):
        """Spawn a background thread so we don't block Kodi's main thread."""
        with self._lock:
            if self._processing_thread and self._processing_thread.is_alive():
                log("Processing thread already running — skipping.", xbmc.LOGDEBUG)
                return
            self._stop_muting.clear()
            self._processing_thread = threading.Thread(
                target=self._process_playback
            )
            self._processing_thread.daemon = True
            self._processing_thread.start()

    def _process_playback(self):
        """
        Core logic: find subtitles -> match bad words -> start real-time muting.

        Subtitles are only ever used as a *data source*. The subtitle display
        is turned back off on every exit path once the scan finishes, so
        profanity (or any subtitle) text never stays on screen. This also
        means the filter works even when the user keeps subtitles switched off.
        """
        subtitle_wait = _get_setting_int("subtitle_wait", 10)
        subtitle_retries = _get_setting_int("subtitle_retries", 10)
        retry_interval = 3  # seconds between retries

        # Wait a few seconds for the player to initialise
        log("Waiting 3s for player to initialise...")
        for _ in range(3):
            if self._stop_muting.is_set() or self._monitor.abortRequested():
                return
            time.sleep(1)

        if not self.isPlaying():
            log("No longer playing — aborting scan.", xbmc.LOGDEBUG)
            return

        video_path = self._get_video_path()
        if not video_path:
            log("Could not determine video path.", xbmc.LOGWARNING)
            return

        log("Processing: {}".format(video_path[:120]))

        # --- Load word list ---
        word_list = load_word_list(WORD_LIST_PATH)
        if not word_list:
            log("Bad-word list is empty — nothing to filter.", xbmc.LOGWARNING)
            notify("Bad-word list is empty. Add words to filter.txt.")
            return

        patterns = build_patterns(word_list)
        log("Loaded {} filter pattern(s).".format(len(patterns)))

        # --- Handle subtitles before scanning ---
        # The subtitle is only ever used as a *data source* for timing. If the
        # user already has subtitles switched on (the common default), we don't
        # touch the display at all while scanning — Kodi has already loaded the
        # subtitle, so we capture it straight away and hide the text afterwards.
        # If subtitles were OFF, we briefly force them on for streaming sources
        # long enough to capture the data, then restore the display state.
        matched = []
        subs_were_on = self._subtitles_enabled()
        subs_forced = False
        wait_time = 0

        if video_path.startswith(("http://", "https://", "plugin://")):
            log("Streaming source detected (playerid={}, subs_were_on={}).".format(
                self._get_player_id(), subs_were_on))
            if subs_were_on:
                # Subtitles already on — no need to wait, data should be ready.
                log("Subtitles already enabled — capturing data now.")
                notify_debug("Subtitles were ON. Capturing then hiding.[CR]Playerid={}".format(
                    self._get_player_id()))
            else:
                # Force them on so the streaming add-on delivers the subtitle.
                self._force_enable_subtitles()
                subs_forced = True
                wait_time = subtitle_wait
                enabled_now = self._subtitles_enabled()
                log("Subtitles active after force-enable: {}".format(enabled_now))
                if not enabled_now:
                    notify_debug("Tried to force subtitles on but none became active.[CR]Playerid={}".format(
                        self._get_player_id()))

        try:
            # --- Scene-skip setup (independent of subtitle discovery) ---
            # Skips flagged scenes regardless of whether subtitles are found,
            # so scary/mature skipping works even when the profanity filter
            # can't locate a subtitle for the video.
            if self._load_scene_skip(video_path):
                self._start_skip_loop()

            # Wait for a streaming subtitle to actually load (only when we had
            # to force it on). When subtitles were already on, skip the wait.
            if wait_time:
                log("Waiting {}s for subtitle to load...".format(wait_time))
                for _ in range(wait_time):
                    if self._stop_muting.is_set() or self._monitor.abortRequested():
                        return
                    time.sleep(1)

            if not self.isPlaying():
                log("No longer playing — aborting scan.", xbmc.LOGDEBUG)
                return

            # --- Locate subtitle (with retries) ---
            cues = None
            last_reason = []
            for attempt in range(1, subtitle_retries + 1):
                if self._stop_muting.is_set() or self._monitor.abortRequested():
                    return

                # Try Strategy A: Get subtitle URL and download it
                cues, reason_a = self._try_get_subtitle_from_url()
                if cues:
                    log("Got {} cues from subtitle URL (attempt {}).".format(len(cues), attempt))
                    break
                last_reason.append(reason_a)

                # Try Strategy B: Search for local subtitle file
                cues, reason_b = self._try_get_subtitle_from_file(video_path)
                if cues:
                    log("Got {} cues from local file (attempt {}).".format(len(cues), attempt))
                    break
                last_reason.append(reason_b)

                log("Subtitle not found (attempt {}/{}): {} | {}".format(
                    attempt, subtitle_retries, reason_a, reason_b))
                time.sleep(retry_interval)

            if not cues:
                log("No subtitle found or parsed — profanity filter inactive.", xbmc.LOGWARNING)
                reason = " | ".join(dict.fromkeys(last_reason))
                notify_debug("Subtitle not found.[CR]Player:{}[CR]{}".format(
                    self._get_player_id(), reason[:220]))
                notify("No subtitle found. Filter inactive for this video.")
                return

            log("Parsed {} subtitle cue(s).".format(len(cues)))

            # --- Match bad words ---
            matched = find_matching_cues(cues, patterns)
            log("Found {} cue(s) containing bad words.".format(len(matched)))

            if not matched:
                log("No bad words found in subtitles.")
                notify("No bad words found. Nothing to mute.")
                return

            # --- Build mute intervals ---
            pre_buf = _get_setting_float("pre_buffer", 0.3)
            post_buf = _get_setting_float("post_buffer", 0.3)
            intervals = _build_intervals(matched, pre_buffer=pre_buf, post_buffer=post_buf)
            merged = _merge_intervals(intervals)

            log("Created {} mute interval(s). Starting real-time monitor.".format(len(merged)))
            notify("{} word(s) will be muted.".format(len(matched)))

            # --- Start real-time mute monitoring ---
            self._mute_controller = MuteController(merged)
            self._start_mute_loop()
        finally:
            # Never leave profanity text on screen. Hide subtitles whenever
            # bad words were found (this realises the user's request: if
            # subtitles were already on by default, capture them, then hide
            # them) and whenever we had to force subtitles on ourselves.
            # If the user had subtitles on already and no bad words were
            # found, leave them exactly as they were.
            if matched or subs_forced:
                self._hide_subtitles()
                log("Subtitles hidden from display.")

    def _get_player_id(self, default=1):
        """
        Return the playerid of the active video player (or *default*).
        Hardcoding playerid 1 fails when other players (e.g. audio) are
        active, so we ask Kodi which player is currently playing video.
        """
        try:
            request = json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.GetActivePlayers",
                "id": 0
            })
            response = json.loads(xbmc.executeJSONRPC(request))
            for player in response.get("result", []):
                if player.get("type") == "video":
                    return player.get("playerid", default)
        except Exception as e:
            log("Could not resolve active player id: {}".format(str(e)))
        return default

    # ------------------------------------------------------------------
    # Subtitle acquisition strategies
    # ------------------------------------------------------------------

    def _try_get_subtitle_from_url(self):
        """
        Try to find the subtitle URL and download/parse it.
        Returns (list_of_cues, reason_str) — cues is None if not found.
        """
        url = self._find_subtitle_url()
        if not url:
            return None, "no URL found (JSON-RPC + log scan)"

        content = self._download_subtitle(url)
        if not content:
            return None, "URL found but download failed/empty: {}".format(url[:100])

        fmt = "vtt" if ".vtt" in url.lower() else "srt"
        cues = parse_subtitle_content(content, format_hint=fmt)
        if cues:
            return cues, "ok ({} cues from {})".format(len(cues), url[:60])
        return None, "URL content parsed to 0 cues: {}".format(url[:100])

    def _try_get_subtitle_from_file(self, video_path):
        """
        Try to find a local subtitle file and parse it.
        Returns (list_of_cues, reason_str) — cues is None if not found.
        """
        from subtitle_locator import find_subtitle_for_video
        subtitle_path = find_subtitle_for_video(video_path)
        if not subtitle_path:
            return None, "no subtitle file on disk"
        cues = parse_subtitle_file(subtitle_path)
        if cues:
            return cues, "ok ({} cues from {})".format(len(cues), subtitle_path)
        return None, "disk file parsed to 0 cues: {}".format(subtitle_path)

    def _find_subtitle_url(self):
        """
        Find the subtitle URL using multiple strategies:
        1. Check Kodi JSON-RPC for current subtitle info
        2. Parse the Kodi log file for the subtitle URL
        3. Fall back to a saved subtitle file on disk (Strategy B in caller)
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
            request = json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.GetProperties",
                "params": {
                    "playerid": self._get_player_id(),
                    "properties": ["currentsubtitle", "subtitles", "subtitleenabled"]
                },
                "id": 1
            })
            response = xbmc.executeJSONRPC(request)
            data = json.loads(response)
            result = data.get("result", {})

            if not isinstance(result, dict):
                log("JSON-RPC result is not a dict: {}".format(type(result).__name__))
                return ""

            subtitle_enabled = result.get("subtitleenabled", False)
            log("Subtitles enabled: {}".format(subtitle_enabled))

            if not subtitle_enabled:
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
                for i, sub in enumerate(subtitles):
                    if isinstance(sub, dict):
                        log("  Sub[{}]: name='{}' lang='{}'".format(
                            i, sub.get("name", ""), sub.get("language", "")))
                        # Check if any subtitle name contains a URL
                        sname = sub.get("name", "")
                        if "http://" in sname or "https://" in sname:
                            return sname

        except Exception as e:
            log("JSON-RPC subtitle check error: {}".format(str(e)))

        return ""

    def _find_subtitle_url_in_log(self):
        """
        Parse Kodi's log file to find the most recent subtitle URL.
        Kodi logs the subtitle URL when it opens it for streaming.
        This is the most reliable method for ororo.tv.
        """
        try:
            # Determine log file path
            log_path = xbmcvfs.translatePath("special://logpath/kodi.log")
            log("Looking for log at: {}".format(log_path))

            if not os.path.isfile(log_path):
                # Try with just the logpath directory
                log_dir = xbmcvfs.translatePath("special://logpath/")
                log("Log dir: {}".format(log_dir))
                # Try kodi.log in the directory
                log_path = os.path.join(log_dir, "kodi.log")
                if not os.path.isfile(log_path):
                    log("Cannot find kodi.log at: {}".format(log_path))
                    return ""

            log("Reading log file: {}".format(log_path))

            # Read the last portion of the log (last 300KB)
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)  # Seek to end
                file_size = f.tell()
                read_size = min(file_size, 300000)
                f.seek(max(0, file_size - read_size))
                log_content = f.read()

            # Look for subtitle URLs — ororo pattern and generic.
            # Capture the FULL URL including any signed query string (e.g.
            # "...vtt?X-Amz-Signature=..."), otherwise the download loses its
            # auth token and fails. We stop at whitespace, quotes or brackets.
            pattern = re.compile(
                r'(https?://[^\s"\'<>)\]]+?\.(?:vtt|srt|ass|ssa|sub)(?:[^\s"\'<>)\]]*))',
                re.IGNORECASE
            )
            matches = pattern.findall(log_content)

            if matches:
                # Return the last (most recent) match
                url = matches[-1].rstrip(">'\")")
                log("Found subtitle URL in log: {}".format(url[:150]))
                return url
            else:
                log("No subtitle URL found in log tail (last {}KB).".format(
                    read_size // 1024))

                # Fallback: scan the WHOLE log. The subtitle URL may have been
                # logged further back (e.g. after heavy activity).
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    whole = f.read()
                matches = pattern.findall(whole)
                if matches:
                    url = matches[-1].rstrip(">'\")")
                    log("Found subtitle URL in full-log scan: {}".format(url[:150]))
                    return url
                log("No subtitle URL found in full log either.")

        except Exception as e:
            log("Error reading log for subtitle URL: {}".format(str(e)))

        return ""

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
                    log("xbmcvfs returned {} bytes — trying urllib.".format(
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
    # Subtitle visibility control
    # ------------------------------------------------------------------

    def _subtitles_enabled(self):
        """Return True if the active video player currently has subtitles on."""
        try:
            request = json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.GetProperties",
                "params": {
                    "playerid": self._get_player_id(),
                    "properties": ["subtitleenabled"]
                },
                "id": 1
            })
            data = json.loads(xbmc.executeJSONRPC(request))
            result = data.get("result", {})
            if isinstance(result, dict):
                return bool(result.get("subtitleenabled", False))
        except Exception as e:
            log("Could not read subtitle state: {}".format(str(e)))
        return False

    def _force_enable_subtitles(self):
        """
        Force-enable subtitles in the player so Kodi downloads/streams them.
        This ensures the add-on can parse the subtitle data even if the user
        had subtitles turned off.
        """
        try:
            # First check if subtitles are already enabled
            request = json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.GetProperties",
                "params": {
                    "playerid": self._get_player_id(),
                    "properties": ["subtitleenabled", "currentsubtitle", "subtitles"]
                },
                "id": 1
            })
            response = xbmc.executeJSONRPC(request)
            data = json.loads(response)
            result = data.get("result", {})

            if isinstance(result, dict) and result.get("subtitleenabled", False):
                log("Subtitles already enabled.")
                return

            # Enable subtitles — try to select the first available subtitle
            # Use Player.SetSubtitle with "on" to enable current subtitle
            request2 = json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.SetSubtitle",
                "params": {
                    "playerid": self._get_player_id(),
                    "subtitle": "on"
                },
                "id": 2
            })
            xbmc.executeJSONRPC(request2)
            log("Forced subtitles ON via JSON-RPC.")

            # Wait a moment and verify
            time.sleep(1)

            # If still no subtitle, try setting index 0 explicitly
            response3 = xbmc.executeJSONRPC(request)
            data3 = json.loads(response3)
            result3 = data3.get("result", {})
            if isinstance(result3, dict) and not result3.get("subtitleenabled", False):
                # Try enabling with explicit index
                subtitles = result3.get("subtitles", [])
                if isinstance(subtitles, list) and len(subtitles) > 0:
                    request4 = json.dumps({
                        "jsonrpc": "2.0",
                        "method": "Player.SetSubtitle",
                        "params": {
                            "playerid": self._get_player_id(),
                            "subtitle": 0,
                            "enable": True
                        },
                        "id": 3
                    })
                    xbmc.executeJSONRPC(request4)
                    log("Forced subtitle index 0 ON.")
                else:
                    log("No subtitle streams available yet to enable.")

        except Exception as e:
            log("Error forcing subtitles on: {}".format(str(e)))

    def _hide_subtitles(self):
        """
        Hide subtitle display without fully disabling the subtitle stream.
        Uses Player.SetSubtitle with "off" to stop rendering subtitles
        on screen. The subtitle data has already been parsed so we no
        longer need it visible.
        """
        try:
            request = json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.SetSubtitle",
                "params": {
                    "playerid": self._get_player_id(),
                    "subtitle": "off"
                },
                "id": 10
            })
            xbmc.executeJSONRPC(request)
            log("Subtitle display turned OFF.")
        except Exception as e:
            log("Error hiding subtitles: {}".format(str(e)))

    # ------------------------------------------------------------------
    # Mute loop
    # ------------------------------------------------------------------

    def _start_mute_loop(self):
        """Start the real-time mute polling loop in a background thread."""
        self._mute_thread = threading.Thread(target=self._mute_loop)
        self._mute_thread.daemon = True
        self._mute_thread.start()

    def _mute_loop(self):
        """
        Poll the playback position and mute/unmute as needed.
        Runs until playback stops or the stop event is set.
        """
        controller = self._mute_controller
        if not controller:
            return

        log("Mute loop started ({} intervals).".format(controller.interval_count))

        while not self._stop_muting.is_set() and not self._monitor.abortRequested():
            try:
                if not self.isPlaying():
                    break
                current_time = self.getTime()
                controller.update(current_time)
            except RuntimeError:
                break

            time.sleep(POLL_INTERVAL)

        controller.cleanup()
        log("Mute loop ended.")

    # ------------------------------------------------------------------
    # Scene-skip loop
    # ------------------------------------------------------------------

    def _start_skip_loop(self):
        """Start the scene-skip polling loop in a background thread."""
        if not self._skip_controller:
            return
        self._skip_thread = threading.Thread(target=self._skip_loop)
        self._skip_thread.daemon = True
        self._skip_thread.start()

    def _skip_loop(self):
        """
        Poll the playback position and seek past flagged scenes.
        Runs until playback stops or the stop event is set.
        """
        controller = self._skip_controller
        if not controller:
            return

        log("Scene-skip loop started ({} scenes).".format(controller.count))

        while not self._stop_muting.is_set() and not self._monitor.abortRequested():
            try:
                if not self.isPlaying():
                    break
                current_time = self.getTime()
                controller.update(current_time)
            except RuntimeError:
                break

            time.sleep(POLL_INTERVAL)

        log("Scene-skip loop ended.")

    def _load_scene_skip(self, video_path):
        """
        Load the scene-skip list for *video_path* and build a controller.
        Returns True if skipping is active for this video.
        """
        if not _get_setting_bool("enable_scene_skip", False):
            return False

        skip_file = find_skip_file(video_path)
        if not skip_file:
            log("No scene-skip list found for this video.")
            return False

        intervals = parse_skip_file(skip_file)
        if not intervals:
            log("Scene-skip list is empty: {}".format(skip_file))
            return False

        # Merge overlapping/adjacent windows once.
        merged = _merge_intervals(intervals)

        lookahead = _get_setting_float("skip_lookahead", 10.0)
        self._skip_controller = SceneSkipController(self, merged, lookahead=lookahead)
        log("Loaded {} scene window(s) from {}.".format(len(merged), skip_file))
        notify("{} scene(s) will be skipped.".format(len(merged)))
        return True

    def _get_video_path(self):
        """Return the path/URL of the currently playing item."""
        try:
            return self.getPlayingFile()
        except RuntimeError:
            return ""


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
