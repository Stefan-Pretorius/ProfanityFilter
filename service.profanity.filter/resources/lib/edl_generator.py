"""
edl_generator.py
----------------
Generates a Kodi-compatible EDL (Edit Decision List) file from a list
of subtitle cues that contain bad words.

EDL mute action format (MPlayer/Kodi):
    <start_seconds> <end_seconds> 1

The '1' denotes a MUTE action. Kodi will silence the audio between
start_seconds and end_seconds while continuing to play the video.

Reference: https://kodi.wiki/view/Edit_decision_list
"""

import os

# EDL action codes
ACTION_MUTE = 1


def generate_edl(matched_cues, output_path, pre_buffer=0.3, post_buffer=0.3):
    # type: (list, str, float, float) -> bool
    """
    Write an EDL file to *output_path* based on *matched_cues*.

    Parameters
    ----------
    matched_cues : list
        Cue dicts (each with 'start' and 'end' keys in seconds) that
        contain at least one bad word.
    output_path : str
        Full path where the .edl file should be written.
    pre_buffer : float
        Seconds to extend the mute window *before* the subtitle start.
        Compensates for words spoken slightly before the subtitle appears.
    post_buffer : float
        Seconds to extend the mute window *after* the subtitle end.

    Returns
    -------
    bool  True if the file was written successfully, False otherwise.
    """
    if not matched_cues:
        # Remove a stale EDL file if no bad words were found
        _remove_edl(output_path)
        return False

    # Merge overlapping/adjacent mute windows to avoid duplicate entries
    intervals = _build_intervals(matched_cues, pre_buffer=pre_buffer, post_buffer=post_buffer)
    merged = _merge_intervals(intervals)

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            for start, end in merged:
                # Clamp start to 0 to avoid negative timestamps
                start = max(0.0, start)
                fh.write("{:.3f}\t{:.3f}\t{}\n".format(start, end, ACTION_MUTE))
        return True
    except OSError:
        return False


def get_edl_path(video_path):
    # type: (str) -> str
    """
    Derive the EDL file path from the video file path.

    Kodi looks for  <video_basename>.edl  in the same directory as
    the video file.  For streaming URLs (no local path), a temp
    directory is used instead.

    Parameters
    ----------
    video_path : str
        The path or URL of the currently playing video.

    Returns
    -------
    str  Full path to the corresponding .edl file.
    """
    import xbmcvfs  # Available only inside Kodi runtime

    # Strip query strings from URLs
    clean_path = video_path.split("?")[0].split("|")[0]

    if clean_path.startswith(("http://", "https://", "plugin://")):
        # Streaming: write EDL to Kodi's temp/profile directory
        temp_dir = xbmcvfs.translatePath("special://temp/profanity_filter/")
        if not os.path.isdir(temp_dir):
            os.makedirs(temp_dir)
        # Use a stable filename derived from the URL
        import hashlib
        url_hash = hashlib.md5(video_path.encode("utf-8")).hexdigest()
        return os.path.join(temp_dir, url_hash + ".edl")
    else:
        # Local file: place .edl alongside the video
        base, _ = os.path.splitext(clean_path)
        return base + ".edl"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_intervals(cues, pre_buffer=0.3, post_buffer=0.3):
    # type: (list, float, float) -> list
    """Return a list of (start, end) tuples with buffers applied."""
    return [(cue["start"] - pre_buffer, cue["end"] + post_buffer) for cue in cues]


def _merge_intervals(intervals):
    # type: (list) -> list
    """Merge overlapping or adjacent intervals."""
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            # Overlapping or touching — extend the previous interval
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _remove_edl(path):
    # type: (str) -> None
    """Silently remove an EDL file if it exists."""
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
