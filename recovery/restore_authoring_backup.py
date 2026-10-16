"""Verify/restore the optional private authoring archive. Never overwrite a directory."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import zipfile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_relative(name):
    p = PurePosixPath(name)
    if p.is_absolute() or not p.parts or any(x in {'..', '.'} or ':' in x or '\\' in x for x in p.parts):
        raise ValueError('Unsafe archive path: ' + name)
    return Path(*p.parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, required=True)
    ap.add_argument('--sha256', required=True, help='Expected complete ZIP hash from the handoff')
    ap.add_argument('--output', type=Path, help='New directory; omit to verify only')
    ap.add_argument('--restore-history', action='store_true', help='Also reconstruct historical disc/card outputs')
    ap.add_argument('--source-bin', type=Path)
    ap.add_argument('--source-bios', type=Path)
    ap.add_argument('--xdelta', type=Path)
    args = ap.parse_args()
    if sha(args.archive) != args.sha256.lower():
        raise ValueError('Archive SHA-256 mismatch')
    with zipfile.ZipFile(args.archive) as archive:
        manifest = json.loads(archive.read('AUTHORING_MANIFEST.json').decode('utf-8'))
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive entries')
        for name in names:
            safe_relative(name)
        expected_names = {r['path'] for r in manifest['payloads']} | {'AUTHORING_MANIFEST.json'}
        if set(names) != expected_names:
            raise ValueError('Unexpected archive entries')
        for r in manifest['payloads']:
            with archive.open(r['path']) as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != r['sha256'] or archive.getinfo(r['path']).file_size != r['bytes']:
                raise ValueError('Payload mismatch: ' + r['path'])
        sources = {'original_single_bin': args.source_bin, 'original_bios': args.source_bios}
        if args.restore_history:
            if not args.output or not args.xdelta:
                ap.error('--restore-history requires --output, --xdelta and both original sources')
            for key, profile in manifest['source_profiles'].items():
                source = sources[key]
                if source is None or source.stat().st_size != profile['bytes'] or sha(source) != profile['sha256']:
                    raise ValueError('Original source mismatch: ' + key)
        if args.output:
            output = args.output.resolve()
            output.mkdir(parents=True, exist_ok=False)
            for r in manifest['payloads']:
                if not r['path'].startswith('project/'):
                    continue
                relative = safe_relative(r['path'][len('project/'):])
                target = output / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(r['path']) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                if sha(target) != r['sha256']:
                    raise ValueError('Written file mismatch: ' + r['path'])
            if args.restore_history:
                with tempfile.TemporaryDirectory(prefix='tenshi2_restore_') as temp:
                    patch = Path(temp) / 'input.xdelta'
                    for r in manifest['historical_deltas']:
                        patch.write_bytes(archive.read(r['archive_path']))
                        target = output / safe_relative(r['original_path'])
                        target.parent.mkdir(parents=True, exist_ok=True)
                        subprocess.run([str(args.xdelta.resolve()), '-d', '-s', str(sources[r['source_kind']].resolve()), str(patch), str(target)], check=True)
                        if target.stat().st_size != r['target_bytes'] or sha(target) != r['target_sha256']:
                            raise ValueError('Historical output mismatch: ' + r['original_path'])
    print(json.dumps({'status': 'PASS', 'payloads_verified': len(manifest['payloads']),
                      'restored': args.output is not None, 'history_restored': args.restore_history}))


if __name__ == '__main__':
    main()
