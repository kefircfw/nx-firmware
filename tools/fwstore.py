"""Firmware NCA store: every NCA once, a manifest per firmware version.

Layout of this repo:
  index.json                 all versions, newest first
  manifests/<version>.json   the NCAs of one version, each with the release that holds it
  release fw-<version>       assets = the NCAs that first appeared in that version

An NCA's file name is its content id (the first 16 bytes of its SHA-256), so the name already
identifies the content; the manifest keeps the full SHA-256 and the size for checking downloads.

Commands:
  pending  --source-json <file>      versions in the source list that are not in index.json, oldest first
  ingest   <version> <dir|zip>       write manifests/<version>.json, print the new NCA paths (one per line)
  index                              rebuild index.json from manifests/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = 'manifests'
RELEASE_PREFIX = 'fw-'
SOURCE = 'THZoria/NX_Firmware'
NCA_NAME = re.compile(r'^[0-9a-f]{32}(\.cnmt)?\.nca$')


def version_key(v: str):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r'[.\-]', v))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_manifests(root: Path) -> dict:
    out = {}
    for p in sorted((root / MANIFESTS).glob('*.json')):
        m = json.loads(p.read_text(encoding='utf-8'))
        out[m['version']] = m
    return out


def known_ncas(manifests: dict) -> dict:
    """sha256 -> release tag that holds it."""
    return {n['sha256']: n['release'] for m in manifests.values() for n in m['ncas']}


def collect_ncas(folder: Path) -> list:
    files = [p for p in folder.rglob('*') if p.is_file()]
    ncas = [p for p in files if NCA_NAME.match(p.name.lower())]
    if not ncas:
        raise SystemExit(f'no NCA files in {folder}')
    return sorted(ncas, key=lambda p: p.name.lower())


def ingest(root: Path, version: str, src: Path) -> list:
    """Writes the manifest of `version`; returns the NCA files to upload to its release."""
    manifests = load_manifests(root)
    if version in manifests:
        raise SystemExit(f'{version} is already in the store')
    tmp = None
    if src.is_file():
        tmp = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp.name)
        src = Path(tmp.name)
    known = known_ncas(manifests)
    release = RELEASE_PREFIX + version
    entries, new = [], []
    for p in collect_ncas(src):
        digest = sha256_file(p)
        if not digest.startswith(p.name[:32].lower()):
            raise SystemExit(f'{p.name}: name does not match its SHA-256 ({digest[:32]})')
        holder = known.get(digest)
        if holder is None:
            holder = release
            known[digest] = release
            new.append(p)
        entries.append({'name': p.name.lower(), 'size': p.stat().st_size, 'sha256': digest, 'release': holder})
    manifest = {
        'version': version,
        'source': f'{SOURCE}@{version}',
        'nca_count': len(entries),
        'size': sum(e['size'] for e in entries),
        'new_in_this_version': len(new),
        'ncas': entries,
    }
    (root / MANIFESTS).mkdir(exist_ok=True)
    (root / MANIFESTS / f'{version}.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    write_index(root)
    if tmp:
        # the caller uploads the new files: keep them in a stable place next to the repo
        keep = root / '.upload' / version
        keep.mkdir(parents=True, exist_ok=True)
        moved = []
        for p in new:
            dst = keep / p.name.lower()
            p.replace(dst)
            moved.append(dst)
        tmp.cleanup()
        new = moved
    return new


def write_index(root: Path):
    manifests = load_manifests(root)
    versions = sorted(manifests.values(), key=lambda m: version_key(m['version']), reverse=True)
    index = {
        'format': 1,
        'download': 'https://github.com/kefircfw/nx-firmware/releases/download/{release}/{name}',
        'manifest': 'https://raw.githubusercontent.com/kefircfw/nx-firmware/main/manifests/{version}.json',
        'versions': [{'version': m['version'], 'nca_count': m['nca_count'], 'size': m['size']} for m in versions],
    }
    (root / 'index.json').write_text(json.dumps(index, indent=1) + '\n', encoding='utf-8')


def pending(root: Path, source_json: Path) -> list:
    """Source versions (gh api releases JSON: [{tag_name, assets:[{name}]}]) missing from the store."""
    have = set(load_manifests(root))
    releases = json.loads(source_json.read_text(encoding='utf-8'))
    out = []
    for r in releases:
        tag = r['tag_name'].strip()
        if tag in have or r.get('draft') or r.get('prerelease'):
            continue
        if any(a['name'].lower().endswith('.zip') for a in r.get('assets', [])):
            out.append(tag)
    return sorted(out, key=version_key)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pending'); p.add_argument('--source-json', type=Path, required=True)
    p = sub.add_parser('ingest'); p.add_argument('version'); p.add_argument('src', type=Path)
    sub.add_parser('index')
    ap.add_argument('--root', type=Path, default=ROOT)
    a = ap.parse_args(argv)
    if a.cmd == 'pending':
        print('\n'.join(pending(a.root, a.source_json)))
    elif a.cmd == 'ingest':
        for f in ingest(a.root, a.version, a.src):
            print(f)
    else:
        write_index(a.root)


if __name__ == '__main__':
    sys.exit(main())
