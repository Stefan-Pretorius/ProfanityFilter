"""
Regression tests for the Amazon VOD subtitle discovery helpers.

These are pure-Python tests (no Kodi needed), so they run on any interpreter:

    python -m unittest discover -s tests
    # or simply
    python tests/test_amazon_vod.py

They are not part of the shipped add-on; see tools/make_release.py, which
zips only the service.profanity.filter directory.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "service.profanity.filter", "resources", "lib")
sys.path.insert(0, os.path.abspath(LIB))

from amazon_vod import (  # noqa: E402
    parse_proxy_address,
    parse_subtitle_requests,
    language_of,
    is_forced,
    choose_subtitle,
    build_subtitle_url,
    is_proxied_path,
)


# A slice of a real kodi.log recorded while playing a Prime Video title. The
# add-on's proxy logs the request path as a Python list of segments, which is
# exactly what the old "http...\.srt" log grep could not cope with.
REAL_LOG = (
    "2026-10-15 18:31:24.405 T:17476  info <general>: [Amazon VOD] "
    "proxy.py:68 [PS] Requested GET path ['subtitles', "
    "'https%3A%2F%2Fcf-timedtext.aux.pv-cdn.net%2F339f%2Fcf85%2Ff277%2F4ef5"
    "-9e9e-a3e364dbcaff%2Ffafc79d4-dd25-49ea-95c8-50f7376d3cdf.ttml2', "
    "'da.srt']\n"
    "2026-10-15 18:33:02.100 T:17476  info <general>: [Amazon VOD] "
    "proxy.py:68 [PS] Requested GET path ['subtitles', "
    "'https%3A%2F%2Fcf-timedtext.aux.pv-cdn.net%2Faaa%2Fbbb%2Fccc%2Fddd.ttml2', "
    "'en-[CC].srt']\n"
)


class ProxyAddressTest(unittest.TestCase):
    def test_reads_host_and_port(self):
        self.assertEqual(parse_proxy_address("127.0.0.1:61049"), "127.0.0.1:61049")

    def test_tolerates_surrounding_whitespace(self):
        self.assertEqual(parse_proxy_address("  127.0.0.1:61049\n"), "127.0.0.1:61049")

    def test_rejects_junk(self):
        for junk in ("", None, "not-an-address", "http://127.0.0.1:61049"):
            self.assertEqual(parse_proxy_address(junk), "")


class ParseRequestsTest(unittest.TestCase):
    def test_finds_both_subtitle_requests(self):
        requests = parse_subtitle_requests(REAL_LOG)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["filename"], "da.srt")
        self.assertEqual(requests[1]["filename"], "en-[CC].srt")

    def test_keeps_the_escaped_upstream_url(self):
        requests = parse_subtitle_requests(REAL_LOG)
        self.assertTrue(requests[0]["escaped"].startswith("https%3A%2F%2F"))
        self.assertTrue(requests[0]["escaped"].endswith(".ttml2"))

    def test_ignores_other_proxy_traffic(self):
        log = ("[PS] Requested GET path ['mpd', "
               "'https%3A%2F%2Fa139vod-dash.akamaized.net%2Fmovie.mpd']\n"
               "[PS] Requested POST path ['gpr', 'https%3A%2F%2Fatv-ps-fe']\n")
        self.assertEqual(parse_subtitle_requests(log), [])

    def test_handles_empty_input(self):
        self.assertEqual(parse_subtitle_requests(""), [])
        self.assertEqual(parse_subtitle_requests(None), [])


class LanguageTest(unittest.TestCase):
    def test_plain_codes(self):
        self.assertEqual(language_of("da.srt"), "da")
        self.assertEqual(language_of("en.srt"), "en")

    def test_sdh_and_forced_suffixes_are_stripped(self):
        self.assertEqual(language_of("en-[CC].srt"), "en")
        self.assertEqual(language_of("en.Forced.srt"), "en")
        self.assertEqual(language_of("en-[CC].Forced.srt"), "en")

    def test_regional_variants_fold_to_base(self):
        self.assertEqual(language_of("fr-Canada.srt"), "fr")

    def test_forced_detection(self):
        self.assertTrue(is_forced("en-[CC].Forced.srt"))
        self.assertFalse(is_forced("en-[CC].srt"))


class ChooseSubtitleTest(unittest.TestCase):
    def _request(self, filename):
        return {"escaped": "X", "filename": filename}

    def test_prefers_english_over_whatever_came_first(self):
        requests = [self._request("da.srt"), self._request("en-[CC].srt")]
        self.assertEqual(choose_subtitle(requests)["filename"], "en-[CC].srt")

    def test_newest_english_wins(self):
        requests = [self._request("en.srt"), self._request("en-[CC].srt")]
        self.assertEqual(choose_subtitle(requests)["filename"], "en-[CC].srt")

    def test_prefers_non_forced(self):
        requests = [self._request("en.Forced.srt"), self._request("en.srt")]
        self.assertEqual(choose_subtitle(requests)["filename"], "en.srt")

    def test_falls_back_to_any_language_when_no_preferred_one_exists(self):
        requests = [self._request("da.srt"), self._request("fr.srt")]
        self.assertEqual(choose_subtitle(requests)["filename"], "fr.srt")

    def test_nothing_to_choose(self):
        self.assertIsNone(choose_subtitle([]))


class BuildUrlTest(unittest.TestCase):
    def test_builds_the_proxy_url(self):
        url = build_subtitle_url("127.0.0.1:61049", "https%3A%2F%2Ffoo.ttml2",
                                 "en-[CC].srt")
        self.assertEqual(
            url,
            "http://127.0.0.1:61049/subtitles/https%3A%2F%2Ffoo.ttml2/en-[CC].srt")

    def test_end_to_end_from_the_recorded_log(self):
        requests = parse_subtitle_requests(REAL_LOG)
        chosen = choose_subtitle(requests)
        url = build_subtitle_url("127.0.0.1:61049", chosen["escaped"],
                                 chosen["filename"])
        self.assertTrue(url.startswith("http://127.0.0.1:61049/subtitles/"))
        self.assertTrue(url.endswith("/en-[CC].srt"))


class ProxiedPathTest(unittest.TestCase):
    def test_matches_the_proxied_mpd(self):
        path = ("http://127.0.0.1:61049/mpd/"
                "https%3A%2F%2Fa139vod-dash.akamaized.net%2Fmovie.mpd")
        self.assertTrue(is_proxied_path(path, "127.0.0.1:61049"))

    def test_matches_a_plugin_url_for_the_addon(self):
        self.assertTrue(is_proxied_path(
            "plugin://plugin.video.amazon-test/?mode=PlayVideo", "127.0.0.1:61049"))

    def test_rejects_other_sources(self):
        self.assertFalse(is_proxied_path("http://127.0.0.1:8080/other.mpd",
                                        "127.0.0.1:61049"))
        self.assertFalse(is_proxied_path(
            "plugin://plugin.video.ororotv/?mode=play", "127.0.0.1:61049"))
        self.assertFalse(is_proxied_path("/movies/local.mkv", "127.0.0.1:61049"))
        self.assertFalse(is_proxied_path("", "127.0.0.1:61049"))
        self.assertFalse(is_proxied_path("http://127.0.0.1:61049/x", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
