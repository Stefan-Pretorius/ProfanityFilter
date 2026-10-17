#!/usr/bin/env python3
"""
vendor_kodi.py
--------------
Refresh the copies of Kodi's own official add-ons that this repository
re-publishes in thirdparty/.

Amazon VOD declares four requirements that live in Kodi's official repository:

    script.module.beautifulsoup4
    script.module.requests
    script.module.pyxbmct
    script.module.inputstreamhelper

Those were originally left to Kodi's official repository, on the theory that it
is enabled on every installation. In practice a Google TV box reported Amazon
VOD as uninstallable with a missing dependency, and the official repository is
the only part of Amazon VOD's dependency tree that this repository does not
serve. Publishing them here as well removes the last third-party host from the
install path: everything then comes from stefan-pretorius.github.io, the same
host the filter and the browse add-on already install from.

Shadowing is not a risk, because these copies are always the *current* official
version, never a newer one. Kodi installs the newest version offered by any
enabled repository, so when Kodi's mirror publishes an update it wins and ours
is simply ignored until this script is run again.

The full set is computed rather than hardcoded: the requirements are read out
of the official index and followed transitively, the same way Kodi resolves
them, so a new sub-dependency of one of these modules is picked up
automatically. Anything Kodi ships itself, and anything mirroring duties
already covered by tools/vendor_sandmann.py, is skipped.

Run from the repository root:
    python3 tools/vendor_kodi.py
"""

import hashlib
import io
import os
import ssl
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIRDPARTY_DIR = os.path.join(ROOT, "thirdparty")

# Kodi 21's add-on branch. The modules below declare nothing but
# "xbmc.python 3.0.0", so the same zips serve Kodi 19 (Matrix), 20 (Nexus)
# and 21 (Omega); there is no reason to publish one copy per branch.
BRANCH = "omega"
INDEX_URL = "https://mirrors.kodi.tv/addons/{0}/addons.xml".format(BRANCH)
CHECKSUM_URL = INDEX_URL + ".md5"
DATADIR = "https://mirrors.kodi.tv/addons/{0}/".format(BRANCH)

# The official modules Amazon VOD asks for directly. These are the seeds used
# when thirdparty/ is empty; normally the requirements of every zip already
# vendored there are seeded as well, so something like script.module.six -
# required by script.module.mechanicalsoup rather than by Amazon VOD itself -
# is picked up without being spelled out here.
SEEDS = (
    "script.module.beautifulsoup4",
    "script.module.requests",
    "script.module.pyxbmct",
    "script.module.inputstreamhelper",
)

# Satisfied by Kodi itself, never published anywhere. Kodi bundles both of
# these with the application on every platform, so a repository that carried
# them would be inventing a copy of something that is already there.
# script.module.pil in particular is a deliberate placeholder in Kodi's own
# source tree (xbmc/xbmc/addons/script.module.pil holds an addon.xml and an
# icon and nothing else), which is why it appears in no add-on index.
KODI_BUNDLED = frozenset((
    "xbmc.addon",
    "xbmc.python",
    "xbmc.gui",
    "script.module.pil",
    "script.module.pycryptodome",
))

# Owned by tools/vendor_sandmann.py. If the closure below ever reaches one of
# these, that script is the one that should fetch it - two mirrors of the same
# add-on id would fight over the filename in thirdparty/.
MIRRORED_BY_VENDOR_SANDMANN = frozenset((
    "plugin.video.amazon-test",
    "script.module.amazoncaptcha",
    "script.module.mechanicalsoup",
    "script.module.pyautogui",
))

HEADERS = {"User-Agent": "ProfanityFilter-release-tooling"}


def urlopen(url):
    """
    Fetch *url*, tolerating a TLS-inspecting proxy.

    mirrors.kodi.tv cannot always be verified from a managed Windows box (an
    interception proxy replaces the certificate chain). Retrying once without
    verification keeps this script usable there; CI and normal boxes take the
    verified path and never see the fallback.
    """
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        return urllib.request.urlopen(request, timeout=180)
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        print("  note: cannot verify the TLS certificate for {0} - retrying "
              "unverified (interception proxy?)".format(url.split("/")[2]))
        return urllib.request.urlopen(
            request, timeout=180, context=ssl._create_unverified_context())


def fetch(url):
    try:
        with urlopen(url) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit("{} returned HTTP {}".format(url, error.code))
    except Exception as error:
        raise SystemExit("could not fetch {}: {!r}".format(url, error))


def parse_index(blob):
    """
    {addon id: (version, (requirement ids,))} for an official addons.xml.

    The official index carries whole addon.xml documents, requirements
    included, so the dependency graph can be walked without downloading
    anything first - which is exactly what Kodi does with it.
    """
    entries = {}
    for addon in ET.fromstring(blob).findall("addon"):
        requires = addon.find("requires")
        entries[addon.get("id")] = (
            addon.get("version"),
            tuple(imp.get("addon") for imp in requires.findall("import"))
            if requires is not None else (),
        )
    return entries


def closure(entries, seeds):
    """
    Every add-on reachable from *seeds*, breadth first, in index order.

    Requirements this repository does not publish - Kodi's own bundled
    modules, and the add-ons vendor_sandmann.py already mirrors - are skipped
    rather than followed. Anything else that is not in the official index is
    reported, because Kodi would then have no way to resolve it.
    """
    order = []
    seen = set()
    queue = list(seeds)
    external = []
    while queue:
        addon_id = queue.pop(0)
        if addon_id in seen:
            continue
        seen.add(addon_id)
        if addon_id in KODI_BUNDLED or addon_id in MIRRORED_BY_VENDOR_SANDMANN:
            continue
        if addon_id not in entries:
            external.append(addon_id)
            continue
        version, requires = entries[addon_id]
        order.append(addon_id)
        queue.extend(requires)
    return order, sorted(set(external))


def published_requirements(thirdparty_dir=THIRDPARTY_DIR):
    """
    Every requirement declared by an add-on already vendored in thirdparty/.

    The official half of the dependency tree is only reachable through the
    files we publish - script.module.six, for instance, arrives via
    script.module.mechanicalsoup - so the walk starts from what is on disk
    rather than from Amazon VOD alone.
    """
    requirements = set()
    if not os.path.isdir(thirdparty_dir):
        return requirements
    for name in sorted(os.listdir(thirdparty_dir)):
        if not name.endswith(".zip"):
            continue
        with zipfile.ZipFile(os.path.join(thirdparty_dir, name)) as archive:
            candidates = [n for n in archive.namelist()
                          if os.path.basename(n) == "addon.xml"]
            if not candidates:
                continue
            root = ET.fromstring(archive.read(min(candidates, key=len)))
        requires = root.find("requires")
        if requires is not None:
            requirements.update(imp.get("addon") for imp in requires.findall("import"))
    return requirements


def main():
    index = fetch(INDEX_URL)
    declared = fetch(CHECKSUM_URL).decode("ascii").strip().split()[0]
    actual = hashlib.md5(index).hexdigest()
    if declared != actual:
        raise SystemExit("index checksum mismatch: Kodi would reject this index "
                         "({} != {})".format(declared, actual))
    print("Kodi {} index verified ({} bytes, md5 {})".format(
        BRANCH, len(index), actual))

    entries = parse_index(index)
    for seed in SEEDS:
        if seed not in entries:
            raise SystemExit(
                "{} is no longer in Kodi's {} index - either Kodi stopped "
                "shipping it or the branch has moved; check before "
                "publishing".format(seed, BRANCH))

    seeds = tuple(SEEDS) + tuple(sorted(published_requirements()))
    addon_ids, external = closure(entries, seeds)
    print("Kodi-side dependency set, {0} add-on(s):".format(len(addon_ids)))
    for addon_id in addon_ids:
        print("  {0:<44} {1}".format(addon_id, entries[addon_id][0]))
    if external:
        print("  not published here or by Kodi, so left to their own source: "
              + ", ".join(external))

    os.makedirs(THIRDPARTY_DIR, exist_ok=True)
    wanted = set()
    for addon_id in addon_ids:
        version = entries[addon_id][0]
        name = "{0}-{1}.zip".format(addon_id, version)
        blob = fetch("{0}{1}/{2}".format(DATADIR, addon_id, name))

        # Trust the archive over the index, the same check vendor_sandmann.py
        # makes: the id/version pair inside the zip is what becomes the
        # filename Kodi goes looking for.
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            inner = ET.fromstring(archive.read(addon_id + "/addon.xml"))
        if (inner.get("id"), inner.get("version")) != (addon_id, version):
            raise SystemExit("{} declares {}/{} - refusing to publish it under "
                             "the index's name".format(name, inner.get("id"),
                                                       inner.get("version")))

        wanted.add(name)
        target = os.path.join(THIRDPARTY_DIR, name)
        with open(target, "wb") as handle:
            handle.write(blob)
        digest = hashlib.sha256(blob).hexdigest()
        print("  {0:<52} {1:>9,} bytes  sha256 {2}".format(name, len(blob), digest))

    # Anything of ours in this set that the index no longer offers is stale.
    for existing in os.listdir(THIRDPARTY_DIR):
        if not existing.endswith(".zip"):
            continue
        stem = existing[:-len(".zip")]
        addon_id = stem[:stem.rindex("-")] if "-" in stem else stem
        if addon_id in addon_ids and existing not in wanted:
            os.remove(os.path.join(THIRDPARTY_DIR, existing))
            print("  removed stale", existing)

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
