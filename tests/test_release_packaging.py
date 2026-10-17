"""
Tests for the release packaging (tools/make_release.py).

These run the real build into a temporary directory and check the result
against the rules Kodi itself applies when it installs from a repository:

  * the index at <datadir>/addons.xml must match <datadir>/addons.xml.md5
    byte for byte (Kodi hashes the downloaded body, so a CRLF difference is
    a hard failure, not a cosmetic one),
  * each listed add-on's zip must be at
    <datadir>/<addon id>/<addon id>-<version>.zip

That second rule is the one that has bitten this project before: the build
used to publish zips under <addon id>/<version>/, which Kodi never requests,
so "Install from repository" silently could not find anything.

Pure Python, no Kodi needed:

    python -m unittest discover -s tests
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import make_release  # noqa: E402


def read_addon_xml(addon_dir):
    with open(os.path.join(ROOT, addon_dir, "addon.xml"), "r", encoding="utf-8") as fh:
        return fh.read()


SERVICE_XML = read_addon_xml("service.profanity.filter")
REPO_XML = read_addon_xml("repository.profanityfilter")
SERVICE_ID, SERVICE_VERSION = make_release.parse_addon_meta(SERVICE_XML)
REPO_ID, REPO_VERSION = make_release.parse_addon_meta(REPO_XML)

BUNDLED_ZIPS = [os.path.basename(p) for p in make_release.BUNDLED_ADDONS]

AMAZON_VOD_ID = "plugin.video.amazon-test"

# Provided by Kodi itself, so published nowhere. Kodi bundles both of these
# with the application on every platform: script.module.pil is a deliberate
# placeholder in Kodi's own source tree (xbmc/addons/script.module.pil holds an
# addon.xml and an icon and no code at all), which is why it appears in no Kodi
# add-on index even though amazoncaptcha declares a dependency on it.
FROM_KODI_ITSELF = {
    "xbmc.addon",       # the add-on manager itself, virtual, always present
    "xbmc.python",
    "script.module.pil",
}

# Deliberately not mirrored. plugin.video.ororotv supplies the login, the My
# Shows lists and the playback for Ororo TV Browse, and is published by ororo
# itself; this repository has no business redistributing it.
EXTERNAL = {
    "plugin.video.ororotv",
}


def addon_version_key(version):
    """
    Order two add-on versions the way Kodi orders them.

    Kodi splits a version on '.' and compares the parts numerically, with '~'
    marking a pre-release (sorts before the bare version) and a '+' suffix
    sorting after it - which is why "1.3.2+matrix.1" satisfies a requirement of
    "1.3.1+matrix.1" while a bare "1.3.1" would not.
    """
    base, marker, _suffix = version.partition("~")
    if not marker:
        base, marker, _suffix = version.partition("+")
    parts = []
    for chunk in base.split("."):
        digits = "".join(character for character in chunk if character.isdigit())
        parts.append(int(digits) if digits else 0)
    # "~" (pre-release) < "" (release) < "+" (suffix)
    rank = {"~": 0, "": 1, "+": 2}.get(marker, 1)
    return tuple(parts), rank


class BuildTests(unittest.TestCase):
    """One real build, shared by the whole class (it writes ~a few hundred KB)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="profanity-release-")
        cls.dist = os.path.join(cls.tmp, "dist")
        cls.pages = os.path.join(cls.dist, "gh-pages")
        cls._saved = (make_release.DIST, make_release.PAGES)
        make_release.DIST = cls.dist
        make_release.PAGES = cls.pages
        make_release.main()

    @classmethod
    def tearDownClass(cls):
        make_release.DIST, make_release.PAGES = cls._saved
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- helpers ---------------------------------------------------------

    def index_ids(self):
        tree = ET.parse(os.path.join(self.pages, "addons.xml"))
        self.assertEqual(tree.getroot().tag, "addons")
        return sorted(a.get("id") for a in tree.getroot().findall("addon"))

    def index_entries(self):
        """Every (id, version) Kodi is told it can install."""
        tree = ET.parse(os.path.join(self.pages, "addons.xml"))
        return [(a.get("id"), a.get("version"))
                for a in tree.getroot().findall("addon")]

    def index_versions(self):
        tree = ET.parse(os.path.join(self.pages, "addons.xml"))
        return {a.get("id"): a.get("version")
                for a in tree.getroot().findall("addon")}

    # -- release assets --------------------------------------------------

    def test_release_assets_are_built(self):
        for name in ("{0}-{1}.zip".format(SERVICE_ID, SERVICE_VERSION),
                     "{0}-{1}.zip".format(REPO_ID, REPO_VERSION)):
            self.assertTrue(os.path.isfile(os.path.join(self.dist, name)),
                            "{} is missing from dist/ (would not become a release asset)".format(name))

    def test_bundled_addons_are_release_assets(self):
        for name in BUNDLED_ZIPS:
            self.assertTrue(os.path.isfile(os.path.join(self.dist, name)),
                            "{} is missing from dist/".format(name))

    def test_every_asset_is_a_readable_zip_with_its_addon_xml(self):
        for name in os.listdir(self.dist):
            if not name.endswith(".zip"):
                continue
            path = os.path.join(self.dist, name)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip(), "{} is corrupt".format(name))
                addon_xmls = [n for n in archive.namelist()
                              if os.path.basename(n) == "addon.xml"]
                self.assertTrue(addon_xmls, "{} has no addon.xml".format(name))

    def test_service_zip_contains_the_real_addon(self):
        path = os.path.join(self.dist, "{0}-{1}.zip".format(SERVICE_ID, SERVICE_VERSION))
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            self.assertIn("{0}/service.py".format(SERVICE_ID), names)
            self.assertIn("{0}/resources/filter.txt".format(SERVICE_ID), names)
            content = archive.read("{0}/addon.xml".format(SERVICE_ID)).decode("utf-8")
        self.assertEqual(make_release.parse_addon_meta(content),
                         (SERVICE_ID, SERVICE_VERSION))

    def test_asset_filenames_match_the_version_declared_inside_them(self):
        # A filename built from the wrong source (e.g. the XML declaration's
        # version) would publish an add-on whose name Kodi never asks for.
        for name in os.listdir(self.dist):
            if not name.endswith(".zip"):
                continue
            addon_id = name[:name.rindex("-")]
            with zipfile.ZipFile(os.path.join(self.dist, name)) as archive:
                content = archive.read(
                    "{0}/addon.xml".format(addon_id)).decode("utf-8")
            meta_id, meta_version = make_release.parse_addon_meta(content)
            self.assertEqual("{0}-{1}.zip".format(meta_id, meta_version), name)

    # -- the index -------------------------------------------------------

    def test_index_lists_every_addon_we_advertise(self):
        ids = self.index_ids()
        self.assertIn(SERVICE_ID, ids)
        self.assertIn(REPO_ID, ids)
        # Amazon VOD's repository, so a box can also track it upstream.
        self.assertIn("repository.sandmann79.plugins", ids)
        # Our own browse add-on, developed in its own repository.
        self.assertIn("plugin.video.ororotv.browse", ids)

    def test_amazon_vod_installs_from_this_repository_alone(self):
        # Regression test for the reported failure: the repository carried only
        # a pointer to Sandmann79's repository add-on, which has to fetch a
        # second index from raw.githubusercontent.com. When that nested fetch
        # does not happen the nested repository looks empty and Amazon VOD
        # never appears, so Prime Video cannot be installed from here at all.
        # Amazon VOD and its private modules must therefore be published here.
        ids = self.index_ids()
        self.assertIn(AMAZON_VOD_ID, ids)
        for module in ("script.module.amazoncaptcha",
                       "script.module.mechanicalsoup",
                       "script.module.pyautogui"):
            self.assertIn(module, ids)

    def published_requires(self, addon_id, versions=None):
        """
        (requirement id, required version, optional) for one published add-on.

        Read out of the zip this repository actually serves, not out of a
        source tree, because that zip is what Kodi inspects.
        """
        versions = versions or self.index_versions()
        path = os.path.join(self.pages, addon_id,
                            "{0}-{1}.zip".format(addon_id, versions[addon_id]))
        with zipfile.ZipFile(path) as archive:
            content = archive.read(
                "{0}/addon.xml".format(addon_id)).decode("utf-8")
        requires = ET.fromstring(content).find("requires")
        if requires is None:
            return []
        return [(node.get("addon"), node.get("version"), node.get("optional"))
                for node in requires]

    def test_every_amazon_vod_requirement_is_resolvable(self):
        # Catches the real risk of mirroring: an upstream Amazon VOD that grows
        # a dependency on some further module that we have not vendored.
        # Installing it would then fail with an unmet dependency.
        versions = self.index_versions()
        self.assertIn(
            AMAZON_VOD_ID, versions,
            "{} is not in the index, so it cannot be installed from this "
            "repository".format(AMAZON_VOD_ID))

        published = set(versions)
        for requirement, _version, _optional in self.published_requires(AMAZON_VOD_ID, versions):
            self.assertTrue(
                requirement in published or requirement in FROM_KODI_ITSELF,
                "{} requires {}, which is neither published here nor supplied "
                "by Kodi itself - vendor it in thirdparty/ (see "
                "tools/vendor_kodi.py)".format(AMAZON_VOD_ID, requirement))

    def test_the_whole_dependency_tree_is_served_from_here(self):
        # The point of mirroring the official modules: a box that can reach
        # stefan-pretorius.github.io and has Kodi installed needs no other host
        # to install Amazon VOD. Anything neither published here nor bundled by
        # Kodi must be listed in EXTERNAL with a reason, or the install fails
        # with the unmet-dependency error this test exists to prevent.
        versions = self.index_versions()
        published = set(versions)
        unresolved = []
        for addon_id in sorted(published):
            for requirement, _version, _optional in self.published_requires(addon_id, versions):
                if requirement in published or requirement in FROM_KODI_ITSELF:
                    continue
                if requirement in EXTERNAL:
                    continue
                unresolved.append("{} -> {}".format(addon_id, requirement))
        self.assertEqual(
            unresolved, [],
            "these dependencies have no source the box can reach: {}".format(
                ", ".join(unresolved)))

    def test_external_dependencies_are_really_external(self):
        # Keeps the allowlist honest: an entry that we started publishing
        # should be removed from it, not left to mask a mistake.
        published = set(self.index_versions())
        for addon_id in EXTERNAL:
            self.assertNotIn(addon_id, published,
                             "{} is published here now, so it no longer "
                             "belongs in EXTERNAL".format(addon_id))

    def test_published_versions_satisfy_every_requirement(self):
        # Mirroring can also fail the other way round: publishing an older
        # module than a dependant asks for. Kodi compares the versions itself
        # and refuses the install, so the published set has to win on its own.
        versions = self.index_versions()
        for addon_id in sorted(versions):
            for requirement, needed, optional in self.published_requires(addon_id, versions):
                if requirement not in versions or not needed:
                    continue
                have = versions[requirement]
                self.assertGreaterEqual(
                    addon_version_key(have), addon_version_key(needed),
                    "{} requires {} {} but this repository publishes {} - "
                    "Kodi would reject the install".format(
                        addon_id, requirement, needed, have))

    def test_the_two_vendoring_scripts_agree_on_ownership(self):
        # Two mirrors of one add-on id would fight over the same filename in
        # thirdparty/, so vendor_kodi.py must never touch what
        # vendor_sandmann.py owns, and the two lists must stay in step.
        import vendor_kodi
        import vendor_sandmann
        self.assertEqual(set(vendor_kodi.MIRRORED_BY_VENDOR_SANDMANN),
                         set(vendor_sandmann.MIRROR_IDS))

    def test_index_lists_each_addon_exactly_once(self):
        ids = self.index_ids()
        self.assertEqual(len(ids), len(set(ids)))

    def test_index_versions_match_the_addon_xml_files(self):
        versions = self.index_versions()
        self.assertEqual(versions[SERVICE_ID], SERVICE_VERSION)
        self.assertEqual(versions[REPO_ID], REPO_VERSION)

    def test_index_md5_matches_the_published_bytes(self):
        with open(os.path.join(self.pages, "addons.xml"), "rb") as fh:
            body = fh.read()
        with open(os.path.join(self.pages, "addons.xml.md5"), "r", encoding="ascii") as fh:
            declared = fh.read().strip()
        self.assertEqual(declared, hashlib.md5(body).hexdigest())

    def test_index_uses_lf_endings_only(self):
        # Windows CRLF would break the md5 on every Kodi that downloads it.
        with open(os.path.join(self.pages, "addons.xml"), "rb") as fh:
            body = fh.read()
        self.assertNotIn(b"\r\n", body)

    def test_index_has_no_duplicate_xml_declaration(self):
        with open(os.path.join(self.pages, "addons.xml"), "r", encoding="utf-8") as fh:
            body = fh.read()
        self.assertEqual(body.count("<?xml"), 1)

    # -- where Kodi actually looks ---------------------------------------

    def test_pages_zip_path_is_the_layout_kodi_derives(self):
        expected = os.path.join("/datadir", SERVICE_ID,
                                "{0}-{1}.zip".format(SERVICE_ID, SERVICE_VERSION))
        self.assertEqual(
            make_release.pages_zip_path("/datadir", SERVICE_ID, SERVICE_VERSION),
            expected)

    def test_every_addon_in_the_index_has_its_zip_where_kodi_looks(self):
        # Regression test. Kodi builds "<datadir>/<id>/<id>-<version>.zip";
        # publishing under "<id>/<version>/" makes the add-on uninstallable.
        # Driven by the index itself, so a newly added add-on is covered
        # without this test needing to change.
        entries = self.index_entries()
        self.assertTrue(entries)
        for addon_id, version in entries:
            expected = os.path.join(self.pages, addon_id,
                                    "{0}-{1}.zip".format(addon_id, version))
            self.assertTrue(os.path.isfile(expected),
                            "Kodi would fetch {} but it was not published".format(expected))

    def test_no_zip_is_hidden_in_a_version_subdirectory(self):
        for addon_id, version in self.index_entries():
            stale = os.path.join(self.pages, addon_id, version)
            self.assertFalse(os.path.exists(stale),
                             "{} uses the old <id>/<version>/ layout Kodi never requests".format(stale))

    def test_repository_zip_is_also_at_the_site_root(self):
        # README step 3 browses the site root for this file by name.
        root_zip = os.path.join(self.pages, "{0}-{1}.zip".format(REPO_ID, REPO_VERSION))
        self.assertTrue(os.path.isfile(root_zip))

    def test_bundled_repository_points_at_the_python3_index(self):
        path = os.path.join(self.pages, "repository.sandmann79.plugins",
                            "repository.sandmann79.plugins-1.0.4.zip")
        with zipfile.ZipFile(path) as archive:
            content = archive.read("repository.sandmann79.plugins/addon.xml").decode("utf-8")
        self.assertIn("packages-py3/addons.xml", content)
        self.assertIn('minversion="18.9.0"', content)

    def test_bundled_zips_are_published_unchanged(self):
        # Byte for byte. These are other people's signed-off releases; a
        # repack would change what users run, and Amazon VOD is GPL code whose
        # distributed form should stay exactly as upstream published it.
        for src in make_release.BUNDLED_ADDONS:
            addon_id, version, _content = make_release.read_bundled_meta(src)
            published = os.path.join(self.pages, addon_id,
                                     "{0}-{1}.zip".format(addon_id, version))
            with open(src, "rb") as fh:
                original = fh.read()
            with open(published, "rb") as fh:
                republished = fh.read()
            self.assertEqual(original, republished,
                             "{} was altered on the way into the repository".format(addon_id))

    # -- browsability ----------------------------------------------------

    def test_directory_listings_expose_every_zip(self):
        root_listing = os.path.join(self.pages, "index.html")
        with open(root_listing, "r", encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn('href="{0}-{1}.zip"'.format(REPO_ID, REPO_VERSION), body)

        for addon_id, version in self.index_entries():
            listing = os.path.join(self.pages, addon_id, "index.html")
            self.assertTrue(os.path.isfile(listing), "{} is missing".format(listing))
            with open(listing, "r", encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn('href="{0}-{1}.zip"'.format(addon_id, version), body)

    def test_listing_anchor_text_equals_href(self):
        # Kodi's HTTPDirectory.cpp only lists an entry whose text is its href.
        with open(os.path.join(self.pages, "index.html"), "r", encoding="utf-8") as fh:
            for line in fh:
                if "<a href=" not in line:
                    continue
                name = line.split("<a href=\"", 1)[1].split("\"", 1)[0]
                self.assertIn(">{0}</a>".format(name), line)


class WriteAddonsXmlTests(unittest.TestCase):
    ONE = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addon id="a.b" version="1.0"/>\n'
    TWO = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addon id="c.d" version="2.0"/>\n'

    def test_wraps_every_document_in_one_addons_root(self):
        xml, _checksum = make_release.write_addons_xml([self.ONE, self.TWO])
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "addons")
        self.assertEqual([a.get("id") for a in root.findall("addon")], ["a.b", "c.d"])

    def test_checksum_covers_the_returned_document(self):
        xml, checksum = make_release.write_addons_xml([self.ONE, self.TWO])
        self.assertEqual(checksum, hashlib.md5(xml.encode("utf-8")).hexdigest())

    def test_single_document_still_works(self):
        xml, _checksum = make_release.write_addons_xml([self.ONE])
        self.assertEqual(len(ET.fromstring(xml).findall("addon")), 1)


class BundledMetaTests(unittest.TestCase):
    def test_bundled_zip_metadata_reads_back_its_own_id_and_version(self):
        for path in make_release.BUNDLED_ADDONS:
            self.assertTrue(os.path.isfile(path), "{} is not vendored".format(path))
            addon_id, version, content = make_release.read_bundled_meta(path)
            self.assertTrue(addon_id)
            self.assertTrue(version)
            self.assertIn(addon_id, content)
            self.assertEqual("{0}-{1}.zip".format(addon_id, version),
                             os.path.basename(path))

    def test_missing_addon_xml_is_reported(self):
        handle, empty = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        try:
            with zipfile.ZipFile(empty, "w") as archive:
                archive.writestr("nothing/here.txt", "x")
            with self.assertRaises(SystemExit):
                make_release.read_bundled_meta(empty)
        finally:
            os.remove(empty)

    def test_bundled_addons_are_discovered_from_the_directory(self):
        # Discovery, not a hardcoded list: dropping a zip in thirdparty/ has to
        # be enough for the next build to publish and index it.
        tmp = tempfile.mkdtemp(prefix="thirdparty-")
        try:
            for name in ("b-1.0.zip", "a-2.0.zip", "notes.txt"):
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                    fh.write("x")
            discovered = [os.path.basename(p)
                          for p in make_release.bundled_addons(tmp)]
            self.assertEqual(discovered, ["a-2.0.zip", "b-1.0.zip"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bundled_addons_tolerates_a_missing_directory(self):
        self.assertEqual(
            make_release.bundled_addons(os.path.join(ROOT, "no-such-directory")),
            ())

    def test_the_repository_really_does_vendor_something(self):
        # A silent glob failure would publish an index with no Amazon VOD in it
        # and nothing else would complain.
        self.assertTrue(make_release.BUNDLED_ADDONS)


if __name__ == "__main__":
    unittest.main()
