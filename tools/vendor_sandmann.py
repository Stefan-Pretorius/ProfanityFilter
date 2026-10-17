#!/usr/bin/env python3
"""
vendor_sandmann.py
------------------
Refresh the copies of Sandmann79's add-ons that this repository re-publishes in
thirdparty/.

Why these are vendored rather than left behind Sandmann79's repository pointer:
a Kodi box that installs "Sandmann79s Repository" from this repository gets a
766-byte add-on whose only job is to fetch an index from raw.githubusercontent
.com. If that nested fetch does not happen, the repository looks empty and
Amazon VOD never appears - which is exactly what happened in practice. Shipping
the zips here means Amazon VOD installs straight from
stefan-pretorius.github.io, the same host the filter already comes from.

The repository pointer is still listed in our index as well, so a box that wants
Amazon VOD updates direct from upstream can have them: Kodi installs the newest
version offered by any enabled repository.

Only the add-ons Amazon VOD actually declares it needs are mirrored. The rest of
its dependencies come from Kodi's official repository, which is enabled by
default, so they are not duplicated here.

Run from the repository root:
    python3 tools/vendor_sandmann.py
"""

import hashlib
import io
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIRDPARTY_DIR = os.path.join(ROOT, "thirdparty")

INDEX_URL = "https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/addons.xml"
CHECKSUM_URL = "https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/addons.xml.md5"
DATADIR = "https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/"

# Amazon VOD itself, plus the three modules it requires that exist nowhere else.
# (script.module.beautifulsoup4, script.module.requests, script.module.pyxbmct
# and script.module.inputstreamhelper are in Kodi's official repository.)
MIRROR_IDS = (
    "plugin.video.amazon-test",
    "script.module.amazoncaptcha",
    "script.module.mechanicalsoup",
    "script.module.pyautogui",
)

HEADERS = {"User-Agent": "ProfanityFilter-release-tooling"}


def fetch(url):
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit("{} returned HTTP {}".format(url, error.code))
    except Exception as error:
        raise SystemExit("could not fetch {}: {!r}".format(url, error))


def main():
    index = fetch(INDEX_URL)
    declared = fetch(CHECKSUM_URL).decode("ascii").strip().split()[0]
    actual = hashlib.md5(index).hexdigest()
    if declared != actual:
        raise SystemExit("index checksum mismatch: Kodi would reject this index "
                         "({} != {})".format(declared, actual))
    print("Sandmann79 index verified ({} bytes, md5 {})".format(len(index), actual))

    root = ET.fromstring(index)
    versions = {a.get("id"): a.get("version") for a in root.findall("addon")}

    os.makedirs(THIRDPARTY_DIR, exist_ok=True)
    written = []
    for addon_id in MIRROR_IDS:
        if addon_id not in versions:
            raise SystemExit("{} is no longer in Sandmann79's index".format(addon_id))
        version = versions[addon_id]
        name = "{0}-{1}.zip".format(addon_id, version)
        blob = fetch("{0}{1}/{2}".format(DATADIR, addon_id, name))

        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            inner = ET.fromstring(archive.read(addon_id + "/addon.xml"))
        if (inner.get("id"), inner.get("version")) != (addon_id, version):
            raise SystemExit("{} declares {}/{} - refusing to publish it under the "
                             "index's name".format(name, inner.get("id"),
                                                   inner.get("version")))

        # Drop any other version of this add-on we previously vendored.
        for existing in os.listdir(THIRDPARTY_DIR):
            if existing.startswith(addon_id + "-") and existing != name:
                os.remove(os.path.join(THIRDPARTY_DIR, existing))
                print("  removed stale", existing)

        target = os.path.join(THIRDPARTY_DIR, name)
        with open(target, "wb") as handle:
            handle.write(blob)
        digest = hashlib.sha256(blob).hexdigest()
        written.append((addon_id, version, len(blob), digest))
        print("  {0:<44} {1:>9,} bytes  sha256 {2}".format(name, len(blob), digest))

    print()
    print("thirdparty/ now holds:")
    for name in sorted(os.listdir(THIRDPARTY_DIR)):
        if name.endswith(".zip"):
            size = os.path.getsize(os.path.join(THIRDPARTY_DIR, name))
            print("  {0:<52} {1:>9,} bytes".format(name, size))
    print()
    print("tools/make_release.py discovers thirdparty/*.zip automatically, so the")
    print("index will list these on the next build. Update the tables in")
    print("thirdparty/README.md with the versions and checksums above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
