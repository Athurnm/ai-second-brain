# Releasing

Cutting a new desktop release is three steps: bump the version, tag it, push
the tag. CI (`.github/workflows/build-desktop.yml`) does the rest — it builds
Windows, macOS (universal), and Linux installers, signs the updater artifact,
and publishes a GitHub Release with everything attached.

## 1. Bump the version

Bump the version number in all three places (they must match):

- `desktop/package.json` -> `"version"`
- `desktop/src-tauri/Cargo.toml` -> `[package] version`
- `desktop/src-tauri/tauri.conf.json` -> `"version"`

## 2. Tag it

```bash
git tag desktop-vX.Y.Z
git push origin desktop-vX.Y.Z
```

The tag name must match `desktop-v*` — that's what the `build-desktop.yml`
workflow triggers on.

## 3. CI does the rest

`tauri-apps/tauri-action@v0` runs once per OS in the build matrix
(`windows-latest`, `macos-latest` universal, `ubuntu-22.04`) and each run:

- Builds the platform's installer(s) (`.exe`/`.msi`, `.dmg`/`.app.tar.gz`,
  `.deb`/`.AppImage`).
- Because `bundle.createUpdaterArtifacts` is `true` in `tauri.conf.json`,
  also produces a signed updater artifact + `.sig` for that platform.
- Creates (first job to run) or appends to (later jobs) the GitHub Release
  for the pushed tag, uploading its installers, its updater artifact, and
  merging into the release's `latest.json` — the file
  `plugins.updater.endpoints` in `tauri.conf.json` points at
  (`.../releases/latest/download/latest.json`).

### Required repo secrets

CI signs the updater artifact with the keypair generated locally via
`npx tauri signer generate -w /home/brobri/.tauri/asb-updater.key --password ""`.
The private key never lives in the repo — set these two repo secrets from it:

| Secret | Value |
| :--- | :--- |
| `TAURI_SIGNING_PRIVATE_KEY` | contents of `/home/brobri/.tauri/asb-updater.key` |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | `` (empty — the key was generated with no password) |

The matching public key is already committed in
`src-tauri/tauri.conf.json` (`plugins.updater.pubkey`) — that's what installed
apps use to verify the signature before installing an update, so it's safe to
have in the repo even though the private key is not.

## What users see

Any installed app on `>= 0.2.0` (the first updater-enabled build) checks for
updates automatically and silently on launch, and any time via
**AI Second Brain -> Check for Updates…** in the native menu (that path
surfaces errors as a toast instead of failing silently, since it was asked
for explicitly). When a newer release exists, a banner appears at the top of
the app offering **Update & Restart** or **Later** — "Later" only dismisses
it for the rest of that run, it isn't a permanent opt-out.

Apps older than 0.2.0 have no updater at all, so they will never see this
banner and must be reinstalled manually once.
