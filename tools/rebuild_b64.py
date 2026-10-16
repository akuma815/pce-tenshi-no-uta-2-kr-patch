"""Rebuild the frozen PCE-CD v1.0 core in an isolated private staging tree."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STEM = 'Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args, cwd, log):
    with log.open('wb') as stream:
        result = subprocess.run([str(x) for x in args], cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Build step failed ({result.returncode}); see {log}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source-bin', type=Path, required=True)
    ap.add_argument('--source-cue', type=Path, required=True)
    ap.add_argument('--source-bios', type=Path, required=True)
    ap.add_argument('--xdelta', type=Path, required=True)
    ap.add_argument('--dotnet', default='dotnet')
    ap.add_argument('--redump-track02', type=Path)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    profile = json.loads((ROOT / 'config/rebuild_b64.json').read_text(encoding='utf-8'))
    if args.source_bin.stat().st_size != profile['source_bin']['bytes'] or sha(args.source_bin) != profile['source_bin']['sha256']:
        raise ValueError('Unsupported single-BIN source')
    if sha(args.source_cue) != profile['source_cue_sha256']:
        raise ValueError('Unsupported single-BIN CUE layout')
    bios = args.source_bios.read_bytes()
    if len(bios) == 262656:
        bios = bios[512:]
    if len(bios) != profile['source_bios']['bytes'] or hashlib.sha256(bios).hexdigest() != profile['source_bios']['sha256']:
        raise ValueError('Unsupported Japanese System Card 3.0 BIOS')
    if sha(ROOT / profile['font']['path']) != profile['font']['sha256']:
        raise ValueError('Galmuri14 source font mismatch')
    if args.redump_track02 and (args.redump_track02.stat().st_size != profile['redump_track02']['bytes'] or sha(args.redump_track02) != profile['redump_track02']['sha256']):
        raise ValueError('Unsupported Redump Track 02 source')
    stage = (args.output or ROOT / 'build' / ('b64_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
    stage.mkdir(parents=True, exist_ok=False)

    def ignored(folder, names):
        return [n for n in names if n in {'bin', 'obj', '__pycache__', '.git'} or Path(n).suffix.lower() in {'.exe', '.dll', '.pdb', '.pyc', '.bin', '.pce', '.mp4'}]

    for name in ['tools', 'translation', 'assets', 'config', 'licenses']:
        shutil.copytree(ROOT / name, stage / name, ignore=ignored)
    shutil.copytree(ROOT / 'release/app', stage / 'release/app', ignore=ignored)
    shutil.copyfile(args.source_bin, stage / (STEM + '.bin'))
    shutil.copyfile(args.source_cue, stage / (STEM + '.cue'))
    probes = stage / 'probes'
    probes.mkdir()
    original_bios = probes / 'SystemCard3_original_noheader.pce'
    original_bios.write_bytes(bios)
    patch = ROOT / profile['bootstrap']['patch']
    if sha(patch) != profile['bootstrap']['patch_sha256']:
        raise ValueError('Intermediate-card delta mismatch')
    intermediate = probes / 'SystemCard3_btrack_full_v6.pce'
    run([args.xdelta.resolve(), '-d', '-s', original_bios, patch, intermediate], stage, stage / 'bootstrap.log')
    if sha(intermediate) != profile['bootstrap']['target_sha256']:
        raise ValueError('Restored intermediate card mismatch')
    run([args.dotnet, 'build', 'tools/huc6280_disasm_verifier/huc6280_disasm_verifier.csproj', '-c', 'Debug', '--nologo', '--verbosity', 'quiet'], stage, stage / 'disassembler_build.log')
    run([sys.executable, '-X', 'utf8', 'tools/build_btrack_b64_hook_build.py'], stage, stage / 'b64_build.log')
    disc = stage / (STEM + '_btrack_b64.bin')
    cue = disc.with_suffix('.cue')
    card = probes / 'SystemCard3_btrack_b64.pce'
    if sha(disc) != profile['expected_b64']['disc_sha256'] or sha(card) != profile['expected_b64']['card_sha256']:
        raise ValueError('Rebuilt disc/card differ from the published v1.0')
    if sha(cue) != profile['expected_b64']['cue_sha256']:
        raise ValueError('Rebuilt CUE differs from the known b64 layout')
    report = {'status': 'PASS', 'evidence_class': 'Source rebuild with byte-identical disc/CUE/system-card outputs; no new runtime test', 'disc_bytes': disc.stat().st_size, 'disc_sha256': sha(disc), 'cue_sha256': sha(cue), 'card_bytes': card.stat().st_size, 'card_sha256': sha(card), 'bootstrap_restored_from_original_bios': True, 'redump_track02_verified': False}
    if args.redump_track02:
        sys.path.insert(0, str(stage / 'release/app'))
        from cdrom_mode1 import mode1_sector
        source = args.redump_track02.read_bytes()
        data = disc.read_bytes()
        output = bytearray(source[:224 * 2352])
        for index in range(len(source) // 2352 - 224):
            start = 7914480 + index * 2048
            output += mode1_sector(data[start:start + 2048], 3590 + index)
        target = stage / 'Track02_KR.bin'
        target.write_bytes(output)
        if sha(target) != profile['redump_track02']['expected_output_sha256']:
            raise ValueError('Reconstructed Redump Track 02 differs from public patch output')
        report.update({'redump_track02_verified': True, 'redump_track02_sha256': sha(target), 'redump_track02_bytes': target.stat().st_size})
    (stage / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output_directory': str(stage), **report}, indent=2))


if __name__ == '__main__':
    main()
