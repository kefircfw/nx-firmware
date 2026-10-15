import hashlib
import json
import zipfile

import pytest

import fwstore


def make_nca(folder, payload: bytes, meta=False):
    name = hashlib.sha256(payload).hexdigest()[:32] + ('.cnmt.nca' if meta else '.nca')
    (folder / name).write_bytes(payload)
    return name


def test_ingest_stores_each_nca_once_and_points_to_first_release(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    v1 = tmp_path / 'v1'; v1.mkdir()
    shared = make_nca(v1, b'system module')
    make_nca(v1, b'meta 1', meta=True)
    new1 = fwstore.ingest(root, '1.0.0', v1)
    assert len(new1) == 2

    v2 = tmp_path / 'v2'; v2.mkdir()
    make_nca(v2, b'system module')            # unchanged between versions
    changed = make_nca(v2, b'meta 2', meta=True)
    new2 = fwstore.ingest(root, '2.0.0', v2)
    assert [p.name for p in new2] == [changed]

    m2 = json.loads((root / 'manifests' / '2.0.0.json').read_text())
    where = {n['name']: n['release'] for n in m2['ncas']}
    assert where == {shared: 'fw-1.0.0', changed: 'fw-2.0.0'}
    assert m2['new_in_this_version'] == 1 and m2['nca_count'] == 2

    index = json.loads((root / 'index.json').read_text())
    assert [v['version'] for v in index['versions']] == ['2.0.0', '1.0.0']


def test_ingest_from_zip_moves_new_files_for_upload(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    src = tmp_path / 'src'; src.mkdir()
    name = make_nca(src, b'payload')
    z = tmp_path / 'Firmware.3.0.0.zip'
    with zipfile.ZipFile(z, 'w') as f:
        f.write(src / name, name)
    new = fwstore.ingest(root, '3.0.0', z)
    assert [p.name for p in new] == [name] and new[0].exists()
    assert new[0].parent == root / '.upload' / '3.0.0'


def test_renamed_or_corrupt_nca_is_refused(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    src = tmp_path / 'src'; src.mkdir()
    (src / ('0' * 32 + '.nca')).write_bytes(b'not matching')
    with pytest.raises(SystemExit):
        fwstore.ingest(root, '4.0.0', src)


def test_pending_skips_stored_and_sorts_by_version(tmp_path):
    root = tmp_path / 'repo'; (root / 'manifests').mkdir(parents=True)
    (root / 'manifests' / '9.0.0.json').write_text(json.dumps({'version': '9.0.0', 'ncas': []}))
    src = tmp_path / 'rel.json'
    zip_ = [{'name': 'Firmware.zip'}]
    src.write_text(json.dumps([
        {'tag_name': '10.0.0', 'assets': zip_},
        {'tag_name': '9.0.0', 'assets': zip_},
        {'tag_name': '9.1.0', 'assets': zip_},
        {'tag_name': '9.2.0', 'assets': []},
        {'tag_name': '11.0.0', 'assets': zip_, 'prerelease': True},
    ]))
    assert fwstore.pending(root, src) == ['9.1.0', '10.0.0']
