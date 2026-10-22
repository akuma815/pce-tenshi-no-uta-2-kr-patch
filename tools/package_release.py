#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.0.1 배포 ZIP 조립 (2026-10-22).

입력: 공식 단일 BIN 재빌드 스테이지 두 개(이전 판 = b64 = v1.0, 이번 판 = b65), 원본 단일 BIN·원본 BIOS·Redump Track 02, xdelta3.exe.
출력: release/dist/<이름>/ 에 패치 6종 + 패처 exe(PyInstaller) + cue_template + README, 그리고 ZIP 과 SHA-256 목록(JSON).
패처 소스(release/app/tenshi2kr_patcher.py)의 OUT_*/PREV_* 해시 상수는 여기서 계산한 값으로 치환해 둔다(소스에 반영됨).

사용:
  python -X utf8 tools/package_release.py --prev-stage build/b64_official --stage build/b65_official --prev-tag b64 --tag b65 \
      --source-bin Original/Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin --source-bios bios/SystemCard3_original.pce \
      --redump-track02 "Original/Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02).bin" \
      --xdelta <xdelta3.exe> --name Tenshi2_KR_v1.0.1_20261022 --prev-zip build/v1.0_release/Tenshi2_KR_v1.0_20261014.zip
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = 'Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP'


def sha(path, algo='sha256'):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, algo).hexdigest()


def run(args, cwd=None):
    r = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'{args[0]} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}')
    return r


def xdelta(x, src, dst, out):
    run([x, '-e', '-9', '-f', '-s', src, dst, out])
    chk = Path(str(out) + '.chk')
    run([x, '-d', '-f', '-s', src, out, chk])
    assert sha(chk) == sha(dst), f'xdelta round-trip mismatch for {out}'
    chk.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prev-stage', type=Path, required=True)
    ap.add_argument('--stage', type=Path, required=True)
    ap.add_argument('--prev-tag', default='b64')
    ap.add_argument('--tag', default='b65')
    ap.add_argument('--source-bin', type=Path, required=True)
    ap.add_argument('--source-bios', type=Path, required=True)
    ap.add_argument('--redump-track02', type=Path, required=True)
    ap.add_argument('--xdelta', type=Path, required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--prev-zip', type=Path, help='이전 판 ZIP (v0.3→ 카드 패치 재사용)')
    ap.add_argument('--skip-exe', action='store_true')
    a = ap.parse_args()

    bios = a.source_bios.read_bytes()
    if len(bios) == 262656:
        bios = bios[512:]
    disc = a.stage / f'{STEM}_btrack_{a.tag}.bin'
    card = a.stage / 'probes' / f'SystemCard3_btrack_{a.tag}.pce'
    t2 = a.stage / 'Track02_KR.bin'
    pdisc = a.prev_stage / f'{STEM}_btrack_{a.prev_tag}.bin'
    pcard = a.prev_stage / 'probes' / f'SystemCard3_btrack_{a.prev_tag}.pce'
    pt2 = a.prev_stage / 'Track02_KR.bin'
    for p in (disc, card, t2, pdisc, pcard, pt2):
        assert p.exists(), p

    out = ROOT / 'release' / 'dist' / a.name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    tmp = ROOT / 'release' / 'dist' / '_tmp'
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    bios_file = tmp / 'SystemCard3_original_noheader.pce'
    bios_file.write_bytes(bios)

    x = a.xdelta.resolve()
    xdelta(x, a.source_bin, disc, out / 'Tenshi_no_Uta_II_KR_disc.xdelta')
    xdelta(x, pdisc, disc, out / 'Tenshi_no_Uta_II_KR_disc_from_v1.0.xdelta')
    xdelta(x, a.redump_track02, t2, out / 'Tenshi_no_Uta_II_KR_track02_redump.xdelta')
    xdelta(x, pt2, t2, out / 'Tenshi_no_Uta_II_KR_track02_redump_from_v1.0.xdelta')
    xdelta(x, bios_file, card, out / 'SystemCard3_KR.xdelta')
    if a.prev_zip:
        with zipfile.ZipFile(a.prev_zip) as z:
            for info in z.infolist():
                if info.filename.endswith('SystemCard3_KR_from_v0.3.xdelta'):
                    (out / 'SystemCard3_KR_from_v0.3.xdelta').write_bytes(z.read(info))
    shutil.copyfile(ROOT / 'release/app/cue_template.cue', out / 'cue_template.cue')
    shutil.copyfile(ROOT / 'release/app/README.txt', out / 'README.txt')

    # 패처 소스 해시 상수 갱신
    src = ROOT / 'release/app/tenshi2kr_patcher.py'
    text = src.read_text(encoding='utf-8')
    consts = {
        'ORIG_BIN_SHA1': sha(a.source_bin, 'sha1'), 'ORIG_CARD_SHA1': hashlib.sha1(bios).hexdigest(),
        'OUT_BIN_SHA1': sha(disc, 'sha1'), 'OUT_CARD_SHA1': sha(card, 'sha1'),
        'REDUMP_T2_SHA1': sha(a.redump_track02, 'sha1'), 'OUT_T2_SHA1': sha(t2, 'sha1'),
        'PREV_BIN_SHA1': sha(pdisc, 'sha1'), 'PREV_T2_SHA1': sha(pt2, 'sha1'),
    }
    for k, v in consts.items():
        text, n = re.subn(rf'^{k} = "[0-9a-f]{{40}}"$', f'{k} = "{v}"', text, flags=re.M)
        assert n == 1, k
    src.write_text(text, encoding='utf-8')

    if not a.skip_exe:
        app = tmp / 'app'
        shutil.copytree(ROOT / 'release/app', app, ignore=shutil.ignore_patterns('build', 'dist', '__pycache__'))
        shutil.copyfile(x, app / 'xdelta3.exe')
        run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', 'Tenshi2KR_Patcher.spec'], cwd=app)
        shutil.copyfile(app / 'dist' / 'Tenshi2KR_Patcher.exe', out / 'Tenshi2KR_Patcher.exe')

    zpath = out.parent / f'{a.name}.zip'
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.iterdir()):
            z.write(p, f'{a.name}/{p.name}')
    report = {'name': a.name, 'zip_sha256': sha(zpath), 'files': {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(out.iterdir())},
              'outputs': {'disc_sha256': sha(disc), 'disc_sha1': consts['OUT_BIN_SHA1'], 'card_sha256': sha(card), 'card_sha1': consts['OUT_CARD_SHA1'],
                          'track02_sha256': sha(t2), 'track02_sha1': consts['OUT_T2_SHA1']},
              'inputs': {'source_bin_sha256': sha(a.source_bin), 'source_bios_sha256': hashlib.sha256(bios).hexdigest(), 'redump_track02_sha256': sha(a.redump_track02)},
              'prev': {'disc_sha1': consts['PREV_BIN_SHA1'], 'track02_sha1': consts['PREV_T2_SHA1'], 'card_sha1': sha(pcard, 'sha1')}}
    (out.parent / f'{a.name}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    shutil.rmtree(tmp)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
