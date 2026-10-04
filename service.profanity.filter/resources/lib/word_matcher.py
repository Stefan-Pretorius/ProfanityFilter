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


# What may sit between the words of a multi-word entry. Subtitles punctuate
# exclamations ("Oh, God", "What the hell!"), so the entry "oh god" has to
# match that. No word characters are allowed here, which is what stops
# "to hell" from matching "to me about hell".
_WORD_GAP = "[\\s,.;:!?'\"()\\-\\[\\]\\u2013\\u2014\\u2026]*\\s+"


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
      - The words of a multi-word entry may be separated by punctuation as
        well as spaces, because subtitles punctuate exclamations: "Oh, God"
        must still be matched by the entry "oh god", and "What the hell!"
        by "what the hell". The separator class contains no word characters,
        so "to hell" still cannot match "to me about hell".
      - All other regex metacharacters are escaped.
    """
    # Escape everything, then un-escape our wildcard placeholder
    escaped = re.escape(pattern).replace(r"\*", ".?")
    # re.escape renders a space as "\ " - widen just that to allow punctuation.
    escaped = escaped.replace("\\ ", _WORD_GAP)
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
