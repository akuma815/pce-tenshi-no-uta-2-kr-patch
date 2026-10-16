"""Add historical captures and record-based diagrams to the v1 article."""
from pathlib import Path
import base64
import html
import json
import re
import shutil
import zipfile
import build_publication_worklog_20261010 as baseline

ROOT = baseline.ROOT
NAME = 'Tenshi2_KR_Worklog_20261010_v2'
PUB = ROOT / 'workspace/publication' / NAME
QA = ROOT / 'qa/publication' / NAME
sha = baseline.sha
CAPTURES = {
    6: ('translation/b4_debug_2026-08-23/v9_probe/run6_v17/mark1_f7294.png', 'V17'),
    7: ('translation/bios_retest_2026-08-22/R0_original_f800.png', 'R0 original'),
    8: ('translation/bios_retest_2026-08-22/R2_18glyph_f800.png', 'R2 18glyph'),
    9: ('translation/b9_runtime_v1_fail_2026-08-28/walk_f23998.png', 'b9 v1'),
    10: ('translation/b9_runtime_v3_pass_2026-08-28/pocserve_03_f03544.png', 'b9 v3'),
    12: baseline.FIGURES[0][:2], 13: baseline.FIGURES[1][:2],
    14: baseline.FIGURES[2][:2], 15: baseline.FIGURES[3][:2],
}
ADDITIONS = {
    1: [(1, '기록 기반 설명도입니다. 당시 단일 BIN의 데이터 섹터 형식을 잘못 처리한 과정과 수정 방향을 정리했으며, 실제 부팅 오류 화면이나 크기 비례 디스크 배치도는 아닙니다.')],
    2: [(2, '기록 기반 설명도입니다. 시스템 카드 한자 슬롯을 한글 그림으로 바꾸는 시험과 초기 기각 판정의 후속 정정을 정리했습니다. 당시 한 글자 출력 화면을 재현한 그림은 아닙니다.')],
    3: [(3, '기록 기반 설명도입니다. 한 글자 시험의 호출 위치 정정, 여덟 글자 표시 성공, 메모 진입 안정성 실패를 구분했습니다. 문자열은 당시 시험 표본이며 실제 게임 화면이 아닙니다.')],
    4: [(4, '기록 기반 설명도입니다. 첫 필드·전투·탑의 관측 경로에서 같은 RAM 영역을 교체하는 구조를 정리했습니다. 모든 장면의 읽기 크기나 전체 메모리 배치를 그대로 나타낸 도식은 아닙니다.')],
    5: [(5, '기록 기반 설명도입니다. 초기 상주 풀과 이후 모듈별 자산 소유 설계를 비교했습니다. 1,053자·99개는 당시 패키지 작업의 범위이며 현재 최종 방식이나 게임 전체 검수 완료를 뜻하지 않습니다.')],
    6: [(6, 'V17 내용 교체 실험의 실제 에뮬레이터 캡처입니다. 원본 게임 코드 상태에서 LBA 5480 부근의 14섹터만 바꿔도 전투 그래픽이 깨지는 진단 자료입니다. 현재 b26 화면이 아닙니다.')],
    7: [(7, '8월 22일 재검증에서 원본 시스템 카드로 부팅한 실제 에뮬레이터 캡처입니다. 아래 18글자 교체 카드와 같은 f800 조건의 비교 기준입니다.'),
        (8, '같은 재검증에서 18글자 교체 시스템 카드로 부팅한 실제 에뮬레이터 캡처입니다. 비교한 부팅 화면은 원본과 픽셀 단위로 같았으며, 초기 손상 판정을 철회한 근거 중 하나입니다. 부팅 비교만으로 모든 인게임 경로가 검증된 것은 아닙니다.')],
    8: [(9, 'b9 v1의 자동 실행 말미에 남은 실제 에뮬레이터 캡처입니다. 카드 확장 뱅크가 Arcade Card RAM 창에 가려 읽힌 코드가 0이 되면서 멈춘 빌드의 검은 화면입니다. 검은 화면 자체가 원인을 설명하는 자료는 아니며, 원인 판정은 당시 버스 실측 기록에 근거합니다.'),
        (10, '가려지는 뱅크를 피해 배치한 b9 v3의 실제 에뮬레이터 캡처입니다. 첫 대사의 한글 출력 경로를 확인한 자료입니다. 위 실패 화면과 같은 프레임 비교가 아니며, 전체 54씬 검수나 b26 완성 상태를 뜻하지 않습니다.')],
    9: [(11, '기록 기반 설명도입니다. 폐기한 에뮬레이터 자막 방식의 수집·매칭·위치 추적과 난관을 정리했습니다. 소실된 오버레이 캡처를 복원하거나 당시 자막 화면을 재현한 자료는 아닙니다.')],
}

def main():
    QA.mkdir(parents=True, exist_ok=True)
    # v1 is immutable input; regenerated v2 retains all original paragraphs.
    md = (baseline.PUB / '작업기.md').read_text(encoding='utf-8')
    md = re.sub(r'images/(0[1-4])\.png', lambda m:f'images/{int(m[1])+11:02}.png', md)
    for sec, figures in ADDITIONS.items():
        marker = f'\n## {sec+1}. '
        assert marker in md
        extra = '\n\n'.join(f'![{caption}](images/{num:02}.png)' for num, caption in figures)
        md = md.replace(marker, '\n'+extra+'\n'+marker, 1)
    md = md.replace('이번 글의 화면은 작업 과정에서 남긴 서로 다른 빌드의 캡처입니다.',
        '이번 글에는 작업 과정에서 남긴 서로 다른 빌드의 실제 캡처와, 기록을 읽어 만든 설명도가 함께 들어 있습니다. 각각의 종류와 확인 범위는 그림 안의 표시 및 캡션에 적었습니다.')
    (PUB / '작업기.md').write_text(md, encoding='utf-8')
    diagrams = {d['image']:d for d in json.loads((QA/'diagram_sources.json').read_text(encoding='utf-8'))}
    provenance = []
    for num in range(1, 16):
        rel = f'images/{num:02}.png'
        target = PUB / rel
        if num in CAPTURES:
            source, build = CAPTURES[num]
            shutil.copyfile(ROOT/source, target)
            entry = dict(image=rel, source=source, build=build, kind='actual_emulator_capture',
                source_bytes_preserved=True, newly_captured=False)
        else:
            assert target.is_file(), rel
            entry = dict(diagrams[rel], generator='tools/draw_publication_explainers_20261010.py',
                         generated_in_this_session=True)
        entry.update(sha256=sha(target), b26_full_qa_evidence=False)
        provenance.append(entry)
    captions = re.findall(r'!\[(.*?)\]\((images/\d{2}\.png)\)', md)
    assert [rel for _,rel in captions] == [f'images/{num:02}.png' for num in range(1,16)]
    for entry, (caption, _) in zip(provenance, captions):
        entry['caption'] = caption
    (PUB/'이미지_출처_구분.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    parts = re.split(r'\n\s*\n', md.strip())
    rendered, plain = [], []
    for part in parts:
        if part.startswith('# '):
            title = part[2:]; plain.append(title)
        elif part.startswith('## '):
            heading = part[3:]; num = int(heading.split('.')[0])
            rendered.append(f'<h2 id="s{num}">{html.escape(heading)}</h2>'); plain.append(heading)
        elif part.startswith('!['):
            caption, rel = re.fullmatch(r'!\[(.*?)\]\((images/\d{2}\.png)\)',part).groups()
            kind = provenance[int(Path(rel).stem)-1]['kind']
            data = base64.b64encode((PUB/rel).read_bytes()).decode('ascii')
            rendered.append(f'<figure data-kind="{kind}"><button class="zoom" aria-label="이미지 확대"><img src="data:image/png;base64,{data}" alt="{html.escape(caption)}"></button><figcaption>{html.escape(caption)}</figcaption></figure>')
            plain.append(f'[이미지 삽입: {rel}]\n{caption}')
        else:
            rendered.append(f'<p>{html.escape(part)}</p>'); plain.append(part)
    (PUB/'카페_복사용_본문.txt').write_text('\n\n'.join(plain)+'\n',encoding='utf-8-sig')
    oldhtml = (baseline.PUB/'작업기.html').read_text(encoding='utf-8')
    css = re.search(r'<style>(.*?)</style>',oldhtml,re.S)[1]
    css = css.replace('max-width:682px','max-width:800px').replace('height:auto;margin:auto;image-rendering:pixelated','height:auto;margin:auto')
    css = css.replace('height:auto;image-rendering:pixelated','height:auto')
    css += 'figure[data-kind="actual_emulator_capture"] img,dialog[data-kind="actual_emulator_capture"] img{image-rendering:pixelated}'
    script = re.search(r'<script>(.*?)</script>',oldhtml,re.S)[1]
    script = script.replace("d.querySelector('img').src=b.querySelector('img').src;", "d.dataset.kind=b.closest('figure').dataset.kind;d.querySelector('img').src=b.querySelector('img').src;")
    page = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{css}</style></head><body><header><div><h1>{html.escape(title)}</h1><p>2026.10.10 · 초기 조사부터 b26 테스트판까지의 중간 작업기<br>실제 에뮬레이터 캡처 9장과 기록 기반 설명도 6장 · 각 캡션에 종류와 확인 범위를 표시했습니다.<br>이미지를 클릭하면 확대됩니다.</p></div></header><main>{"".join(rendered)}</main><dialog><button autofocus>닫기</button><img alt="확대 자료"></dialog><script>{script}</script></body></html>'
    page = page.replace('ㅎㅎ','<span class="emotion">ㅎㅎ</span>').replace('ㅠㅠ','<span class="emotion">ㅠㅠ</span>')
    (PUB/'작업기.html').write_text(page,encoding='utf-8')
    guide = (baseline.PUB/'업로드_안내.txt').read_text(encoding='utf-8-sig')
    guide = guide.replace('01~04 순서입니다.','01~15 순서입니다.').replace('메모 본문 이미지(04)','메모 본문 이미지(15)')
    guide = guide.replace('이미지는 원본 캡처 바이트를 그대로 복사했습니다. 01=b13, 02=b17, 03=b22, 04=b25입니다.\n모두 작업 당시의 에뮬레이터 화면이며, b26 전체 검수 또는 실제 기기 확인을 뜻하지 않습니다.',
        '01~05와 11은 기록 기반 설명도입니다. 당시 게임 화면을 재현한 그림이 아닙니다.\n06=V17 전투 손상, 07=원본 카드 부팅, 08=18글자 카드 재검증, 09=b9 v1 검은 화면, 10=b9 v3 대사입니다.\n12=b13 초상화, 13=b17 타이틀, 14=b22 조사, 15=b25 메모 본문입니다.\n실제 캡처 9장은 원본 바이트를 복사했습니다. b26 전체 검수 또는 실제 기기 확인을 뜻하지 않습니다.')
    (PUB/'업로드_안내.txt').write_text(guide,encoding='utf-8-sig')
    sources = baseline.SOURCES + ['docs/retired/Z11_에뮬레이터_오버레이_설계.md',
        'docs/active/Z9_b9_카드_확장_설계.md', 'translation/task4_field_hook_poc_v2_runtime.json',
        'translation/task5_field_multiglyph_poc_runtime.json']
    (QA/'sources.json').write_text(json.dumps({'project_sources':[dict(path=p,sha256=sha(ROOT/p)) for p in sources],
        'previous_package':dict(path=str(baseline.PUB.with_suffix('.zip')),sha256=sha(baseline.PUB.with_suffix('.zip')))},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copyfile(baseline.QA/'작성_근거.md',QA/'작성_근거.md')
    with (QA/'작성_근거.md').open('a',encoding='utf-8') as f:
        f.write('\n## v2 보완\n\n사용자 요청으로 1~5와 9절에 기록 기반 설명도 6장, 6~8절에 기존 캡처 5장을 추가했다. 실제 캡처 총 9장·설명도 6장이다. 당시 없는 화면을 재현하지 않았다. 이전 공개물과 QA는 보존했다. 게임은 실행하지 않았다. 출처는 diagram_sources.json 및 공개 이미지 출처표에 기록했다.\n')
    payload = sorted(p for p in PUB.rglob('*') if p.is_file() and p.name!='SHA256.txt')
    assert len(payload)==20
    (PUB/'SHA256.txt').write_text(''.join(f'{sha(p)}  {p.relative_to(PUB).as_posix()}\n' for p in payload),encoding='utf-8')
    archive = PUB.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PUB.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(PUB).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==21
        for name in z.namelist():
            assert z.read(name)==(PUB/name).read_bytes()
            assert Path(name).suffix in {'.md','.txt','.html','.json','.png'}
    assert len(parts)==len(plain) and page.count('<h2 ')==15
    embedded = re.findall(r'data:image/png;base64,([A-Za-z0-9+/=]+)',page)
    assert len(embedded)==15
    for data, (_,rel) in zip(embedded,captions): assert base64.b64decode(data)==(PUB/rel).read_bytes()
    for entry in provenance:
        if entry['kind']=='actual_emulator_capture':
            assert (ROOT/entry['source']).read_bytes()==(PUB/entry['image']).read_bytes()
        else:
            assert '기록 기반 설명도' in entry['caption']
    for p in PUB.rglob('*'):
        if p.is_file() and p.suffix!='.png': assert '\ufffd' not in p.read_text(encoding='utf-8-sig')
    report = dict(status='PASS',date='2026-10-10',sections=15,figures=15,captures=9,diagrams=6,
        package_files=21,archive=str(archive),sha256=sha(archive),
        checks=['utf8','section_plaintext_parity','sequential_markers','original_capture_byte_equality',
                'embedded_png_equality','diagram_labels','zip_crc_payload','publication_only_extensions'],
        new_game_validation=False,board_posted=False)
    (QA/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__ == '__main__':
    main()
