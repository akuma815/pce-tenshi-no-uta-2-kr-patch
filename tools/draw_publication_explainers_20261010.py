"""Draw record-based technical figures. These are not recreated game screens."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / 'workspace/publication/Tenshi2_KR_Worklog_20261010_v2'
QA = ROOT / 'qa/publication/Tenshi2_KR_Worklog_20261010_v2'
FONT = Path('C:/Windows/Fonts/malgun.ttf')
BOLD = Path('C:/Windows/Fonts/malgunbd.ttf')
W, H = 800, 930
FIGURES = [
    (1, '01', 'CD를 다시 만들 때의 첫 실수', [
        ('원본 단일 BIN의 구성', '트랙 1: 오디오 / 트랙 2: 게임 데이터\n트랙 3~34: 오디오', 'normal'),
        ('초기 오판 → LOAD ERROR', '2,048B 데이터 섹터를 2,352B RAW로 처리\n데이터와 뒤쪽 오디오 위치가 어긋남', 'fail'),
        ('수정 → 무변경 왕복부터 확인', 'CUE와 실제 트랙 형식에 맞춰 재조립\n나중에 원본 BIN·CUE와 해시 일치 확인', 'pass'),
    ], '이 도식은 당시 단일 BIN 기준입니다.\nRedump RAW 덤프에는 같은 섹터 처리를 적용하지 않습니다.',
     ['docs/retired/진행 내용.txt', 'docs/active/Z2_무수정_모듈_재조립.md']),
    (2, '02', '시스템 카드의 글꼴 한 칸 바꾸기', [
        ('일본어 출력 경로를 이용', '대사 문자 코드 → 시스템 카드 글꼴 요청\n한자 슬롯의 그림 出 → 한글 가', 'normal'),
        ('당시 확인한 범위', '한 글자 표시와 다음 페이지 진행 성공\n여러 슬롯 확장 때는 화면 손상으로 판단', 'normal'),
        ('나중에 뒤집힌 초기 판단', '8월 22일 카드와 실행 설정을 지정해 재시험\n기록된 부팅 화면 손상은 재현되지 않음', 'pass'),
    ], '한 글자·다글자 초기 화면을 재현한 그림이 아닙니다.\n실제 재검증 캡처는 작업기 7번에 별도로 실었습니다.',
     ['docs/retired/Task0_기준선.md', 'docs/active/전략_재검토_BIOS폰트_2026-08-22.md']),
    (3, '03', '한 글자 성공 → 여덟 글자 → 메모 실패', [
        ('한 글자 훅: 호출 위치부터 정정', 'CD 좌표 보정값을 두 번 더해 잘못된 곳을 수정\n실제 호출부로 고친 뒤 가 표시 성공', 'normal'),
        ('여덟 글자 시험: 표시 성공', '준비는다됐나페이\n원문의 16바이트 안에서 2바이트 코드 8개', 'pass'),
        ('메모 선택: 안정성 실패', '대사와 필드 메뉴는 표시됐지만 메모 진입 시 멈춤\n표시 성공만으로 전체 시험을 승인하지 않음', 'fail'),
    ], '문자열은 시험 기록의 표본입니다. 게임 화면이 아닙니다.\n당시 개별 실패의 세부 원인은 후속 격리 실험 대상이었습니다.',
     ['docs/retired/Task4_1글자_훅_PoC.md', 'docs/retired/Task5_필드_다글자_PoC.md',
      'translation/task4_field_hook_poc_v2_runtime.json', 'translation/task5_field_multiglyph_poc_runtime.json']),
    (4, '04', '같은 RAM에 다음 장면이 올라옵니다', [
        ('시작 필드', '관측 경로: 장면 뱅크 $68~$7F에 데이터 적재\n여기에 한글 글꼴을 계속 남겨두려는 시도', 'normal'),
        ('전투·탑으로 전환', '동일한 $68~$7F 영역에 다른 장면 데이터 적재\n관측한 96섹터 로드는 총 192KB를 교체', 'fail'),
        ('상주 방식의 문제', '영구 보관할 코드·글꼴과 게임 자산이 충돌\n장면을 넘어 유지할 여유 뱅크는 없었음', 'normal'),
    ], '첫 필드·전투·탑에서 관측한 교체 구조의 개념도입니다.\n모든 장면의 로드 크기가 192KB라는 뜻은 아닙니다.',
     ['docs/active/Z1_모듈_로더_카탈로그.md', 'docs/retired/Task.md', 'docs/HANDOFF.md']),
    (5, '05', '글꼴의 수명을 모듈과 맞춰보기', [
        ('초기 시도: 계속 살아 있는 공용 풀', '한글 코드·그림을 한 번 올리고 장면 전환 뒤에도 유지\n다른 모듈의 공간을 침범해 반복 실패', 'fail'),
        ('재설계: 모듈이 자기 자산 소유', '해당 모듈의 코드·글꼴·텍스트를 함께 관리\n모듈이 내려가면 자산도 함께 폐기', 'pass'),
        ('범위를 조금씩 넓힌 시험', '필드·전투 한 글자 → 전환·메모·탑 본문 확인\n당시 글리프 패키지: 1,053자 / 99개', 'normal'),
    ], '당시 모듈 방식의 설계도입니다. 현재 최종 방식과 구분합니다.\n패키지 생성은 게임 전체 번역·완주 검수 완료를 뜻하지 않습니다.',
     ['docs/retired/Task.md', 'docs/HANDOFF.md']),
    (9, '11', '에뮬레이터 자막 방식에서 막힌 곳', [
        ('글자 출력 순간 잡기', '게임이 일본어를 그리는 호출에서 원문을 수집\n원문과 번역문을 연결해 화면 위에 자막 표시', 'normal'),
        ('문장 매칭과 창 위치가 난관', '이름·숫자 치환은 문장 그대로 비교할 수 없음\n배경·초상화 갱신이 위치 추적에 섞임', 'fail'),
        ('10월 9일: 해당 경로 폐기', '자막 대신 시스템 카드 + 디스크 패치로 복귀\n렌더 경로 정보와 보충 번역은 일부 보존', 'normal'),
    ], '보존된 기록을 설명한 도식입니다. 당시 자막 화면이 아닙니다.\n오버레이 수확 원본 캡처는 소실되어 공개 그림으로 쓰지 않았습니다.',
     ['docs/HANDOFF.md', 'docs/retired/Z11_에뮬레이터_오버레이_설계.md']),
]

def wrap(draw, text, font, width):
    result = []
    for paragraph in text.split('\n'):
        line = ''
        for char in paragraph:
            if draw.textlength(line + char, font=font) > width and line:
                result.append(line.rstrip())
                line = char.lstrip()
            else:
                line += char
        result.append(line.rstrip())
    return result

def main():
    (PUB / 'images').mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    records = []
    for section, number, title, cards, note, sources in FIGURES:
        im = Image.new('RGB', (W, H), '#f0f4f8')
        d = ImageDraw.Draw(im)
        f_title = ImageFont.truetype(str(BOLD), 34)
        f_head = ImageFont.truetype(str(BOLD), 29)
        f_body = ImageFont.truetype(str(FONT), 26)
        f_note = ImageFont.truetype(str(FONT), 23)
        d.rectangle((0, 0, W, 150), fill='#162f48')
        d.text((34, 24), f'{section:02}  기록 기반 설명도', font=f_note, fill='#b9daee')
        lines = wrap(d, title, f_title, W-68)
        for i, line in enumerate(lines):
            d.text((34, 65+i*43), line, font=f_title, fill='white')
        y = 182
        for index, (heading, body, state) in enumerate(cards):
            accent = {'normal': '#316da6', 'fail': '#a63f40', 'pass': '#21745d'}[state]
            blines = wrap(d, body, f_body, W-116)
            height = 65 + 38*len(blines) + 25
            assert y+height < 810, (section, heading, y, height)
            d.rounded_rectangle((30, y, W-30, y+height), radius=14, fill='white', outline='#d2dde7', width=2)
            d.rounded_rectangle((30, y, 38, y+height), radius=4, fill=accent)
            d.text((54, y+16), heading, font=f_head, fill=accent)
            for j, line in enumerate(blines):
                d.text((54, y+66+j*38), line, font=f_body, fill='#203448')
            y += height
            if index < len(cards)-1:
                d.line((W//2, y+4, W//2, y+26), fill='#687e92', width=3)
                d.polygon([(W//2-7,y+19),(W//2+7,y+19),(W//2,y+27)], fill='#687e92')
                y += 34
        nlines = wrap(d, note, f_note, W-68)
        assert y+30+len(nlines)*34 < H-12, (section, y, nlines)
        for j, line in enumerate(nlines):
            d.text((34, y+24+j*34), line, font=f_note, fill='#526579')
        im.save(PUB / f'images/{number}.png')
        records.append({'section':section, 'image':f'images/{number}.png',
                        'kind':'record_based_explanatory_diagram', 'sources':sources,
                        'not_a_game_capture':True, 'not_to_scale':True})
    (QA / 'diagram_sources.json').write_text(json.dumps(records, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Record-based diagrams: {len(records)}')

if __name__ == '__main__':
    main()
