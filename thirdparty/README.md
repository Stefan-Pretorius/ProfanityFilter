# Vendored add-ons

These zips are not built from source in this repository. They are copied
verbatim from elsewhere and re-published, unchanged, so that a Kodi box can
install everything it needs from this repository alone.

One of them is this author's own add-on, developed in a separate repository;
the other is third-party. Provenance and licence are recorded for both below.

## plugin.video.ororotv.browse-1.0.0.zip

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
is not in this repository, so it has to be installed first (it is what supplies
the login, the My Shows lists and the actual video playback); on a box where it
is missing, Kodi will report an unmet dependency rather than install a browser
with nothing to browse.

### Updating this file

1. In `C:\OroroBrowse`, run `python -m unittest discover -s tests`, then
   `python tools/make_zip.py`.
2. Copy the new `dist/plugin.video.ororotv.browse-<version>.zip` over the old
   file here and delete the old one.
3. Update this table's version, size, SHA-256 and the filename in
   `BUNDLED_ADDONS` in `tools/make_release.py`.
4. Re-run `python tools/make_release.py` and check the listing.

## repository.sandmann79.plugins-1.0.4.zip

| | |
|---|---|
| What it is | The Kodi *repository* add-on for Sandmann79's add-ons, which is how Kodi installs and updates **Amazon VOD** (`plugin.video.amazon-test`). |
| Upstream | https://github.com/Sandmann79/xbmc |
| Upstream release | https://github.com/Sandmann79/xbmc/releases/tag/Repository (release "Plugin Repository v1.0.4") |
| Download URL | https://github.com/Sandmann79/xbmc/releases/download/Repository/repository.sandmann79.plugins-1.0.4.zip |
| Size | 766 bytes |
| SHA-256 | `95ced51a9ce7f1732e132a4c51fdbe31e0f330f4728fc29085194d0f7adb8aeb` |
| Licence | GPL-3.0 |

This add-on is a **repository pointer, not the Amazon VOD code itself**. Its
`addon.xml` declares two `<dir>` blocks; Kodi 19+ uses the second one:

```xml
<dir minversion="18.9.0">
  <info compressed="false">https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/addons.xml</info>
  <checksum>https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/addons.xml.md5</checksum>
  <datadir zip="true">https://raw.githubusercontent.com/Sandmann79/xbmc/master/packages-py3/</datadir>
</dir>
```

Because it points at Sandmann79's live index, Amazon VOD still updates
directly from upstream: this copy only has to change if Sandmann79 changes
the repository URL or the `minversion` gating, and the current 1.0.4 is the
newest release of it.

We deliberately do **not** vendor Amazon VOD itself. It requires eight
modules, three of which (`script.module.mechanicalsoup`,
`script.module.pyautogui`, `script.module.amazoncaptcha`) exist only in
Sandmann79's repository - so a copy here would need four add-ons kept in
step by hand, and would silently go stale. Bundling the 766-byte repository
pointer instead gives one-place installation *and* automatic updates.

### Why bundle it at all

Installing the filter on a TV means typing a URL into Kodi's file manager.
Having this repository add-on served from the same place means the Amazon VOD
step is done entirely from Kodi's add-on browser, with no second URL to find.

### Updating this file

1. Check for a newer release: https://github.com/Sandmann79/xbmc/releases
   (the release tagged `Repository`). Most releases do not change it.
2. Download the new `repository.sandmann79.plugins-<version>.zip`.
3. Replace the file here, remove the old one, and update this table and
   `BUNDLED_ADDONS` in `tools/make_release.py` if the version changed.
4. Re-run `python tools/make_release.py` and check the listing.
