"""
subtitle_locator.py
-------------------
Locates a local subtitle file for the currently playing video.

This module only handles LOCAL file discovery. Streaming subtitle URL
detection is handled by service.py directly.

Strategy (in order of preference):
  1. Look for a sidecar subtitle file next to the video (same base name).
  2. Check Kodi's temp folder for recently modified subtitle files.
  3. Scan the Kodi userdata/addon_data folder for subtitle downloads.
"""

import os
import glob
import time
from typing import Optional

try:
    import xbmc
    import xbmcvfs
    _IN_KODI = True
except ImportError:
    _IN_KODI = False


def _translate_path(path):
    """Use xbmcvfs.translatePath (Kodi 19+) with fallback."""
    if not _IN_KODI:
        return path
    return xbmcvfs.translatePath(path)


def _log(msg):
    """Log a message to Kodi's log."""
    if _IN_KODI:
        xbmc.log("[ProfanityFilter] " + msg, xbmc.LOGINFO)


# Subtitle extensions to search for
SUBTITLE_EXTENSIONS = [".srt", ".vtt", ".sub", ".ass", ".ssa"]

# How recently (seconds) a temp file must have been modified
TEMP_FILE_MAX_AGE = 300  # 5 minutes


def find_subtitle_for_video(video_path, max_age=None):
    # type: (str, Optional[int]) -> Optional[str]
    """
    Return the path to the best local subtitle file for *video_path*, or None.
    """
    age_limit = max_age if max_age is not None else TEMP_FILE_MAX_AGE

    # --- 1. Sidecar file next to the video (local files only) ---
    if not video_path.startswith(("http://", "https://", "plugin://")):
        sidecar = _find_sidecar(video_path)
        if sidecar:
            _log("Found sidecar subtitle: {}".format(sidecar))
            return sidecar

    # --- 2. Kodi temp/cache folder ---
    temp_sub = _find_in_temp_folder(age_limit)
    if temp_sub:
        _log("Found subtitle in temp: {}".format(temp_sub))
        return temp_sub

    # --- 3. Kodi subtitles folder ---
    sub_folder = _find_in_subtitle_folder(age_limit)
    if sub_folder:
        _log("Found subtitle in subtitles folder: {}".format(sub_folder))
        return sub_folder

    # --- 4. Addon data directories ---
    addon_sub = _find_in_addon_data(age_limit)
    if addon_sub:
        _log("Found subtitle in addon_data: {}".format(addon_sub))
        return addon_sub

    return None


def _find_sidecar(video_path):
    # type: (str) -> Optional[str]
    """Look for a subtitle file with the same base name as the video."""
    base, _ = os.path.splitext(video_path)
    for ext in SUBTITLE_EXTENSIONS:
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
        upper_candidate = base + ext.upper()
        if os.path.isfile(upper_candidate):
            return upper_candidate
    return None


def _find_in_temp_folder(max_age):
    # type: (int) -> Optional[str]
    """Search Kodi's temp folder for a recently written subtitle file."""
    if not _IN_KODI:
        return None
    temp_dir = _translate_path("special://temp/")
    return _scan_directory_for_subtitles(temp_dir, max_age)


def _find_in_subtitle_folder(max_age):
    # type: (int) -> Optional[str]
    """Search the user-configured Kodi subtitles download folder."""
    if not _IN_KODI:
        return None
    sub_dir = _translate_path("special://subtitles/")
    if os.path.isdir(sub_dir):
        return _scan_directory_for_subtitles(sub_dir, max_age)
    return None


def _find_in_addon_data(max_age):
    # type: (int) -> Optional[str]
    """Search addon_data directories for subtitle files."""
    if not _IN_KODI:
        return None
    addon_data_dir = _translate_path("special://profile/addon_data/")
    if not os.path.isdir(addon_data_dir):
        return None
    now = time.time()
    candidates = []
    for addon_dir in os.listdir(addon_data_dir):
        full_addon_dir = os.path.join(addon_data_dir, addon_dir)
        if not os.path.isdir(full_addon_dir):
            continue
        for ext in SUBTITLE_EXTENSIONS:
            pattern = os.path.join(full_addon_dir, "**", "*" + ext)
            for path in glob.glob(pattern, recursive=True):
                try:
                    mtime = os.path.getmtime(path)
                    age = now - mtime
                    if age <= max_age:
                        candidates.append((mtime, path))
                except OSError:
                    pass
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def _scan_directory_for_subtitles(directory, max_age):
    # type: (str, int) -> Optional[str]
    """
    Scan a directory for subtitle files modified within max_age seconds.
    Returns the most recently modified subtitle file, or None.
    """
    if not os.path.isdir(directory):
        return None
    now = time.time()
    candidates = []
    for ext in SUBTITLE_EXTENSIONS:
        # Search root level
        pattern = os.path.join(directory, "*" + ext)
        for path in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(path)
                if now - mtime <= max_age:
                    candidates.append((mtime, path))
            except OSError:
                pass
        # Search one level deep
        pattern2 = os.path.join(directory, "*", "*" + ext)
        for path in glob.glob(pattern2):
            try:
                mtime = os.path.getmtime(path)
                if now - mtime <= max_age:
                    candidates.append((mtime, path))
            except OSError:
                pass
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None
