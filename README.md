# nx-firmware

Nintendo Switch firmware as single NCA files, each stored once. Kefir Hub downloads only the NCAs a
console is missing for an update or a downgrade, and checks each one by its SHA-256.

Source: [THZoria/NX_Firmware](https://github.com/THZoria/NX_Firmware). The `sync` workflow runs daily and
adds every new version; the first runs fill the store with all versions.

## Layout

| Path | What |
|---|---|
| `index.json` | All versions, newest first, plus URL templates |
| `manifests/<version>.json` | Every NCA of that version: `name`, `size`, `sha256`, `release` |
| Release `fw-<version>` | The NCAs that first appeared in that version |

Download one NCA: `https://github.com/kefircfw/nx-firmware/releases/download/<release>/<name>`.
An NCA's name is its content id, the first 32 hex digits of its SHA-256.

## Tools

```
python tools/fwstore.py ingest <version> <folder|zip>   # add a version locally
python -m pytest tools                                  # tests
```
