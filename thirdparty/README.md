# Bundled add-ons

These zips are **not** built from source in this repository. They are copied
verbatim from elsewhere and re-published unchanged, so that a Kodi box can
install everything it needs from this repository alone.

`tools/make_release.py` discovers them by name: every `*.zip` in this directory
is published and listed in the repository index, so adding or refreshing one is
a file operation rather than an edit in a second place. Each filename must be
`<addon id>-<version>.zip` and must match the id and version declared inside the
archive — a test enforces that, because that pair is exactly what Kodi turns
into the URL it goes looking for.

| File | What it is | Size | Licence |
|---|---|---|---|
| `plugin.video.amazon-test-1.2.3+matrix.1.zip` | Amazon VOD (Prime Video) | 877,603 B | GPL-3.0 |
| `script.module.amazoncaptcha-0.5.11+matrix.1.zip` | Amazon VOD dependency | 867,780 B | MIT |
| `script.module.mechanicalsoup-1.0.0+matrix.1.zip` | Amazon VOD dependency | 24,596 B | MIT |
| `script.module.pyautogui-0.9.51+matrix.1.zip` | Amazon VOD dependency | 41,067 B | BSD-3-Clause |
| `script.module.beautifulsoup4-4.12.2.zip` | Kodi module Amazon VOD needs | 80,703 B | MIT |
| `script.module.soupsieve-2.4.1.zip` | dependency of beautifulsoup4 | 41,348 B | MIT |
| `script.module.requests-2.31.0.zip` | Kodi module Amazon VOD needs | 67,576 B | Apache-2.0 |
| `script.module.certifi-2023.5.7.zip` | dependency of requests | 162,689 B | MPL-2.0 |
| `script.module.chardet-5.1.0.zip` | dependency of requests | 204,491 B | LGPL-2.1 |
| `script.module.idna-3.10.0.zip` | dependency of requests | 73,349 B | BSD-3-Clause |
| `script.module.urllib3-2.2.3.zip` | dependency of requests | 130,842 B | MIT |
| `script.module.pysocks-1.7.0+matrix.1.zip` | dependency of urllib3 | 23,589 B | BSD-3-Clause |
| `script.module.six-1.16.0+matrix.1.zip` | dependency of mechanicalsoup | 16,999 B | MIT |
| `script.module.pyxbmct-1.3.2+matrix.1.zip` | Kodi module Amazon VOD needs | 406,640 B | GPL-3.0 |
| `script.module.inputstreamhelper-0.8.6.zip` | Kodi module Amazon VOD needs | 110,321 B | MIT |
| `repository.sandmann79.plugins-1.0.4.zip` | pointer for Amazon VOD updates | 766 B | GPL-3.0 |
| `plugin.video.ororotv.browse-1.0.0.zip` | Ororo TV Browse (our own) | 21,910 B | GPL-3.0-or-later |

Every zip is published byte for byte unchanged — licence files included — and a
test checks that, because a repack would change what users run and would make
the distributed form of GPL code diverge from upstream's.

## Amazon VOD (`plugin.video.amazon-test`) and its private modules

| | |
|---|---|
| What it is | **Amazon VOD** — plays Prime Video through Kodi, which is the only way the Profanity Filter can mute it (the Prime Video app itself cannot be filtered). |
| Upstream | https://github.com/Sandmann79/xbmc |
| Index | https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/addons.xml |
| Version | 1.2.3+matrix.1 |
| SHA-256 | `df68ad179f32f86b46c73a4caedbe8fe8d0ef98ab81a087c9f38ccc62e7716d5` |
| Licence | GPL-3.0 (a `LICENSE` file ships inside the zip) |

Amazon VOD declares eight requirements. Three exist **only** in Sandmann79's
index, so they are mirrored here, otherwise Kodi could not satisfy them and the
install would fail with an unmet dependency:

| Module | Version | SHA-256 | Licence |
|---|---|---|---|
| `script.module.amazoncaptcha` | 0.5.11+matrix.1 | `bb0ad30c96d97268e0c7ec26731bc6ee35eca3dd66e7e13e191e4dbf3562d0ae` | MIT |
| `script.module.mechanicalsoup` | 1.0.0+matrix.1 | `3d8870081a2e03ae0ded83d05051fcfad379f320fff0b64bbfc11bea3fdecd7e` | MIT |
| `script.module.pyautogui` | 0.9.51+matrix.1 | `1d0ae84f81993631c4116dbda9b61c1199b40689c7e47d6c31a5ba1d51aa873a` | BSD-3-Clause |

Two more ship inside Kodi itself and are published nowhere: `xbmc.python` and
`script.module.pil`. Kodi bundles both on every platform —
`script.module.pil` is a deliberate placeholder in Kodi's own source tree
(`xbmc/addons/script.module.pil` holds an `addon.xml` and an icon and no code
at all), which is why it appears in no add-on index even though
`script.module.amazoncaptcha` declares a dependency on it. That placeholder was
the prime suspect when a box reported a missing dependency; it is not the cause,
because Kodi ships it with the application rather than serving it from a
repository.

### Updating the five Sandmann79 files

```sh
python tools/vendor_sandmann.py
```

That verifies Sandmann79's index checksum, downloads the current version of each,
refuses to publish anything whose declared id/version does not match the index,
deletes the superseded file, and prints the new sizes and checksums. Then update
the tables above and re-run `python tools/make_release.py`.

## Kodi modules mirrored from `mirrors.kodi.tv` (`tools/vendor_kodi.py`)

The remaining four requirements — `script.module.beautifulsoup4`,
`script.module.requests`, `script.module.pyxbmct` and
`script.module.inputstreamhelper` — are in Kodi's official repository, and were
originally left there on the theory that it is enabled on every installation.
**That turned out not to be good enough.** A box reported Amazon VOD as
uninstallable with a missing dependency, and Kodi's official repository is the
only part of this dependency tree that this repository was not serving. They are
mirrored here now, together with everything they need in turn, so that reaching
`stefan-pretorius.github.io` and having Kodi installed is sufficient.

| Module | Version | SHA-256 | Licence | Needed by |
|---|---|---|---|---|
| `script.module.beautifulsoup4` | 4.12.2 | `20e7e56c9f2575bc3977b7d1c875a4a56163b789a4c088a561d988f4c64fd3cd` | MIT | Amazon VOD |
| `script.module.soupsieve` | 2.4.1 | `dd8c8f17c3c8e8a87b700d2c076f6771a81b08e3ba313bb5c64ddc1500788d8b` | MIT | beautifulsoup4 |
| `script.module.requests` | 2.31.0 | `a5704f0fd7afb4154e1beea9b5f05a002bcd75fa581a1e5fd15ece39bf2bd38a` | Apache-2.0 | Amazon VOD |
| `script.module.certifi` | 2023.5.7 | `c16d4cd2efe6e57dbb5e8d71a9beb3af213b1e3d717e8b0b24f0cbdc4c645070` | MPL-2.0 | requests |
| `script.module.chardet` | 5.1.0 | `d5010fc55a9523d86a306ae9e6a8dea0e3248fe079b9ed37280fe86110cd766a` | LGPL-2.1 | requests |
| `script.module.idna` | 3.10.0 | `c4ff34dbfab2736e9214a374d331bd6f558d8b3fea8eb7902e210749509242b3` | BSD-3-Clause | requests |
| `script.module.urllib3` | 2.2.3 | `740b2d63bb50eee9fb35f01c567ec8d3588c5bbd548e2b8d280932be30d82f53` | MIT | requests |
| `script.module.pysocks` | 1.7.0+matrix.1 | `fd043d04eecbd3f34e85a9ff35c4cdab57af8a6d6e6b90317806a0f72685c03b` | BSD-3-Clause | urllib3 |
| `script.module.six` | 1.16.0+matrix.1 | `4197f7773f75ab9f16b3c920195acbb8b8b151b4b3c8c3e14fc4876e764e3860` | MIT | mechanicalsoup |
| `script.module.pyxbmct` | 1.3.2+matrix.1 | `f0448a1b3e7245b359062227fa72e8875c36c492d63d099be0e71806d4335cac` | GPL-3.0 | Amazon VOD |
| `script.module.inputstreamhelper` | 0.8.6 | `326ff6182802c7fc3967df254823c84ba39eedacae03b1349eb4acafcb231801` | MIT | Amazon VOD |

These are Kodi team code, not Sandmann79's, and are published exactly as Kodi's
mirror serves them.

### Why mirroring these does not shadow the official copies

Kodi installs the newest version offered by any enabled repository, and these
copies are always the **current** official version, never a newer one. When
Kodi's mirror publishes an update it wins and our copy is ignored until
`tools/vendor_kodi.py` is run again. A box that can reach `mirrors.kodi.tv`
therefore sees no difference at all; a box that cannot still gets everything it
needs. The set is computed, not hardcoded: the requirements are read out of the
official index and followed transitively the same way Kodi resolves them, so
`script.module.six` (required by `mechanicalsoup`, not by Amazon VOD) is picked
up without being listed anywhere.

Tests pin all of this down:

* `test_the_whole_dependency_tree_is_served_from_here` - every requirement of
  every add-on in the index is either in the index too, shipped with Kodi
  (`xbmc.python`, `xbmc.addon`, `script.module.pil`), or listed in the test's
  `EXTERNAL` set with a reason. The only external entry is
  `plugin.video.ororotv`, which ororo publishes itself.
* `test_published_versions_satisfy_every_requirement` - e.g. the published
  `script.module.pyxbmct` 1.3.2 satisfies Amazon VOD's `1.3.1+matrix.1`. An
  older module published here would make Kodi refuse the install.
* `test_the_two_vendoring_scripts_agree_on_ownership` - two mirrors of one
  add-on id would fight over the same filename in `thirdparty/`.

### Updating these eleven files

```sh
python tools/vendor_kodi.py
```

That verifies the official index checksum, walks the dependency graph, refuses
to publish anything whose declared id/version does not match the index, deletes
superseded files, and prints the new sizes and checksums. Then update the tables
above and re-run `python tools/make_release.py`.

## `repository.sandmann79.plugins-1.0.4.zip`

| | |
|---|---|
| What it is | The Kodi *repository* add-on for Sandmann79's add-ons. |
| Upstream release | https://github.com/Sandmann79/xbmc/releases/tag/Repository (release "Plugin Repository v1.0.4") |
| Download URL | https://github.com/Sandmann79/xbmc/releases/download/Repository/repository.sandmann79.plugins-1.0.4.zip |
| Size | 766 bytes |
| SHA-256 | `95ced51a9ce7f1732e132a4c51fdbe31e0f330f4728fc29085194d0f7adb8aeb` |
| Licence | GPL-3.0 |

This is a **pointer, not code**. Its `addon.xml` declares two `<dir>` blocks and
Kodi 19+ uses the second one:

```xml
<dir minversion="18.9.0">
  <info compressed="false">https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/addons.xml</info>
  <checksum>https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/addons.xml.md5</checksum>
  <datadir zip="true">https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/</datadir>
</dir>
```

Because it points at Sandmann79's live index, a box that installs it can track
Amazon VOD directly from upstream. This copy only needs to change if the
repository URL or the `minversion` gating changes.

### Why Amazon VOD is bundled here as well

The first version of this repository carried only the pointer above. That
turned out not to be enough. Installing the pointer gives Kodi an add-on whose
only job is to fetch a second index from `raw.githubusercontent.com`, and until
that second fetch happens the nested repository has nothing in it — no Amazon
VOD, no error, nothing to select. On the Google TV box it was reported as
"Amazon VOD is not doing anything", and there is nothing in the add-on browser
to explain why.

So Amazon VOD, the modules it needs and every module those in turn need are
published here too, served from `stefan-pretorius.github.io` — the same host the
filter itself already installs from, which is known to work from that box. The
pointer stays listed as well, so both routes are available: one-click install
from here, and upstream updates for anyone who installs the nested repository.
Kodi installs the newest version offered by any enabled repository, so the two
do not conflict.

### Updating this file

1. Check for a newer release: https://github.com/Sandmann79/xbmc/releases
   (the release tagged `Repository`). Most releases do not change it.
2. Download the new `repository.sandmann79.plugins-<version>.zip`.
3. Replace the file here and delete the old one. The build discovers the new
   filename automatically; update this table and the summary table above.
4. Re-run `python tools/make_release.py` and check the listing.

## `plugin.video.ororotv.browse-1.0.0.zip`

| | |
|---|---|
| What it is | **Ororo TV Browse** — a Netflix-style browser for the ororo.tv catalogue (poster walls, featured rows, genres, A–Z, years, rating bands, combined search). |
| Source | https://github.com/Stefan-Pretorius/OroroBrowse (its own repository, built and tagged there) |
| Upstream release | https://github.com/Stefan-Pretorius/OroroBrowse/releases |
| Size | 21,910 bytes |
| SHA-256 | `f9af3847d1df953c248ed3cb84ef1c0936274e65b8e869296d63ce466b9ec8af` |
| Licence | GPL-3.0-or-later |

It is **not** third-party code. It lives here so that one source URL on a Kodi
box covers the whole set — filter, Amazon VOD and this browser — instead of
needing a second repository add-on installed by hand. It keeps its own
repository so it can also be published on its own later.

It declares a dependency on `plugin.video.ororotv` 4.0.0 or newer. That add-on
is not in this repository, so it has to be installed first: it is what supplies
the login, the My Shows lists and the actual video playback — and playing
through it is also what keeps the Profanity Filter working on ororo. On a box
where it is missing, Kodi reports an unmet dependency rather than installing a
browser with nothing to browse.

### Updating this file

1. In `C:\OroroBrowse`, run `python -m unittest discover -s tests`, then
   `python tools/make_zip.py`.
2. Copy the new `dist/plugin.video.ororotv.browse-<version>.zip` over the old
   file here and delete the old one.
3. Update this table and the summary table above.
4. Re-run `python tools/make_release.py` and check the listing.
