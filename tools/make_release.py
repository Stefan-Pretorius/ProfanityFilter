#!/usr/bin/env python3
"""
make_release.py
---------------
Builds distributable artifacts for the Profanity Filter Kodi add-on:

  dist/service.profanity.filter-<version>.zip   (the add-on, installable zip)
  dist/repository.profanityfilter-<version>.zip (repository add-on, install once)
  dist/<bundled add-on>-<version>.zip           (copied from thirdparty/)
  dist/gh-pages/addons.xml / addons.xml.md5     (repository index)
  dist/gh-pages/...                             (ready-to-upload GitHub Pages tree)

Everything in dist/*.zip also becomes a GitHub Release asset, and the whole
dist/gh-pages tree is published to the gh-pages branch. A Kodi box can
therefore install the filter, this repository add-on, Amazon VOD (Prime Video)
and Ororo TV Browse from one URL, with no nested repository to find.

Run from the repository root:
    python3 tools/make_release.py
"""

import hashlib
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(ROOT, "service.profanity.filter")
REPO_DIR = os.path.join(ROOT, "repository.profanityfilter")
THIRDPARTY_DIR = os.path.join(ROOT, "thirdparty")
ADDON_XML = os.path.join(ADDON_DIR, "addon.xml")
DIST = os.path.join(ROOT, "dist")
PAGES = os.path.join(DIST, "gh-pages")

# Add-ons published byte for byte instead of being built here. Every zip in
# thirdparty/ is published as-is, so adding or refreshing one is a file
# operation rather than an edit here. Provenance, versions and licences are
# recorded in thirdparty/README.md.
#
#   * repository.sandmann79.plugins - a 766-byte pointer that lets Amazon VOD
#     update from upstream.
#   * plugin.video.amazon-test (Amazon VOD) and the three modules it requires
#     that exist nowhere but Sandmann79's index - script.module.amazoncaptcha,
#     script.module.mechanicalsoup, script.module.pyautogui. Mirrored so that
#     Amazon VOD installs directly from this repository: a nested repository
#     fetch is not something Kodi reliably performs, and when it does not, the
#     nested repository simply looks empty. Refresh with
#     tools/vendor_sandmann.py.
#   * plugin.video.ororotv.browse - developed in its own repository,
#     https://github.com/Stefan-Pretorius/OroroBrowse.
#
# Amazon VOD's other dependencies (script.module.beautifulsoup4, .requests,
# .pyxbmct, .inputstreamhelper) deliberately come from Kodi's official
# repository, which is enabled by default. Duplicating those here would let a
# stale copy of ours be installed in place of a newer official one.
def bundled_addons(thirdparty_dir=THIRDPARTY_DIR):
    """
    Every add-on zip vendored in thirdparty/, as paths, sorted.

    Discovery rather than a hardcoded list, so adding or refreshing a bundled
    add-on is a file operation and the published index cannot drift out of
    step with what is actually vendored.
    """
    if not os.path.isdir(thirdparty_dir):
        return ()
    return tuple(os.path.join(thirdparty_dir, name)
                 for name in sorted(os.listdir(thirdparty_dir))
                 if name.endswith(".zip"))


BUNDLED_ADDONS = bundled_addons()

# The repository add-on is also copied to the site root: Kodi does not look
# there when installing from the repository, but it is the "install from zip
# file" URL the README gives out.
ROOT_PUBLISHED_ID = "repository.profanityfilter"


def apache_listing(title, names):
    """
    Generate a GitHub Pages index.html that Kodi can browse.

    Kodi's HTTP directory parser (HTTPDirectory.cpp) only accepts an entry
    whose *anchor text equals its href* (the filename), so friendly labels
    must not be used. This produces a listing in Apache autoindex style,
    one '<a href="name">name</a>' per line.
    """
    rows = "\n".join('<a href="{0}">{0}</a>'.format(n) for n in names)
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        "<title>{0}</title>\n"
        "</head>\n"
        "<body>\n"
        "<h1>{0}</h1><hr><pre>\n"
        "{1}\n"
        "</pre><hr>\n"
        "</body>\n"
        "</html>\n"
    ).format(title, rows)


def write_directory_listings(root, title):
    """
    Write an index.html into *root* and every sub-directory so that Kodi can
    browse the tree from the top level down to the add-on zip.
    """
    for cur, dirs, files in os.walk(root):
        dirs.sort()
        names = []
        if os.path.abspath(cur) != os.path.abspath(root):
            names.append("../")
        names.extend(d + "/" for d in dirs)
        names.extend(sorted(f for f in files if f != "index.html"))
        rel = os.path.relpath(cur, root)
        page_title = title if rel == "." else title + "/" + rel.replace(os.sep, "/")
        with open(os.path.join(cur, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(apache_listing(page_title, names))


def parse_addon_meta(content):
    """The (id, version) pair declared in an addon.xml document."""
    addon_id = re.search(r'<addon id="([^"]+)"', content).group(1)
    version = re.search(r'<addon[^>]*\sversion="([^"]+)"', content).group(1)
    return addon_id, version


def read_addon_meta(path=ADDON_XML):
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    addon_id, version = parse_addon_meta(content)
    return addon_id, version, content


def read_bundled_meta(path):
    """
    (id, version, addon.xml) for an add-on zip shipped unchanged.

    The archive is the source of truth. A bundled add-on must be published
    under exactly the id and version it declares, because that pair is what
    Kodi turns into the filename it goes looking for.
    """
    with zipfile.ZipFile(path) as archive:
        candidates = [n for n in archive.namelist()
                      if os.path.basename(n) == "addon.xml"]
        if not candidates:
            raise SystemExit("{} contains no addon.xml".format(path))
        content = archive.read(min(candidates, key=len)).decode("utf-8")
    addon_id, version = parse_addon_meta(content)
    return addon_id, version, content


def pages_zip_path(root, addon_id, version):
    """
    Where Kodi looks for an add-on's zip inside a repository.

    Kodi derives the download URL in CAddonInfoBuilder::Generate as
    "<datadir>/<addon id>/<addon id>-<version>.zip" -- the same layout the
    official Kodi mirrors use. Note there is no "<addon id>/<version>/"
    directory in that path, so publishing a zip there leaves it invisible:
    Kodi asks for a file that does not exist and the install or update fails.
    """
    return os.path.join(root, addon_id, "{0}-{1}.zip".format(addon_id, version))


def zip_dir(src_dir, out_zip):
    """Zip *src_dir* into *out_zip* with the folder itself as the archive root."""
    root_name = os.path.basename(src_dir.rstrip(os.sep))
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for cur, _, files in os.walk(src_dir):
            for fname in sorted(files):
                if fname.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(cur, fname)
                rel = os.path.relpath(full, src_dir)
                zf.write(full, os.path.join(root_name, rel))


def write_addons_xml(addon_contents):
    """
    Build the repository index from one or more addon.xml documents.

    Each body is the addon.xml without its XML declaration, concatenated
    inside a single <addons> root - the layout Kodi's AddonsFromRepoXML
    expects.
    """
    bodies = [c.split("?>", 1)[-1].strip() for c in addon_contents]
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        "<addons>\n{0}\n</addons>\n"
    ).format("\n".join(bodies))
    # Several bundled add-ons ship their manifest with CRLF endings. Kodi does
    # not care either way, but normalising keeps the published index to LF only
    # - diffable, and its checksum a function of the content rather than of
    # whichever editor last touched an upstream manifest.
    xml = xml.replace("\r\n", "\n").replace("\r", "\n")
    checksum = hashlib.md5(xml.encode("utf-8")).hexdigest()
    return xml, checksum


def main():
    addon_id, version, addon_content = read_addon_meta(ADDON_XML)
    print("Building {} {}...".format(addon_id, version))

    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(PAGES)

    # 1. Add-on zips. Ours are built from source; bundled ones are copied
    #    unchanged. Each entry is (id, version, addon.xml, dist zip).
    published = []
    for src_dir in (ADDON_DIR, REPO_DIR):
        meta_id, meta_version, content = read_addon_meta(
            os.path.join(src_dir, "addon.xml"))
        out_zip = os.path.join(DIST, "{0}-{1}.zip".format(meta_id, meta_version))
        zip_dir(src_dir, out_zip)
        published.append((meta_id, meta_version, content, out_zip))
        print("  ->", out_zip)

    for bundled in BUNDLED_ADDONS:
        meta_id, meta_version, content = read_bundled_meta(bundled)
        out_zip = os.path.join(DIST, os.path.basename(bundled))
        shutil.copy2(bundled, out_zip)
        published.append((meta_id, meta_version, content, out_zip))
        print("  ->", out_zip, "(bundled, unchanged)")

    # 2. Repository index, listing every add-on Kodi should be able to
    #    install. Written as raw bytes with explicit LF endings: Kodi verifies
    #    addons.xml against addons.xml.md5, so the checksum has to be taken
    #    over exactly the bytes that get published - writing in text mode
    #    would let Windows turn the newlines into CRLF and the checksum would
    #    never match.
    xml, checksum = write_addons_xml([entry[2] for entry in published])
    with open(os.path.join(PAGES, "addons.xml"), "wb") as fh:
        fh.write(xml.encode("utf-8"))
    with open(os.path.join(PAGES, "addons.xml.md5"), "w", encoding="ascii", newline="") as fh:
        fh.write(checksum)

    # 3. GitHub Pages payload, each zip at the path Kodi actually requests.
    for meta_id, meta_version, _content, out_zip in published:
        target = pages_zip_path(PAGES, meta_id, meta_version)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(out_zip, target)
        print("  ->", target)

    for meta_id, _version, _content, out_zip in published:
        if meta_id == ROOT_PUBLISHED_ID:
            shutil.copy2(out_zip, os.path.join(PAGES, os.path.basename(out_zip)))
            print("  ->", os.path.join(PAGES, os.path.basename(out_zip)))

    # 4. Kodi-browsable directory listings (index.html in every directory)
    write_directory_listings(PAGES, "Profanity Filter Repository")

    print("  ->", os.path.join(PAGES, "addons.xml"))
    print("  ->", os.path.join(PAGES, "addons.xml.md5"))
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())
