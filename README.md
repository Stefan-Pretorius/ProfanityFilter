# Profanity Filter (Kodi add-on)

A Kodi **service** add-on that mutes bad words in real time during video
playback. For every video that starts it:

1. **reads** the subtitle from the source (ororo.tv, other streaming add-ons,
   or a local file),
2. **hides** the subtitle from the screen, and
3. **mutes** the audio exactly when a bad word is spoken.

The subtitle is only ever used as a *data source* for timing. Once it has been
read it is switched off and stays off for the rest of the video, so you never
see profanity (or any other subtitle text) on the display and the story stays
intact.

Compatible with Kodi 19 (Matrix), 20 (Nexus) and 21 (Omega).

## Why v1.9.0

Scene skipping is gone, and the add-on is now focused purely on filtering
profanity. The flow is deliberately the same three steps for every video, which
is what makes it work reliably on **ororo.tv**:

- **Always request the subtitle, always wait for it.** Earlier versions skipped
  the wait when subtitles happened to already be switched on, so the scan could
  start before the source had handed anything over. The add-on now always asks
  the source to deliver its subtitle and always gives it time to arrive.
- **Only look at log entries from the current video.** The subtitle URL is
  recovered from `kodi.log`. Only lines written since this video started
  playing are considered, so a subtitle URL left over from a *previous* video
  can no longer be scanned instead of this one.
- **Subtitles are hidden as soon as the data has been read**, whether or not any
  bad words were found.
- **One loop, not two.** Muting and keeping the subtitles hidden now run in a
  single loop, so they can no longer interfere with each other on sources that
  keep flipping subtitles back on.
- **Starting a new video is never skipped.** Stopping one video and starting
  another quickly used to leave the new video unfiltered.
- Music and other non-video playback is ignored.

## Install (one time)

1. On the TV in Kodi: **Settings → System → Add-ons → Unknown sources → ON**.
2. **File manager → Add source → `<none>`** and enter (note the trailing slash):
   `https://stefan-pretorius.github.io/ProfanityFilter/`
   Give it a name (e.g. `ProfanityFilter`).
3. **Settings → Add-ons → Install from zip file** → browse to that source → the
   listing shows real filenames (e.g. `repository.profanityfilter-1.0.0.zip`) →
   select it and install.
4. **Install from repository → Profanity Filter Repository → Profanity
   Filter → Install.**

No phone, no USB, no shared folders.

## Updates

Once the repository is installed, Kodi's add-on manager checks it
automatically. Whenever a new version is tagged in this repository, the
workflow builds and publishes it to the same URL — Kodi downloads and
installs the update itself (or you can press **Check for updates** manually).

## Troubleshooting: the filter doesn't seem to do anything

1. Enable **Add-ons → Profanity Filter → Configure → Show detailed failure
   diagnostics**.
2. Play the video. If the filter still fails, a yellow "PF Diagnose" bubble
   shows the exact failing stage, e.g.:
   - `No subtitle track exposed by this source` → the source provides **no
     subtitle at all** for this video, so there is nothing to scan and mute
   - `...track(s) exposed but none became active` → the source has a subtitle
     but it wouldn't switch on
   - `no URL found (JSON-RPC + log scan)` → no subtitle URL detected
   - `URL found but download failed` → the subtitle was found but couldn't be
     fetched
   - `...parsed to 0 cues` → the subtitle downloaded but couldn't be read
3. Check the **on-screen notifications** first. The add-on reports each step:
   *N word(s) will be muted*, *No bad words found*, *No subtitle found*.
4. If the bubble is cut off, enable Kodi's debug logging (**Settings → System →
   Logging → Enable debug logging**) and look for lines starting with
   `[ProfanityFilter]` in `kodi.log` (`special://logpath/`).

### Tuning

- **Timing → Pre-word buffer / Post-word buffer** widen the mute window around
  each word. Raise these if a word is still partly audible.
- **Subtitles → Subtitle scan delay** is how long the source gets to deliver the
  subtitle after we request it. Raise it on slow streaming add-ons.
- **Subtitles → Subtitle search retries** is how many times discovery is
  attempted. Each retry takes a few seconds, so a video can take a while before
  the filter activates.

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
- `*` is a wildcard for a **single** character: `sh*t` → `shit`, `shut`, `shat`
  — but never `shift`, `sheet` or `shout`.

## Releasing a new version

1. Bump `version` in `service.profanity.filter/addon.xml`.
2. Commit and push.
3. Tag and push — everything else is automated:

```sh
git tag v1.9.0
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
