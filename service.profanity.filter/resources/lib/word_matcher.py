"""
word_matcher.py
---------------
Loads the bad-word list and matches it against subtitle cues.

The filter list supports:
  - Exact words:        "hell"
  - Wildcard patterns:  "sh*t"  (the * matches any characters)
  - Case-insensitive matching throughout
"""

import re
import os


def load_word_list(filepath):
    # type: (str) -> list
    """
    Read the bad-word list from *filepath*.

    Each non-empty, non-comment line is treated as one entry.
    Lines starting with '#' are treated as comments and ignored.

    Returns a list of lowercase word/pattern strings.
    """
    words = []
    if not os.path.isfile(filepath):
        return words

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                word = line.strip().lstrip("\ufeff")
                if word and not word.startswith("#"):
                    words.append(word.lower())
    except OSError:
        pass

    return words


def _pattern_to_regex(pattern):
    # type: (str) -> re.Pattern
    """
    Convert a word-list entry to a compiled regex.

    Rules:
      - The match must be a standalone token, not part of a longer word,
        so "ass" won't match "class" or "badass". This is enforced with
        word-character lookarounds rather than \\b so that patterns which
        start/end with punctuation (e.g. "@$$") also work correctly.
      - '*' in the pattern is treated as a wildcard for a SINGLE masked
        character (e.g. "sh*t" matches "shit", "shut", "shat" but NOT
        "shift", "sheet" or "shout"). This deliberately avoids the greedy
        match-anything behaviour that caused innocent words to be muted.
      - All other regex metacharacters are escaped.
    """
    # Escape everything, then un-escape our wildcard placeholder
    escaped = re.escape(pattern).replace(r"\*", ".?")
    return re.compile(r"(?<!\w)" + escaped + r"(?!\w)", re.IGNORECASE)


def build_patterns(word_list):
    # type: (list) -> list
    """
    Compile a list of regex patterns from the word list.

    Returns a list of compiled re.Pattern objects.
    """
    return [_pattern_to_regex(w) for w in word_list]


def find_matching_cues(cues, patterns):
    # type: (list, list) -> list
    """
    Scan *cues* for any subtitle line that contains at least one bad word.

    Parameters
    ----------
    cues : list
        Output of subtitle_parser.parse_subtitle_file().
    patterns : list
        Output of build_patterns().

    Returns
    -------
    list of cue dicts where at least one pattern matched.
    """
    matched = []
    for cue in cues:
        text = cue.get("text", "")
        for pattern in patterns:
            if pattern.search(text):
                matched.append(cue)
                break  # No need to check further patterns for this cue
    return matched
