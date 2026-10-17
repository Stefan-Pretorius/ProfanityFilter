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

Amazon VOD declares seven requirements. Four come from Kodi's official
repository, which is enabled on every installation and is where they should stay
— duplicating them here would risk a stale copy of ours being installed in place
of a newer official one:

`script.module.beautifulsoup4`, `script.module.requests`, `script.module.pyxbmct`,
`script.module.inputstreamhelper`

The other three exist **only** in Sandmann79's index, so they are mirrored here
too, otherwise Kodi could not satisfy the dependency and the install would fail
with an unmet dependency:

| Module | Version | SHA-256 | Licence |
|---|---|---|---|
| `script.module.amazoncaptcha` | 0.5.11+matrix.1 | `bb0ad30c96d97268e0c7ec26731bc6ee35eca3dd66e7e13e191e4dbf3562d0ae` | MIT |
| `script.module.mechanicalsoup` | 1.0.0+matrix.1 | `3d8870081a2e03ae0ded83d05051fcfad379f320fff0b64bbfc11bea3fdecd7e` | MIT |
| `script.module.pyautogui` | 0.9.51+matrix.1 | `1d0ae84f81993631c4116dbda9b61c1199b40689c7e47d6c31a5ba1d51aa873a` | BSD-3-Clause |

A test (`test_every_amazon_vod_requirement_is_resolvable`) reads these
requirements out of the mirrored zip and fails if Amazon VOD ever grows one that
is neither published here nor on the known list of official add-ons — which is
the way this arrangement would otherwise rot silently.

### Updating these five files

```sh
python tools/vendor_sandmann.py
```

That verifies Sandmann79's index checksum, downloads the current version of each,
refuses to publish anything whose declared id/version does not match the index,
deletes the superseded file, and prints the new sizes and checksums. Then update
the tables above and re-run `python tools/make_release.py`.

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

So the five files needed to install Amazon VOD are published here too, served
from `stefan-pretorius.github.io` — the same host the filter itself already
installs from, which is known to work from that box. The pointer stays listed as
well, so both routes are available: one-click install from here, and upstream
updates for anyone who installs the nested repository. Kodi installs the newest
version offered by any enabled repository, so the two do not conflict.

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
