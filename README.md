# Profanity Filter (Kodi add-on)

A Kodi **service** add-on that mutes bad words in real time during video
playback. For every video that starts it:

1. **reads** the subtitle from the source (ororo.tv, Amazon VOD / Prime Video,
   other streaming add-ons, or a local file),
2. **hides** the subtitle from the screen, and
3. **mutes** the audio exactly when a bad word is spoken.

The subtitle is only ever used as a *data source* for timing. Once it has been
read it is switched off and stays off for the rest of the video, so you never
see profanity (or any other subtitle text) on the display and the story stays
intact.

Compatible with Kodi 19 (Matrix), 20 (Nexus) and 21 (Omega).

## How it finds the subtitle

For every video the add-on tries four sources in order of reliability, and
tells you on screen which one worked:

1. **The ororo.tv API.** ororo hands Kodi the subtitle under a human-readable
   name such as `clarksons farm s01e01 (External)`, *not* as an address, and
   it only writes that address to `kodi.log` at debug level. So on a box with
   normal logging there is no address anywhere to be found. The add-on
   therefore asks the ororo add-on directly for the subtitle list, reusing the
   login already saved in that add-on, and tries both ororo front-end domains
   so a dead mirror does not stop it.
2. **The player.** For sources that do hand Kodi a real subtitle address.
3. **The Amazon VOD proxy.** Amazon VOD (Prime Video) does not hand Kodi an
   address either. It fetches the subtitle from Amazon, then serves every track
   through a small local proxy of its own and tells Kodi only that the track is
   `(External)`. The add-on reads the proxy's address and the subtitle requests
   it logs, then asks the proxy for the English subtitle directly. The proxy
   signs in to Amazon itself, so no extra credentials are needed or stored. This
   does mean the Amazon VOD add-on's own **`logging`** option has to be on,
   because that is what makes its subtitle requests visible.
4. **Kodi's log.** Last resort only — see above.

These are the reasons the filter works on ororo.tv and on Prime Video.

## Which subtitle language is used

The filter always switches to the **English** subtitle rather than whichever
track happens to be listed first. Muting is timed off the subtitle, so on a
title whose first track is Danish (or French, or German) reading the wrong
language means muting at the wrong moments. A track marked *forced* — which
only translates the odd line of foreign dialogue — is used only as a last
resort.

## Why ordinary words are no longer muted

An earlier build muted far too much of the film, for two separate reasons,
both confirmed by testing rather than guessed at:

- **Wildcards were matching too much.** A wildcard here means "any number of
  characters", so `sh*t` also matched *shot*, *shut*, *shoes* and *sheet*,
  `c*nt` also matched *cent*, *content* and *count*, and `d*ck` also matched
  *duck*. `*` now matches exactly one character, and the shipped word list no
  longer uses wildcards at all — every real spelling is written out in full.
- **Words with an innocent meaning were on the list.** `ass` (a donkey), `dick`
  (a first name), `cock` (a bird), `crap`, `anal`, `tits`, `pissed`, `slut` and
  `horny` were all being treated as profanity, which is how `Dick` and `cock`
  ended up muted mid-sentence. All of them now live in an optional tier that is
  off by default.

Every entry in the active tier is either a word that does not exist in ordinary
English, or one that exists but is never used innocently. Coverage went *up* at
the same time — ~308 active entries including the spelling variants and
subtitled forms (`fukker`, `mfucker`, `sh1t`, `b1tch`, `mothafucker`) that were
missing before.

## Religious exclamations (blasphemy)

The religious oaths are muted, but only in their **oath form**. *Oh my God*,
*My God*, *Oh God*, *Jesus*, *Jesus Christ*, *For Christ's sake*, *God damn it*
and *What the hell* are all filtered.

The bare words are deliberately not. *Thank God*, *God bless*, *God's will*,
*God's own country*, *Christmas*, a character called *Godfrey* and *Godzilla*
are all left audible, because muting every mention of God makes a film harder to
follow — which is the exact problem this list was rebuilt to fix. If you want
every single one muted, uncomment `god` and `hell` in the optional tier at the
bottom of `filter.txt`.

One trade-off is worth knowing: an apostrophe counts as a word boundary, so
`jesus` also matches the possessive *Jesus'* as in *in Jesus' name*. That is left
alone on purpose, because suppressing it would also stop *shit's* and
*bastard's*, which matters much more. Comment out the bare `jesus` line if you
would rather not have it.

## Other behaviour worth knowing

- **Always request the subtitle, always wait for it.** Earlier versions skipped
  the wait when subtitles happened to already be switched on, so the scan could
  start before the source had handed anything over. The add-on now always asks
  the source to deliver its subtitle and always gives it time to arrive.
- **Subtitles are hidden as soon as the data has been read**, whether or not any
  bad words were found.
- **One loop, not two.** Muting and keeping the subtitles hidden now run in a
  single loop, so they can no longer interfere with each other on sources that
  keep flipping subtitles back on.
- **Starting a new video is never skipped.** Stopping one video and starting
  another quickly used to leave the new video unfiltered.
- Music and other non-video playback is ignored.
- Scene skipping was removed; the add-on filters profanity only.

## Install (one time)

1. On the TV in Kodi: **Settings → System → Add-ons → Unknown sources → ON**.
2. **File manager → Add source → `<none>`** and enter (note the trailing slash):
   `https://stefan-pretorius.github.io/ProfanityFilter/`
   Give it a name (e.g. `ProfanityFilter`).
3. **Settings → Add-ons → Install from zip file** → browse to that source → the
   listing shows real filenames (e.g. `repository.profanityfilter-1.0.3.zip`) →
   select it and install.
4. **Install from repository → Profanity Filter Repository → Profanity
   Filter → Install.**

That is the filter done. No phone, no USB, no shared folders.

### Everything else from the same place

The same repository also carries the rest of what this setup needs, so there is
no second URL to find or keep track of.

**Amazon VOD (Prime Video)**

5. **Install from repository → Profanity Filter Repository → Video add-ons →
   Amazon VOD → Install.** Kodi fetches the four remaining modules it needs
   from its own repository by itself, so this is a single click.
6. Open Amazon VOD once and sign in with the account that holds the Prime
   subscription (the phone-number account, not the e-mail-only one), then switch
   on its **logging** option — the filter needs that to find the subtitle. See
   [How it finds the subtitle](#how-it-finds-the-subtitle).

Amazon VOD is included here rather than pointed at, because the pointer alone
does not work reliably: it is an add-on whose only job is to fetch a second
index from `raw.githubusercontent.com`, and until that second fetch happens the
nested repository is empty — no Amazon VOD, no error message, nothing. What is
published here instead is Sandmann79's own release, unchanged, served from the
same host as the filter.

If you would rather have Amazon VOD update straight from upstream as well, step
5b is optional: **Add-on repository → Sandmann79s Repository → Install**. Then
Kodi offers whichever of the two routes has the newer version.

**Ororo TV Browse**

7. Install the **Ororo TV** add-on itself (`plugin.video.ororotv`) and sign in
   first. Ororo TV Browse reuses that login, shares its My Shows list and plays
   through it — which is also what keeps the filter working on ororo.
8. **Install from repository → Profanity Filter Repository → Video add-ons →
   Ororo TV Browse → Install.**

Ororo TV Browse gives ororo.tv a Netflix-style front end: featured rows for the
home screen, poster walls with full metadata, A–Z / genre / year / rating
navigation, and combined search over films and TV shows. It is developed in
[its own repository](https://github.com/Stefan-Pretorius/OroroBrowse) and
published here unchanged.

[thirdparty/README.md](thirdparty/README.md) records the exact version, size,
SHA-256 and licence of each bundled add-on, and how to refresh them.

## Updates

Once the repository is installed, Kodi's add-on manager checks it
automatically. Whenever a new version is tagged in this repository, the
workflow builds and publishes it to the same URL — Kodi downloads and
installs the update itself (or you can press **Check for updates** manually).

### It engages late, by design

The subtitle is only readable once the source has delivered it, so the filter
arms a few seconds into playback. **Profanity in roughly the first 10–15 seconds
of a film cannot be muted** — by the time the subtitle arrives, the line has
already been spoken. To arm sooner, lower **Subtitles → Subtitle scan delay**
(default 10 s); to arm later and catch more, raise it.

For the same reason, subtitle timing is approximate. **Timing → Pre-word buffer**
and **Post-word buffer** widen the mute window around each word (default 0.3 s
each side). Raise them if you can still hear the start or end of a word. If a
word is consistently unmuted rather than clipped at the edges, the subtitle is
out of sync and no buffer size will fully fix it.

## Seeing what the add-on is doing

Every video produces a short result at the **top of the screen**. Nothing waits
for you to press OK, so the film is never interrupted:

> **Profanity Filter:** 18 bad word(s) in 1001 lines - 17 mute(s), subtitles hidden

It is one short line, ending in one of:

- `FILTER ACTIVE` — bad words were found and will be muted
- `CLEAN` — subtitle read and hidden, no bad words in it
- `NO SUBTITLE` — the source provides no subtitle, so there is nothing
  to scan (this is the one case where muting is not possible)
- `FAILED` — something went wrong; the full report says what

Music is not announced at all — it was never filtered, so a message about it is
just noise.

Controls live in **Add-ons → My add-ons → Profanity Filter → Configure**:

| Setting | Default | Purpose |
| --- | --- | --- |
| Troubleshooting → Show a report on screen for every video | on | The result itself |
| Troubleshooting → Report waits for me to press OK | off | Opt back into the full report in a dialog that stays up until dismissed |
| Notifications → Show short notifications too | on | Brief "starting" status line |

Turn the report off once things are working.

The **full** report — every line, including the player id, the word list size and
the reason if something failed — is written to `report.txt` in the add-on's data
folder (`special://profile/addon_data/service.profanity.filter/report.txt`),
which means you do not have to pull `kodi.log` off a device you cannot easily
reach. Turn on the *Report waits for me to press OK* setting to see that same
full report on screen.

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
**Settings → Add-ons → Install from zip file**. The same page carries every
bundled add-on — Amazon VOD and its modules, Sandmann79's repository pointer and
Ororo TV Browse — if you would rather install those from a file than from the
repository above.

## Customising the word list

Edit `service.profanity.filter/resources/filter.txt`. Lines starting with `#`
are comments. The file has optional tiers (mild profanity, anatomical terms,
slurs) that are disabled by default — uncomment lines to enable them.

- Matching is **case-insensitive** and **whole-word** (`ass` never matches
  `class`, `pass` or `assessment`).
- `*` is a wildcard for a **single** character, so `sh*t` matches `shit`,
  `shut` and `shat` — but never `shift`, `sheet` or `shout`.
- **Wildcards are blunt, so the shipped list uses none.** `sh*t` still mutes
  the harmless *shot* and *shut*; `c*nt` still mutes *cent*. If you add a
  wildcard yourself, check it against everyday words before saving.
- **Multi-word entries tolerate punctuation between the words**, because
  subtitles punctuate exclamations: the entry `oh god` matches *Oh, God* and
  *Oh... God*. The gap may not contain letters, so `to hell` still does not
  match *to me about hell*.
- Words with a common innocent meaning (`ass`, `dick`, `cock`, `crap`, `anal`)
  are deliberately **not** active. Uncomment them in the optional tiers if you do
  want them. `god` and `hell` are also opt-in, because the oath forms of those
  words are already active — see [Religious exclamations](#religious-exclamations-blasphemy).

`filter-full.txt` in the repository root is the original 2,750-word list, kept
as a reference only. It mutes far too much ordinary dialogue — the header
inside that file explains exactly which entries cause it and why.

## Running the tests

The subtitle-discovery helpers (including the Amazon VOD proxy parsing) are
covered by unit tests that need no Kodi install:

```sh
python -m unittest discover -s tests
```

These live in `tests/` and are not part of the released add-on. They also cover
the release packaging, including the one rule that decides whether Kodi can
install anything from this repository at all: an add-on zip has to be published
at `<repository>/<addon id>/<addon id>-<version>.zip`.

## Releasing a new version

1. Bump `version` in `service.profanity.filter/addon.xml`, and in
   `repository.profanityfilter/addon.xml` if the repository add-on itself changed
   (for example to carry another repository).
2. Commit and push.
3. Tag and push — everything else is automated:

```sh
git tag v1.12.1
git push --tags
```

The workflow builds the zips, attaches them to a GitHub Release — the filter,
this repository add-on, and every bundled add-on (Amazon VOD and its modules,
Amazon VOD's repository pointer, and Ororo TV Browse) — and updates the GitHub
Pages repository (Kodi then updates automatically).

To see what will be published first, run it locally:

```sh
python tools/make_release.py     # writes dist/ and dist/gh-pages/
```

## Repository layout

```
service.profanity.filter/     # the add-on itself
  addon.xml                   # bump version here
  service.py                  # Kodi service entry point
  resources/filter.txt        # the word list you can edit
  resources/lib/              # parsers, matcher, mute controller, amazon_vod
repository.profanityfilter/   # repo add-on (installed once)
thirdparty/                   # bundled add-ons, discovered as thirdparty/*.zip:
                              #   Amazon VOD + its 3 private modules, Sandmann79's
                              #   repository pointer, Ororo TV Browse
tests/                        # pure-Python unit tests (not shipped)
tools/make_release.py         # builds zips + addons.xml locally
tools/vendor_sandmann.py      # refreshes the mirrored Amazon VOD files
.github/workflows/release.yml # builds + publishes on every v* tag
filter-full.txt               # archived 2,750-word list (reference only)
```

### How the repository is laid out for Kodi

Kodi derives an add-on's download address as
`<datadir>/<addon id>/<addon id>-<version>.zip` (this is also how the official
Kodi mirrors are arranged). A zip placed anywhere else — for example under a
`<addon id>/<version>/` sub-folder — is never requested, and the install or
update fails with no clear reason. `tests/test_release_packaging.py` pins this
rule down so it cannot regress.

## License

GPL-2.0-or-later. See [LICENSE](LICENSE).
