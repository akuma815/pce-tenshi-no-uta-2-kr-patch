"""Rebuild the v1.0 (b64) core from a Redump track set instead of the single-BIN dump.

The build chain reads the single-BIN layout (Track 01 raw audio, data track as 2048-byte
sectors from byte 7,914,480, remaining audio raw). This script synthesizes that container
from the 34 Redump track files (Track 01 = 3365 sectors, Track 02 user data from sector 224,
Track 03 without its 150-sector pregap, Tracks 04-34 verbatim). The audio bytes of the
original single-BIN dump differ (dump offset), so the rebuilt disc SHA-256 is NOT comparable
with config/rebuild_b64.json. What IS verified byte-for-byte: the system card, the Redump
Track 02 output (data track), and that audio regions pass through untouched.
"""
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
TRACK = 'Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track %02d).bin'
S = 2352
T2 = 7_914_480          # data track start in the single-BIN layout (= 3365 * 2352)
DATA_SECTORS = 9328     # 9552 Redump Track 02 sectors - 224 pregap sectors
DATA_LBA = 3590


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def run(args, cwd, log):
    with log.open('wb') as stream:
        result = subprocess.run([str(x) for x in args], cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Build step failed ({result.returncode}); see {log}')


def synthesize(redump_dir, out_bin):
    def t(k):
        return (redump_dir / (TRACK % k)).read_bytes()
    t1 = t(1)
    if len(t1) != 3366 * S:
        raise ValueError('Unexpected Redump Track 01 size')
    t2 = t(2)
    if len(t2) != (DATA_SECTORS + 224) * S:
        raise ValueError('Unexpected Redump Track 02 size')
    data = bytearray()
    for i in range(224, len(t2) // S):
        sec = t2[i * S:(i + 1) * S]
        if sec[15] != 1:
            raise ValueError(f'Track 02 sector {i} is not Mode 1')
        data += sec[16:16 + 2048]
    t3 = t(3)
    with out_bin.open('wb') as f:
        f.write(t1[:3365 * S])
        f.write(data)
        f.write(t3[150 * S:])
        for k in range(4, 35):
            f.write(t(k))
    return bytes(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--redump-dir', type=Path, required=True, help='folder with the 34 Redump track .bin files')
    ap.add_argument('--source-bios', type=Path, required=True)
    ap.add_argument('--xdelta', type=Path, required=True)
    ap.add_argument('--dotnet', default='dotnet')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--build', default='b64', help='빌드 태그: tools/build_btrack_<태그>_hook_build.py 실행 (기본 b64)')
    ap.add_argument('--no-expect', action='store_true', help='b64 고정 출력 해시 검사 생략(새 빌드 태그용). 카드·Track02 해시는 보고만 한다')
    args = ap.parse_args()
    tag = args.build
    profile = json.loads((ROOT / 'config/rebuild_b64.json').read_text(encoding='utf-8'))
    track02 = args.redump_dir / (TRACK % 2)
    if track02.stat().st_size != profile['redump_track02']['bytes'] or sha(track02) != profile['redump_track02']['sha256']:
        raise ValueError('Unsupported Redump Track 02 source')
    bios = args.source_bios.read_bytes()
    if len(bios) == 262656:
        bios = bios[512:]
    if len(bios) != profile['source_bios']['bytes'] or sha_bytes(bios) != profile['source_bios']['sha256']:
        raise ValueError('Unsupported Japanese System Card 3.0 BIOS')
    if sha(ROOT / profile['font']['path']) != profile['font']['sha256']:
        raise ValueError('Galmuri14 source font mismatch')
    stage = (args.output or ROOT / 'build' / (f'{args.build}r_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
    stage.mkdir(parents=True, exist_ok=False)

    def ignored(folder, names):
        return [n for n in names if n in {'bin', 'obj', '__pycache__', '.git'} or Path(n).suffix.lower() in {'.exe', '.dll', '.pdb', '.pyc', '.bin', '.pce', '.mp4'}]

    for name in ['tools', 'translation', 'assets', 'config', 'licenses']:
        shutil.copytree(ROOT / name, stage / name, ignore=ignored)
    shutil.copytree(ROOT / 'release/app', stage / 'release/app', ignore=ignored)
    src_bin = stage / (STEM + '.bin')
    orig_data = synthesize(args.redump_dir, src_bin)
    if src_bin.stat().st_size != profile['source_bin']['bytes']:
        raise ValueError('Synthesized container size differs from the single-BIN layout')
    # The chain gates on the single-BIN dump's SHA-256 (build_btrack_b7_hook_build.SRC_SHA256).
    # Only audio bytes differ in the synthesized container, so point the staged copy at its hash;
    # the data-track equivalence is proven below by the Redump Track 02 output hash.
    container_sha = sha(src_bin).upper()
    b7 = stage / 'tools/build_btrack_b7_hook_build.py'
    text = b7.read_text(encoding='utf-8')
    needle = 'SRC_SHA256 = "' + profile['source_bin']['sha256'].upper() + '"'
    if text.count(needle) != 1:
        raise ValueError('Could not locate SRC_SHA256 in the staged b7 build script')
    b7.write_text(text.replace(needle, 'SRC_SHA256 = "' + container_sha + '"  # redump-synthesized container'), encoding='utf-8')
    cue_text = (ROOT / 'release/app/cue_template.cue').read_text(encoding='ascii').replace('{BIN}', STEM + '.bin')
    (stage / (STEM + '.cue')).write_text(cue_text, encoding='ascii')
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
    run([sys.executable, '-X', 'utf8', f'tools/build_btrack_{tag}_hook_build.py'], stage, stage / f'{tag}_build.log')
    disc = stage / (STEM + f'_btrack_{tag}.bin')
    cue = disc.with_suffix('.cue')
    card = probes / f'SystemCard3_btrack_{tag}.pce'
    report = {'status': 'PASS', 'build': tag, 'source': 'redump-track-set', 'disc_bytes': disc.stat().st_size, 'disc_sha256': sha(disc),
              'disc_sha256_comparable_to_single_bin_profile': False, 'synthesized_container_sha256': container_sha.lower(),
              'cue_sha256': sha(cue),
              'card_bytes': card.stat().st_size, 'card_sha256': sha(card)}
    if not args.no_expect and sha(card) != profile['expected_b64']['card_sha256']:
        raise ValueError('Rebuilt system card differs from the published v1.0')
    if not args.no_expect and sha(cue) != profile['expected_b64']['cue_sha256']:
        raise ValueError('Rebuilt CUE differs from the known b64 layout')
    report['card_matches_v1_0'] = sha(card) == profile['expected_b64']['card_sha256']
    src = src_bin.read_bytes()
    out = disc.read_bytes()
    if len(src) != len(out):
        raise ValueError('Rebuilt disc size differs from the source container')
    if src[:T2] != out[:T2] or src[T2 + DATA_SECTORS * 2048:] != out[T2 + DATA_SECTORS * 2048:]:
        raise ValueError('Audio regions were modified by the build')
    report['audio_regions_passthrough'] = True
    sys.path.insert(0, str(stage / 'release/app'))
    from cdrom_mode1 import mode1_sector
    t2 = track02.read_bytes()
    output = bytearray(t2[:224 * S])
    for index in range(DATA_SECTORS):
        start = T2 + index * 2048
        output += mode1_sector(out[start:start + 2048], DATA_LBA + index)
    target = stage / 'Track02_KR.bin'
    target.write_bytes(output)
    if not args.no_expect and sha(target) != profile['redump_track02']['expected_output_sha256']:
        raise ValueError('Reconstructed Redump Track 02 differs from public patch output')
    report.update({'redump_track02_verified': sha(target) == profile['redump_track02']['expected_output_sha256'], 'redump_track02_sha256': sha(target),
                   'redump_track02_bytes': target.stat().st_size, 'data_region_source_sha256': sha_bytes(orig_data)})
    (stage / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output_directory': str(stage), **report}, indent=2))


if __name__ == '__main__':
    main()
