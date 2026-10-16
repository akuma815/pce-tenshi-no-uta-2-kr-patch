"""Package the authored worklog and existing evidence; never run game builds."""
from pathlib import Path
import base64
import hashlib
import html
import json
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'Tenshi2_KR_Worklog_20261010'
PUB = ROOT / 'workspace' / 'publication' / NAME
QA = ROOT / 'qa' / 'publication' / NAME

FIGURES = [
    ('translation/b13_fetch_trace/portrait_b13_300.png', 'b13', '초상화 스트림 처리 후 표시 확인'),
    ('translation/b17_runtime/title_b17_b.png', 'b17', '크기와 배치 조정 후 타이틀'),
    ('translation/b22_runtime/bprobe_01_f02693.png', 'b22', '슈리커가 출력; 이후 메모 결함으로 추가 수정'),
    ('translation/b25_runtime/userstate/u_f090.png', 'b25', '사용자 스테이트에서 메모 본문 표시 확인'),
]
SOURCES = [
    'docs/HANDOFF.md',
    'docs/retired/진행 내용.txt',
    'docs/retired/Task0_기준선.md',
    'docs/retired/Task1_GETFNT_카탈로그.md',
    'docs/retired/Task2_커스텀코드공간.md',
    'docs/retired/Task4_1글자_훅_PoC.md',
    'docs/retired/Task5_필드_다글자_PoC.md',
    'docs/retired/Task.md',
    'docs/active/Z1_모듈_로더_카탈로그.md',
    'docs/active/Z2_무수정_모듈_재조립.md',
    'docs/active/전략_재검토_BIOS폰트_2026-08-22.md',
    'docs/active/Z10_b10_메뉴_UI_인플레이스.md',
    'release/Tenshi2_KR_test_20261010/README.txt',
]
TONE = ROOT.parent / 'Tiny Toon Adventures 2/workspace/publication/TinyToon2_KR_Worklog_AuthorVoice_20261009/작업기.md'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    QA.mkdir(parents=True, exist_ok=True)
    (PUB / 'images').mkdir(exist_ok=True)
    provenance = []
    for i, (source, build, scope) in enumerate(FIGURES, 1):
        target = PUB / 'images' / f'{i:02}.png'
        shutil.copyfile(ROOT / source, target)
        provenance.append(dict(image=f'images/{i:02}.png', source=source, build=build,
                               kind='actual_emulator_capture', scope=scope,
                               sha256=sha(target), source_bytes_preserved=True,
                               newly_captured=False, b26_full_qa_evidence=False))
    (PUB / '이미지_출처_구분.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    md = (PUB / '작업기.md').read_text(encoding='utf-8')
    parts = re.split(r'\n\s*\n', md.strip())
    rendered = []
    plain = []
    captions = []
    for part in parts:
        if part.startswith('# '):
            title = part[2:]
            plain.append(title)
            continue
        if part.startswith('## '):
            heading = part[3:]
            n = int(heading.split('.')[0])
            rendered.append(f'<h2 id="s{n}">{html.escape(heading)}</h2>')
            plain.append(heading)
        elif part.startswith('!['):
            match = re.fullmatch(r'!\[(.*?)\]\((images/\d{2}\.png)\)', part)
            assert match, part
            caption, rel = match.groups()
            b64 = base64.b64encode((PUB / rel).read_bytes()).decode('ascii')
            rendered.append(f'<figure><button class="zoom" aria-label="이미지 확대"><img src="data:image/png;base64,{b64}" alt="{html.escape(caption)}"></button><figcaption>{html.escape(caption)}</figcaption></figure>')
            plain.append(f'[이미지 삽입: {rel}]\n{caption}')
            captions.append((rel, caption))
        else:
            rendered.append(f'<p>{html.escape(part)}</p>')
            plain.append(part)
    (PUB / '카페_복사용_본문.txt').write_text('\n\n'.join(plain)+'\n', encoding='utf-8-sig')
    css = '''*{box-sizing:border-box}body{margin:0;background:#eef1f4;color:#203448;font-family:"Malgun Gothic",sans-serif}header{background:#162f48;color:white;padding:42px 24px}header div,main{max-width:900px;margin:auto}h1{font-size:30px;line-height:1.5;margin:10px 0;word-break:keep-all}header p{font-size:14px;line-height:1.8;color:#dce5ed}main{padding:28px 28px 60px;background:white}h2{font-size:24px;margin-top:44px;border-left:5px solid #316da6;padding-left:14px;line-height:1.5;word-break:keep-all}p{font-size:17px;line-height:1.95;overflow-wrap:anywhere}figure{margin:28px 0 36px}.zoom{display:block;border:0;background:#eff3f6;padding:20px;width:100%;cursor:zoom-in}figure img{display:block;width:100%;max-width:682px;height:auto;margin:auto;image-rendering:pixelated}figcaption{font-size:14px;color:#536478;line-height:1.8;margin-top:10px}dialog{width:min(96vw,1100px);border:0;border-radius:8px;padding:12px}dialog::backdrop{background:#000c}dialog img{width:100%;height:auto;image-rendering:pixelated}dialog button{font:inherit;padding:8px 16px;margin-bottom:12px}.emotion{white-space:nowrap}@media(max-width:600px){header{padding:26px 18px}h1{font-size:25px}main{padding:16px 18px 40px}h2{font-size:21px}.zoom{padding:8px}}'''
    page = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{css}</style></head><body><header><div><h1>{html.escape(title)}</h1><p>2026.10.10 · 초기 조사부터 b26 테스트판까지의 중간 작업기<br>이미지는 당시 빌드의 실제 에뮬레이터 캡처이며, 클릭하면 확대됩니다.</p></div></header><main>{''.join(rendered)}</main><dialog><button autofocus>닫기</button><img alt="확대 자료"></dialog><script>const d=document.querySelector('dialog');document.querySelectorAll('.zoom').forEach(b=>b.onclick=()=>{{d.querySelector('img').src=b.querySelector('img').src;d.showModal()}});d.querySelector('button').onclick=()=>d.close();d.onclick=e=>{{if(e.target===d)d.close()}};</script></body></html>'''
    page = page.replace('ㅎㅎ', '<span class="emotion">ㅎㅎ</span>').replace('ㅠㅠ', '<span class="emotion">ㅠㅠ</span>')
    (PUB / '작업기.html').write_text(page, encoding='utf-8')
    guide = '''네이버 게시판 업로드 안내

제목: 천사의 시 II ~타천사의 선택~ 한국어화 작업기

1. 카페_복사용_본문.txt를 게시글 편집기에 붙여 넣습니다.
2. [이미지 삽입: images/01.png] 표시 위치에 해당 PNG를 올립니다. 01~04 순서입니다.
3. 삽입 표시를 지우고, 바로 뒤의 설명을 이미지 캡션으로 남깁니다.
4. 메모 본문 이미지(04)는 초반 대사 일부를 포함합니다. 게시판 관례에 맞춰 표시해 주세요.

작업기.html은 이미지를 내장한 오프라인 검토용입니다. 이미지 클릭으로 확대하고 Esc 또는 닫기로 돌아옵니다.
이미지는 원본 캡처 바이트를 그대로 복사했습니다. 01=b13, 02=b17, 03=b22, 04=b25입니다.
모두 작업 당시의 에뮬레이터 화면이며, b26 전체 검수 또는 실제 기기 확인을 뜻하지 않습니다.

현재 상태는 2026-10-10 b26 테스트판 준비 및 사용자 플레이 게이트 대기입니다.
완성판 공개·전 범위 번역 완료·완주 검수 완료로 소개하지 않도록 본문의 현재 상태를 유지해 주세요.
이 작업기 ZIP에는 게임 이미지, 시스템 카드 이미지, 패치, 패처, 세이브를 넣지 않았습니다.
게임 테스트판 첨부가 필요하면 release/Tenshi2_KR_test_20261010의 별도 안내와 확인 상태를 검토해 주세요.
작업기 작성 중 실제 게시판 게시는 수행하지 않았습니다.
'''
    (PUB / '업로드_안내.txt').write_text(guide, encoding='utf-8-sig')
    sections = {
        '1': 'retired/진행 내용.txt 진행 내용 1 + active/Z2 혼합 모드 경계·identity 결과. 이후 pregap 설명은 최신 HANDOFF 정정을 우선함.',
        '2-3': 'retired/Task0 제한 성공·과거 실패, Task2 코드 공간, Task4 v1/v2 정정, Task5 표시 성공·메모 안정성 실패.',
        '4-5': 'retired/Task.md 폐기 고지 + active/Z1 로더 그래프 + HANDOFF 단계표 Z1~Z7.',
        '6': 'HANDOFF §9 공유 extent, 5480 전투 자산, 9178 오판 정정, init coverage와 상태 의존 read.',
        '7': 'active/전략_재검토_BIOS폰트_2026-08-22 §1~3 + HANDOFF 시스템카드 실측.',
        '8': 'HANDOFF 235개/12개 제자리 적합, b9 54씬/768KB, Arcade shadow, 텍스트 클래스·미인덱스 규칙.',
        '9': 'HANDOFF Z11 폐기 및 §9 창 위치·매칭 실패 이력. 오버레이 수확 데이터는 삭제 사고로 현존하지 않아 과거 로그의 수치·스크린샷을 새 검증 증거로 사용하지 않음.',
        '10-11': 'active/Z10 §2.13 초상화 오진 정정, §2.14 최소 축약, §2.15 1바이트 코드·이름 재배치 실패, §2.16 전체 표기 복원.',
        '12-14': 'active/Z10 §2.17 타이틀, b18~b26 조사·trail·공용 페치·MPR 복원·메모·글리프 수정 기록.',
        '15': 'HANDOFF 상단 b26 테스트 배포판 + §7 멀티 BIN/적용 명령 + 현재 사용자 게이트 + active/Z10 §5 후속 트랙. 배포 README는 사용법만 참조.',
    }
    editorial = '# 작업기 작성 근거와 검증 경계\n\n작성일: 2026-10-10 (Asia/Seoul)\n\n기존 Tiny Toon 2 AuthorVoice 원고의 짧은 1인칭 존댓말·소량의 감정표현·실패→수정→교훈 전개를 참고했습니다. 개인 추억이나 완주 경험은 새로 만들지 않았습니다. 사용자 추가 지시에 따라 초기 조사부터 시간순으로 작성했습니다.\n\nHANDOFF와 Z10은 최신 추가 절 및 정정 사항을 우선했습니다. 안전판·예전 다음 행동 제목·조사 제거 규칙·남은 NOFIT 수치 등은 과거 단계가 섞여 있어 현황 수치로 복제하지 않았습니다. 235/12, 1053/99, 54씬, 55음절, 259/227 등은 본문에서 해당 조사/빌드 시점에 한정했습니다. b26 전체 플레이 PASS로 승격하지 않았습니다.\n\n## 절별 근거\n\n'
    editorial += '\n'.join(f'- §{key}: {value}' for key, value in sections.items())
    editorial += '\n\n## 이번 세션에서 한 검증\n\n- 원고·텍스트·HTML 문단 대응, 이미지 순서와 출처, 이미지 원본 바이트 동일성, 내장 PNG 동일성, UTF-8, ZIP CRC/허용 파일 검사를 수행합니다. 결과는 같은 폴더의 verification.json에 기록합니다.\n- 기존 스크린샷을 눈으로 확인했습니다. 에뮬레이터를 새로 실행하지 않았습니다.\n- 게임 정적 검증·게임 빌드·패치 실제 적용·새 런타임 스모크·전체 플레이·완주·실제 기기 검증은 이번 세션에서 수행하지 않았습니다.\n- HTML 렌더링은 별도 QA 결과가 있을 때만 확인한 범위로 기록합니다.\n'
    (QA / '작성_근거.md').write_text(editorial+'\n', encoding='utf-8')
    source_record = {'project_sources': [{'path': p, 'sha256': sha(ROOT/p)} for p in SOURCES],
                     'tone_reference': {'path': str(TONE), 'sha256': sha(TONE)},
                     'note': 'HANDOFF hash at publication build; publication session note may subsequently be appended.'}
    (QA / 'sources.json').write_text(json.dumps(source_record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    payload = sorted(p for p in PUB.rglob('*') if p.is_file() and p.name != 'SHA256.txt')
    assert len(payload) == 9
    (PUB / 'SHA256.txt').write_text(''.join(f'{sha(p)}  {p.relative_to(PUB).as_posix()}\n' for p in payload), encoding='utf-8')
    archive = PUB.parent / f'{NAME}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PUB.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(PUB).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == 10
        for p in PUB.rglob('*'):
            if p.is_file():
                assert z.read(p.relative_to(PUB).as_posix()) == p.read_bytes()
        assert all(Path(n).suffix.lower() in {'.md', '.txt', '.html', '.json', '.png'} for n in z.namelist())
    for entry in provenance:
        assert (ROOT / entry['source']).read_bytes() == (PUB / entry['image']).read_bytes()
    embedded = re.findall(r'data:image/png;base64,([A-Za-z0-9+/=]+)', page)
    assert len(embedded) == 4
    for b64, (rel, _) in zip(embedded, captions):
        assert base64.b64decode(b64) == (PUB / rel).read_bytes()
    assert len(re.findall(r'^## ', md, flags=re.M)) == 15
    assert page.count('<h2 ') == 15
    assert len(plain) == len(parts)
    for p in PUB.rglob('*'):
        if p.is_file() and p.suffix != '.png':
            assert '\ufffd' not in p.read_text(encoding='utf-8-sig')
    report = {'status': 'PASS', 'date': '2026-10-10', 'sections': 15, 'figures': 4,
              'package_files': 10, 'archive': str(archive), 'sha256': sha(archive),
              'checks': ['utf8', 'section_and_plaintext_paragraph_parity', 'sequential_figure_markers',
                         'original_capture_byte_equality', 'embedded_png_byte_equality', 'zip_crc',
                         'zip_payload_equality', 'publication_only_extensions'],
              'new_game_validation': False, 'board_posted': False}
    (QA / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    main()
