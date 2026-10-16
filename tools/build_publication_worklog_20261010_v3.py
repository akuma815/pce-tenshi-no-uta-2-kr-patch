"""Insert detailed evidence figures beside the unchanged original narrative."""
import base64
import html
import json
import re
import zipfile
from pathlib import Path
import build_publication_worklog_20261010 as base
from build_publication_visuals_20261010_v3 import NAME,PUB,QA

CSS='''*{box-sizing:border-box}body{margin:0;background:#f1f4f6;color:#25333d;font:18px/1.95 "Malgun Gothic",sans-serif}header{background:#183b4b;color:white;padding:40px 22px}header>div,main{max-width:1060px;margin:auto}h1{font-size:30px;line-height:1.6;margin:0 0 16px}header p{color:#dfedf0;font-size:16px}main{padding:20px 25px 70px;background:white}h2{font-size:25px;line-height:1.6;margin:65px 0 22px;border-bottom:3px solid #39897d;padding-bottom:13px}p{margin:22px 0;overflow-wrap:anywhere}figure{margin:35px 0 40px;padding:13px;background:#f0f4f6;border:1px solid #d0dce2;border-radius:8px}figure button{display:block;width:100%;padding:0;border:0;background:none;cursor:zoom-in}figure img{display:block;width:100%;height:auto}figcaption{margin-top:13px;font-size:16px;line-height:1.8;color:#455f6c}.figlabel{font-weight:bold;color:#277565}dialog{max-width:95vw;max-height:92vh;width:min(1360px,95vw);padding:15px;overflow:auto;border:1px solid #aaa;border-radius:8px}dialog::backdrop{background:#000a}dialog button{position:sticky;left:0;top:0;padding:8px 18px;font:16px "Malgun Gothic";z-index:2}dialog p{font-size:15px;margin:10px 0}dialog img{display:block;width:1280px;max-width:none;height:auto}nav{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}nav a{color:#e6f5f1;border:1px solid #547b86;padding:4px 10px;border-radius:4px;text-decoration:none}@media(max-width:600px){body{font-size:17px}header{padding:28px 18px}main{padding:8px 16px 45px}h1{font-size:25px}h2{font-size:22px;margin-top:48px}figure{padding:7px;margin:26px 0}figcaption{font-size:15px}}'''
SCRIPT='''const d=document.querySelector('dialog');document.querySelectorAll('.zoom').forEach(b=>b.addEventListener('click',()=>{d.querySelector('img').src=b.querySelector('img').src;d.querySelector('img').alt=b.querySelector('img').alt;d.showModal();d.scrollTop=0;d.scrollLeft=0;}));d.querySelector('button').addEventListener('click',()=>d.close());d.addEventListener('click',e=>{if(e.target===d)d.close()});'''

def main():
    manifest=json.loads((QA/'visual_manifest.json').read_text(encoding='utf-8'))
    assert len(manifest)==36
    original=(base.PUB/'작업기.md').read_text(encoding='utf-8')
    original=re.sub(r'\n!\[.*?\]\(images/\d{2}\.png\)\n','\n',original)
    original=original.replace('이번 글의 화면은 작업 과정에서 남긴 서로 다른 빌드의 캡처입니다.',
        '이번 글에는 작업 과정에서 남긴 실행 캡처 31장과 시안·자원 분석 이미지 3장을 활용한 비교 자료, 그리고 기록 기반 설명도를 합쳐 36장을 넣었습니다. 화면마다 당시 빌드와 조건을 적고, 실패 화면이 남아 있지 않은 부분은 설명도로 구분했습니다.')
    blocks=re.split(r'\n\s*\n',original.strip())
    result=[];section=0;paragraph=0;seen=[]
    for block in blocks:
        result.append(block)
        if block.startswith('## '):section=int(block[3:].split('.')[0]);paragraph=0
        elif section:
            paragraph+=1
            for m in manifest:
                if m['section']==section and m['after_paragraph']==paragraph:
                    result.append(f'![{m["caption"]}]({m["image"]})')
                    seen.append(m['number'])
    assert seen==list(range(1,37)),seen
    md='\n\n'.join(result)+'\n'
    (PUB/'작업기.md').write_text(md,encoding='utf-8')
    rendered=[];plain=[];title=''
    for block in result:
        if block.startswith('# '):title=block[2:];plain.append(title)
        elif block.startswith('## '):
            sec=int(block[3:].split('.')[0]);rendered.append(f'<h2 id="s{sec}">{html.escape(block[3:])}</h2>');plain.append(block[3:])
        elif block.startswith('!['):
            caption,rel=re.fullmatch(r'!\[(.*?)\]\((images/\d{2}\.png)\)',block).groups()
            n=int(Path(rel).stem)
            image=base64.b64encode((PUB/rel).read_bytes()).decode('ascii')
            rendered.append(f'<figure id="f{n:02}"><button class="zoom" aria-label="자료 {n:02} 원본 크기로 보기"><img src="data:image/png;base64,{image}" alt="{html.escape(caption)}"></button><figcaption><span class="figlabel">자료 {n:02} · </span>{html.escape(caption)}</figcaption></figure>')
            plain.append(f'[이미지 삽입: {rel}]\n자료 {n:02}. {caption}')
        else:rendered.append('<p>'+html.escape(block)+'</p>');plain.append(block)
    nav=''.join(f'<a href="#s{n}">{n}절</a>' for n in range(1,16))
    initial=base64.b64encode((PUB/manifest[0]['image']).read_bytes()).decode('ascii')
    page=f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style></head><body><header><div><h1>{html.escape(title)}</h1><p>2026.10.10 · 초기 시도부터 b26 테스트판 준비까지<br>비교·설명 자료 36장 · 기존 실행 캡처 31장 및 시안·자원 분석 이미지 3장 활용<br>이미지를 클릭하면 원본 크기로 열립니다. 확대 창에서는 좌우·위아래로 스크롤할 수 있습니다.</p><nav>{nav}</nav></div></header><main>{"".join(rendered)}</main><dialog><button autofocus>닫기</button><p>1280px 원본 크기 · 스크롤해서 자세히 보기 · Esc로 닫기</p><img src="data:image/png;base64,{initial}" alt="확대 자료"></dialog><script>{SCRIPT}</script></body></html>'
    (PUB/'작업기.html').write_text(page,encoding='utf-8')
    (PUB/'카페_복사용_본문.txt').write_text('\n\n'.join(plain)+'\n',encoding='utf-8-sig')
    (PUB/'이미지_출처_구분.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    guide='''천사의 시 II 한국어화 작업기 v3 (2026.10.10)

1. 작업기.html을 열어 글과 36장의 자료를 확인합니다.
   그림 클릭 → 1280px 원본 확대, 스크롤 이동, 닫기 또는 Esc.
2. 카페_복사용_본문.txt를 네이버 게시판 편집기에 붙여 넣습니다.
3. [이미지 삽입: images/XX.png] 표시마다 해당 PNG를 넣고 삽입 표시를 지웁니다.
   이미지 순서는 01~36입니다. 각 그림 바로 아래 설명은 함께 게시합니다.
4. 작업기.md는 수정용 본문입니다. 그림 출처와 조건은 이미지_출처_구분.json에 있습니다.

이전 v1·v2는 보존되어 있습니다. 게시용 최신 수정본은 v3입니다.
실제 게임 화면은 과거 빌드의 원본 캡처를 HTML 문서 안에 그대로 넣어 배열했습니다.
필요한 부분 확대도 원본 이미지의 일부를 표시한 것입니다. 픽셀을 고치지 않았습니다.
각 패널의 ‘당시 실행 캡처 / 정적 자원 분석 / 정적 시안’ 표시를 유지해 주세요.
화면이 없는 초기 실패, Z11 자막, 이름 재배치, 겟피 오류 등은 기록 기반 설명도로 표시했습니다.
이 작업기는 게임·시스템 카드·패치·패처·세이브를 포함하지 않습니다.
초반 대사와 메모 내용이 포함되어 있습니다. 전체 플레이 검수나 최신 b26 완료 자료는 아닙니다.
게시 글 정리 중 게임 빌드·적용·에뮬레이터 실행·새 플레이 검수·네이버 게시는 하지 않았습니다.
'''
    (PUB/'업로드_안내.txt').write_text(guide,encoding='utf-8-sig')
    for p in PUB.iterdir():
        if p.suffix in {'.md','.txt','.json','.html'}:
            text=p.read_text(encoding='utf-8-sig');assert '\ufffd' not in text,p
            assert '???' not in text,p
    payload=sorted(p for p in PUB.rglob('*') if p.is_file() and p.name!='SHA256.txt')
    assert len(payload)==41,len(payload)
    (PUB/'SHA256.txt').write_text(''.join(f'{base.sha(p)}  {p.relative_to(PUB).as_posix()}\n' for p in payload),encoding='utf-8')
    archive=PUB.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PUB.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(PUB).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==42
        for path in z.namelist():
            assert z.read(path)==(PUB/path).read_bytes()
            assert Path(path).suffix in {'.md','.txt','.html','.json','.png'}
    assert page.count('<h2 ')==15 and page.count('<figure ')==36
    embedded=re.findall(r'data:image/png;base64,([A-Za-z0-9+/=]+)',page)
    assert len(embedded)==37
    for b,data in zip(manifest,embedded[:36]):assert base64.b64decode(data)==(PUB/b['image']).read_bytes()
    assert base64.b64decode(embedded[-1])==(PUB/manifest[0]['image']).read_bytes()
    # Each original paragraph is retained, except for the updated visuals inventory.
    original_blocks=[p for p in blocks if not p.startswith('![')]
    assert len(result)==len(original_blocks)+36
    for version in ['', '_v2']:
        old=base.ROOT/'workspace/publication'/f'Tenshi2_KR_Worklog_20261010{version}.zip'
        expected={'':'8ddbfd7140144f0a15551ec48e63465d7e8264891d192888b9700261c52e82f6','_v2':'a50862653f89c34c4293e6c2d3c23fcab743af4d267f81edb549818f4b2243bd'}[version]
        assert base.sha(old)==expected
    report=dict(status='PASS',sections=15,figures=36,package_files=42,zip_sha256=base.sha(archive),
        zip_bytes=archive.stat().st_size,md_sha256=base.sha(PUB/'작업기.md'),html_sha256=base.sha(PUB/'작업기.html'),
        previous_packages_unchanged=True,embedded_pngs_match=True,all_original_paragraphs_retained=True,
        no_rom_or_patch_payload=True,game_execution_performed=False)
    (QA/'packaging.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
