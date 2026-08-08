#!/usr/bin/env python3
"""
make_release.py
---------------
Builds distributable artifacts for the Profanity Filter Kodi add-on:

  dist/service.profanity.filter-<version>.zip   (the add-on, installable zip)
  dist/repository.profanityfilter-<version>.zip (repository add-on, install once)
  dist/addons.xml / addons.xml.md5              (repository index)
  dist/gh-pages/...                             (ready-to-upload GitHub Pages tree)

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
ADDON_XML = os.path.join(ADDON_DIR, "addon.xml")
DIST = os.path.join(ROOT, "dist")
PAGES = os.path.join(DIST, "gh-pages")

# Repository add-on id/version (kept in sync with repository.profanityfilter/addon.xml)
REPO_ID = "repository.profanityfilter"
REPO_VERSION = "1.0.0"


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


def read_addon_meta(path=ADDON_XML):
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    addon_id = re.search(r'<addon id="([^"]+)"', content).group(1)
    version = re.search(r'<addon[^>]*\sversion="([^"]+)"', content).group(1)
    return addon_id, version, content


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


def write_addons_xml(addon_content):
    body = addon_content.split("?>", 1)[-1].strip()
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n{body}\n</addons>\n'.format(
        body=body
    )
    checksum = hashlib.md5(xml.encode("utf-8")).hexdigest()
    return xml, checksum


def main():
    addon_id, version, addon_content = read_addon_meta()
    print("Building {} {}...".format(addon_id, version))

    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(PAGES)

    # 1. Add-on zip (release asset + repository payload)
    addon_zip = os.path.join(DIST, "{id}-{ver}.zip".format(id=addon_id, ver=version))
    zip_dir(ADDON_DIR, addon_zip)
    print("  ->", addon_zip)

    # 2. Repository add-on zip (one-time install)
    repo_zip = os.path.join(DIST, "{id}-{ver}.zip".format(id=REPO_ID, ver=REPO_VERSION))
    zip_dir(REPO_DIR, repo_zip)
    print("  ->", repo_zip)

    # 3. Repository index
    xml, checksum = write_addons_xml(addon_content)
    with open(os.path.join(PAGES, "addons.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)
    with open(os.path.join(PAGES, "addons.xml.md5"), "w", encoding="utf-8") as fh:
        fh.write(checksum)

    # 4. GitHub Pages payload
    pages_addon_dir = os.path.join(PAGES, addon_id, version)
    os.makedirs(pages_addon_dir)
    shutil.copy2(addon_zip, os.path.join(pages_addon_dir, os.path.basename(addon_zip)))
    shutil.copy2(repo_zip, os.path.join(PAGES, os.path.basename(repo_zip)))

    # 5. Kodi-browsable directory listings (index.html in every directory)
    write_directory_listings(PAGES, "Profanity Filter Repository")

    print("  ->", os.path.join(PAGES, "addons.xml"))
    print("  ->", os.path.join(PAGES, "addons.xml.md5"))
    print("  ->", os.path.join(PAGES, "service.profanity.filter/{}/".format(version)))
    print("  ->", os.path.join(PAGES, os.path.basename(repo_zip)))
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())
