# Profanity Filter (Kodi add-on)

A Kodi **service** add-on that mutes bad words in real time during video
playback. It finds the active subtitle (from local files *or* streaming
add-ons such as ororo.tv), scans it against a word list, and mutes the audio
exactly when a bad word is spoken — so you never hear it, and the story stays
intact.

Subtitle **text is never shown on screen**: the add-on only uses the subtitle
data for timing, so you can keep subtitles switched off and profanity never
appears on the display.

Compatible with Kodi 19 (Matrix), 20 (Nexus) and 21 (Omega).

## Why v1.8.0

- **Automatic scene-skipping data.** Scene-skip timestamps can now be fetched
  automatically from a hosted JSON file by **movie title** — no files to copy
  onto the device, which makes scene-skipping usable on a **Google Streamer /
  Android TV box**. The add-on identifies the video from Kodi's metadata
  (`Player.GetItem`, so it works even for opaque `plugin://` streaming URLs) or
  from the file/URL, then downloads its windows from the configured URL
  (default: the `skipdata.json` published with this repo).
- You maintain the data centrally in `skipdata.json`; GitHub Pages serves it and
  the add-on picks up updates automatically.
- Local `.skip.txt` files still work as before and are used as a fallback.

## Why v1.7.1

- **Streaming subtitles are now forced on more reliably.** Enabling an external
  subtitle (e.g. via Google Streamer / ororo) is asynchronous — the source only
  starts delivering the subtitle after the request, sometimes after a delay. The
  add-on now re-requests it inside the retry loop and re-selects the exposed
  track by index until it becomes active, instead of giving up after one try.
  This fixes the "tried to force subtitles on but none became active" message.
- **Clearer diagnostics when no subtitle exists.** The on-screen diagnostic now
  tells you apart the two failure cases: a track existed but wouldn't stay
  enabled, versus the source simply providing **no subtitle at all** for that
  video (in which case muting can't work for that stream).

## Why v1.7.0

- **New: scene skipping.** Beyond muting profanity, the add-on can now *jump
  past* whole scenes you want to avoid — scary, intense or mature moments.
  Scene windows come from simple, offline skip lists you edit yourself (no
  subscription, no external service, nothing to look up at play time).
- Skip lists are matched by movie name and live in
  `special://profile/addon_data/service.profanity.filter/skiplists/`. See
  [Scene skipping](#scene-skipping) below.
- Scene skipping works even when a subtitle can't be found, so it's independent
  of the profanity filter.

## Why v1.6.1

- **Fixes streaming subtitle discovery** (ororo.tv etc.). Subtitle URLs that
  carry a signed query string (e.g. `...vtt?X-Amz-Signature=...`) are now kept
  whole, so the download no longer loses its auth token and fails. The add-on
  also rescans the full Kodi log when the subtitle URL falls outside the most
  recent portion.
- **Diagnose without the log.** A new **"Show detailed failure diagnostics"**
  setting pops up exactly which stage failed (player id, whether subtitles
  became active, URL/download/parse results) so you can report the issue
  straight from the screen.
- **Subtitles already on? Capture, then hide.** If you keep subtitles switched
  on by default, the add-on now just reads the subtitle that's already showing,
  then hides the display — no fragile "force subtitles on" needed. If subtitles
  are off, it still briefly enables them for streaming sources and restores
  your preference afterwards.

## Why v1.6.0

- **No subtitles on screen.** The filter works with subtitles switched off.
  Local files are read from disk directly (never displayed); streaming
  subtitles are only enabled long enough to capture the timing data, then
  hidden again. The old "Hide subtitles after scanning" toggle is gone —
  profanity text is always kept off the screen.
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

## Troubleshooting: streaming content shows "No subtitle found"

1. Enable **Add-ons → Profanity Filter → Configure → Show detailed failure
   diagnostics**.
2. Play the video. If the filter still fails, a yellow "PF Diagnose" bubble
   shows the exact failing stage, e.g.:
   - `...none became active` → forcing subtitles on didn't engage a track; the
     add-on now retries this automatically, so check whether this keeps
     happening on this specific video/source
   - `No subtitle track exposed by this source` → the streaming source provides
     **no subtitle at all** for this video, so there is nothing to scan and mute
   - `...track(s) exposed but none became active` → the source has a subtitle
     but it wouldn't switch on
   - `no URL found (JSON-RPC + log scan)` → no subtitle URL detected
   - `URL found but download failed` → the subtitle was found but couldn't be
     fetched
   - `...parsed to 0 cues` → the subtitle downloaded but couldn't be read
3. If the bubble is cut off, enable Kodi's debug logging (**Settings → System →
   Logging → Enable debug logging**) and look for lines starting with
   `[ProfanityFilter]` in `kodi.log` (`special://logpath/`).

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

## Scene skipping

The add-on can also **jump past whole scenes** you don't want shown (scary
moments, intense violence, mature content) rather than just muting words.

1. Turn it on: **Add-ons → Profanity Filter → Configure → Scene skipping →
   Enable scene skipping**.

### Automatic (hosted JSON — no files on the TV)

This is the recommended way on a Google Streamer / Android TV box where you
can't easily add files. The add-on **identifies the movie** (from Kodi's
metadata, or the file/URL for local content) and downloads its scene timings
from a single hosted JSON file — you edit it in the repo, GitHub Pages serves
it, and every device pulls it automatically.

- The URL is set in **Scene skipping → Hosted skip-data URL** and defaults to
  the one published with this repo (`skipdata.json` on the Pages site).
- Edit `/skipdata.json` in this repository. Keys are **lowercase movie
  titles**, each holding a list of `{ "start", "end" }` scene windows (times as
  `"h:mm:ss"`, `"m:ss"`, or plain seconds). An optional `"default"` key applies
  to every video:

  ```json
  {
    "version": 1,
    "skipdata": {
      "avatar (2009)": [
        { "start": "1:03:45", "end": "1:03:56" },
        { "start": "1:20:28", "end": "1:20:42" }
      ],
      "default": [
        { "start": "00:15:00", "end": "00:15:30" }
      ]
    }
  }
  ```

  The `skipdata.json` file is copied to the Pages site on every release, so the
  add-on always sees your latest update — no add-on reinstall needed.

### Local files (alternative)

If you prefer to keep the list on the device instead: in Kodi's file manager,
go to `special://profile/addon_data/service.profanity.filter/skiplists/` and add
a file **named after the movie** (e.g. `Avatar (2009).skip.txt`) — or
`global.skip.txt` to apply to everything. In that file, put one scene per line,
`START  END`:

```
00:05:30  00:06:15    # skip 5:30 to 6:15
1:23:45   1:24:30     # skip near the end
42.0      45.5        # plain seconds work too
```

`#` starts a comment. Matching is on the video's title/file name and is
case-insensitive. A bundled example is at
`service.profanity.filter/resources/skiplists/global.skip.txt.example`.

### How it behaves

When playback gets within the **Skip-start lookahead** (default 10 s) of a
flagged scene, the add-on jumps to the end of that window. This happens
independently of profanity muting and works even when no subtitle is found.

Useful when hiding from scary/mature content for kids.

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
