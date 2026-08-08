# Profanity Filter (Kodi add-on)

A Kodi **service** add-on that mutes bad words in real time during video
playback. It finds the active subtitle (from local files *or* streaming
add-ons such as ororo.tv), scans it against a word list, and mutes the audio
exactly when a bad word is spoken — so you never hear it, and the story stays
intact.

Compatible with Kodi 19 (Matrix), 20 (Nexus) and 21 (Omega).

## Why v1.5.0

- **No more false positives.** Wildcards are now *single-character* masks, so
  `sh*t` matches `shit` but no longer `shift` / `sheet` / `shout`, and `c*nt`
  no longer matches `count`.
- **Curated word list.** The bundled `resources/filter.txt` contains only
  strong, unambiguous profanity. Common/story-critical words like *god*,
  *hell*, *abuse*, *naked* and *sex* are **not** muted by default. The old
  2,750-word list is kept in the repo as `filter-full.txt` for reference.
- Subtitles are discovered using Kodi's *active video player* instead of a
  hardcoded player id.

## Install (one time)

1. On the TV in Kodi: **Settings → System → Add-ons → Unknown sources → ON**.
2. **File manager → Add source → `<none>`** and enter:
   `https://stefan-pretorius.github.io/ProfanityFilter/`
   Give it a name (e.g. `ProfanityFilter`).
3. **Settings → Add-ons → Install from zip file** → browse to that source →
   install `repository.profanityfilter-1.0.0.zip`.
4. **Install from repository → Profanity Filter Repository → Profanity
   Filter → Install.**

No phone, no USB, no shared folders.

## Updates

Once the repository is installed, Kodi's add-on manager checks it
automatically. Whenever a new version is tagged in this repository, the
workflow builds and publishes it to the same URL — Kodi downloads and
installs the update itself (or you can press **Check for updates** manually).

## Manual install (alternative)

Grab `service.profanity.filter-<version>.zip` from the
[Releases](../../releases) page and install it via
**Settings → Add-ons → Install from zip file**.

## Customising the word list

Edit `service.profanity.filter/resources/filter.txt`. Lines starting with `#`
are comments. The file has optional tiers (mild profanity, anatomical terms,
slurs) that are disabled by default — uncomment lines to enable them.

- Matching is **case-insensitive** and **whole-word** (`ass` never matches
  `class`, `pass` or `assessment`).
- `*` is a wildcard for a **single** character: `sh*t` → `shit`, `shut`, `shat`.

## Releasing a new version

1. Bump `version` in `service.profanity.filter/addon.xml`.
2. Commit and push.
3. Tag and push — everything else is automated:

```sh
git tag v1.6.0
git push --tags
```

The workflow builds the zips, attaches them to a GitHub Release, and updates
the GitHub Pages repository (Kodi then updates automatically).

## Repository layout

```
service.profanity.filter/     # the add-on itself
  addon.xml                   # bump version here
  service.py                  # Kodi service entry point
  resources/filter.txt        # the word list you can edit
  resources/lib/              # parsers, matcher, mute controller
repository.profanityfilter/   # repo add-on (installed once)
tools/make_release.py         # builds zips + addons.xml locally
.github/workflows/release.yml # builds + publishes on every v* tag
filter-full.txt               # old 2,750-word list (reference only)
```

## License

GPL-2.0-or-later. See [LICENSE](LICENSE).
