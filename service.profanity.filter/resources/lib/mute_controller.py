"""
mute_controller.py
------------------
Real-time audio mute controller for the Kodi Profanity Filter.

Instead of relying on EDL files (which only work for local files),
this module monitors the playback position in real-time and mutes/unmutes
the audio when the current time enters or exits a "bad word" window.

This approach works with ALL content types:
  - Local files
  - Streaming URLs (http://, https://)
  - Plugin streams (plugin://) — including ororo.tv
"""

import bisect

try:
    import xbmc
    _IN_KODI = True
except ImportError:
    _IN_KODI = False


class MuteController(object):
    """
    Manages real-time muting based on a list of mute intervals.

    Usage:
        controller = MuteController(intervals)
        # In a polling loop:
        controller.update(current_time_seconds)
        # When playback stops:
        controller.cleanup()
    """

    def __init__(self, intervals):
        # type: (list) -> None
        """
        Parameters
        ----------
        intervals : list of (float, float)
            Sorted, merged list of (start, end) time intervals in seconds
            during which audio should be muted.
        """
        self._intervals = intervals
        self._is_muted_by_us = False
        # Pre-compute start times for fast binary search
        self._starts = [iv[0] for iv in intervals]
        self._ends = [iv[1] for iv in intervals]

    @property
    def interval_count(self):
        # type: () -> int
        return len(self._intervals)

    def should_mute(self, current_time):
        # type: (float) -> bool
        """
        Determine if the audio should be muted at *current_time*.

        Uses binary search for O(log n) performance even with many intervals.
        """
        # Find the rightmost interval whose start <= current_time
        idx = bisect.bisect_right(self._starts, current_time) - 1
        if idx < 0:
            return False
        # Check if current_time is within this interval
        return current_time <= self._ends[idx]

    def update(self, current_time):
        # type: (float) -> None
        """
        Call this every polling cycle with the current playback time.
        Will mute or unmute as needed.
        """
        if not _IN_KODI:
            return

        want_muted = self.should_mute(current_time)

        if want_muted and not self._is_muted_by_us:
            self._mute()
        elif not want_muted and self._is_muted_by_us:
            self._unmute()

    def cleanup(self):
        # type: () -> None
        """Ensure audio is unmuted when playback stops or add-on exits."""
        if self._is_muted_by_us:
            self._unmute()

    def _mute(self):
        # type: () -> None
        """Mute the audio via Kodi JSON-RPC."""
        import json
        # Only mute if not already muted by the user
        if not self._is_system_muted():
            xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0",
                "method": "Application.SetMute",
                "params": {"mute": True},
                "id": 1
            }))
        self._is_muted_by_us = True

    def _unmute(self):
        # type: () -> None
        """Unmute the audio via Kodi JSON-RPC."""
        import json
        xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0",
            "method": "Application.SetMute",
            "params": {"mute": False},
            "id": 1
        }))
        self._is_muted_by_us = False

    def _is_system_muted(self):
        # type: () -> bool
        """Check if Kodi is already muted (e.g., by the user)."""
        import json
        response_raw = xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0",
            "method": "Application.GetProperties",
            "params": {"properties": ["muted"]},
            "id": 1
        }))
        try:
            response = json.loads(response_raw)
            return response.get("result", {}).get("muted", False)
        except (ValueError, KeyError):
            return False
