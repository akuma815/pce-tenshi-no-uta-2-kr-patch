"""Lay out existing evidence in HTML; screenshot pixels are never repainted."""
from pathlib import Path
import html
import json
from PIL import Image
import build_publication_worklog_20261010 as base
from publication_visual_utils import ROOT, Renderer, embedded

NAME='Tenshi2_KR_Worklog_20261010_v3'
PUB=ROOT/'workspace/publication'/NAME
QA=ROOT/'qa/publication'/NAME
BOARDS=[]
CURRENT=[]
E=html.escape

def flow(items):
    return '<div class="flow">'+''.join(f'<div><b>{E(a)}</b><p>{E(b)}</p></div>' for a,b in items)+'</div>'

def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+E(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+E(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'

def note(title,body,tone=''):
    return f'<aside class="{tone}"><b>{E(title)}</b><p>{E(body)}</p></aside>'

def shot(path,label,detail,kind='actual_emulator_capture',crop=None):
    p=ROOT/path
    assert p.is_file(),p
    with Image.open(p) as im:w,h=im.size
    CURRENT.append(dict(source=path,source_sha256=base.sha(p),kind=kind,label=label,
        crop=crop,dimensions=[w,h],newly_captured=False,source_bitmap_embedded_unchanged=True))
    if crop:
        x,y,cw,ch=crop
        assert 0<=x<x+cw<=w and 0<=y<y+ch<=h,(path,crop,w,h)
        image=f'<div class="crop" style="aspect-ratio:{cw}/{ch}"><img src="{embedded(p)}" style="width:{100*w/cw}%;left:{-100*x/cw}%;top:{-100*y/ch}%"></div>'
    else:
        image=f'<img class="screen" src="{embedded(p)}">'
    tag={'actual_emulator_capture':'당시 실행 캡처','static_resource_preview':'정적 자원 분석','static_mock':'정적 시안'}[kind]
    return f'<article class="capture"><div class="tag">{tag}</div><h3>{E(label)}</h3>{image}<p>{E(detail)}</p></article>'

def grid(*cells):return '<div class="grid">'+''.join(cells)+'</div>'

def board(sec,after,title,sub,body,caption,records=None):
    global CURRENT
    number=len(BOARDS)+1
    BOARDS.append(dict(number=number,section=sec,after_paragraph=after,title=title,subtitle=sub,
        body=body,caption=caption,sources=CURRENT,records=records or base.SOURCES,
        kind='evidence_composite' if CURRENT else 'record_based_diagram'))
    CURRENT=[]

def define():
    board(1,2,'처음 막힌 곳은 한글이 아니라 CD 재조립','초기 단일 BIN의 데이터 섹터 형식을 잘못 해석했습니다.',
        flow([('원본 CUE / 데이터 트랙','이 작업의 단일 BIN: 섹터당 2,048B'),('잘못된 재조립','2,352B RAW로 처리 + 불필요한 체크섬'),('결과','데이터·오디오 위치 어긋남 → LOAD ERROR')])+table(['항목','당시 단일 BIN','후에 지원한 Redump'],[['데이터 트랙','2,048B 단위','2,352B RAW 단위'],['재삽입 기준','CUE와 실제 파일 구간','멀티 BIN의 데이터 트랙'],['핵심','덤프 형식을 먼저 확인','초기 규칙을 그대로 적용하지 않기']]),
        '처음 LOAD ERROR가 났던 이유를 기록으로 정리했습니다. 당시 오류 화면은 남아 있지 않아, 화면을 복원하지 않고 섹터 형식과 재조립 과정을 그렸습니다.')
    board(1,4,'원본과 같은 파일로 돌아올 수 있어야 했습니다','아무것도 바꾸지 않은 추출·재조립이 비교 기준이 됐습니다.',
        flow([('원본 보존','BIN · CUE · 데이터 트랙'),('무변경 추출·재조립','번역도 코드 수정도 없는 경로'),('기준선 확인','각 파일의 SHA-256 일치')])+note('확인한 것','Z2 기록: Track 02, 전체 BIN, CUE가 각각 원본과 동일했습니다. 이후 바이트가 달라지는 시험의 기준선입니다.')+note('확인 범위','해시 일치는 무변경 파일의 동일성 검사입니다. 한글 패치의 플레이 검수까지 대신하지는 않습니다.'),
        '원본과 무변경 재조립본을 비교한 절차입니다. 이후 실패를 구분할 기준부터 마련했습니다. 기록 기반 설명도입니다.')
    board(2,1,'첫 실험은 한자 한 칸을 ‘가’로 바꾸는 것이었습니다','시스템 카드의 기존 글꼴 호출을 그대로 이용한 한 글자 시험입니다.',
        flow([('첫 대사의 문자 코드','기존 ‘出’ 코드가 요청됨'),('시스템 카드 글꼴 슬롯','해당 칸의 그림만 ‘가’로 교체'),('기존 GETFNT 호출','교체된 그림을 받아 한글 표시')])+note('처음 확인한 결과','첫 대사 한 글자 표시와 다음 페이지 진행을 확인했습니다. 번역문 전체를 넣은 시험은 아니었습니다.')+note('왜 의미가 있었나','화면에 그릴 글자 그림을 시스템 카드가 공급한다는 경로를 직접 확인할 수 있었습니다.'),
        '첫 한 글자 시험의 구조입니다. 초기 임시 캡처는 남아 있지 않아 실제 출력 화면 대신 코드→글꼴 슬롯→출력 경로를 설명했습니다.')
    board(2,3,'같은 실패처럼 보여도 원인 판정은 바뀌었습니다','초기 기각과 8월 22일 재검증을 시간 순서로 구분했습니다.',
        flow([('초기 시험','2글자 · 18글자 · 896슬롯 확대 후 타일 손상으로 기록'),('당시 판단','시스템 카드 수정이 원인이라고 보고 게임 RAM 방식으로 전환'),('8월 22일 재시험','카드·게임·설정을 지정 → 손상 재현 안 됨')])+note('나중에 정정한 결론','‘시스템 카드를 바꾸면 화면이 깨진다’는 초기 판정은 철회했습니다. 초기 환경의 어떤 설정이 섞였는지까지 복원한 것은 아닙니다.','bad'),
        '초기 실패 판정과 나중에 철회한 판단을 나눴습니다. 재검증의 실제 부팅 화면은 7절에서 비교했습니다. 기록 기반 설명도입니다.')
    board(3,2,'글꼴보다 먼저 ‘이 코드가 실행되는가’를 확인했습니다','섹터 좌표의 보정값을 두 번 더해 다른 호출부를 고친 것이 첫 원인이었습니다.',
        flow([('읽기 기록의 섹터 좌표','파일 위치로 변환'),('보정값 중복 적용','실제 첫 대사와 다른 GETFNT 호출부 수정'),('무조건 ‘가’ 반환 시험','화면 변화 없음 → 호출 위치부터 재추적')])+note('수정 방향','실제로 첫 대사를 그리는 호출부로 옮기고, 한 글자 출력부터 다시 확인했습니다.')+note('실패가 알려준 것','글꼴 데이터가 맞아도 해당 코드에 도달하지 않으면 출력은 바뀌지 않습니다.'),
        '훅을 잘못 건 첫 시도와 위치를 바로잡은 과정을 그렸습니다. 이 초기 시험의 화면은 현재 보존되어 있지 않습니다.')
    board(3,4,'한글 여덟 글자는 나왔지만 메모에서는 멈췄습니다','표시 시험과 장면 전환 안정성은 다른 결과였습니다.',
        '<div class="specimen">준 · 비 · 는 · 다 · 됐 · 나 · 페 · 이</div>'+table(['시험','기록한 결과','해석'],[['첫 대사 16B 안의 8글자','서로 다른 한글 표시','받침 포함 글리프 구분 확인'],['문장 의미','준비는다됐나페이','번역문이 아닌 출력 표본'],['메모 진입','에뮬레이터 응답 중단','표시 성공만으로 안정성 확인 불가']])+note('이때의 한계','이 개별 정지의 원인을 모두 확정한 것은 아닙니다. 뒤의 RAM 소유·수명 조사와 구분해서 읽어야 합니다.','bad'),
        '초기 다글자 시험의 문자를 확대해 적고, 메모 실패를 별도 결과로 표시했습니다. 화면 재현이 아닌 당시 기록의 설명도입니다.')
    board(4,3,'장면이 바뀌면 같은 RAM의 주인도 바뀌었습니다','관측한 시작 필드·첫 전투·탑 경로의 수명 관계를 단순화했습니다.',
        flow([('시작 필드','장면 코드·데이터를 RAM에 적재'),('전투 / 필드 복귀','같은 영역에 다른 장면 데이터를 올림'),('탑 / 메모 전환','상주 한글 코드·글꼴과 자리 충돌')])+ '<div class="banks"><div>필드 데이터</div><div>전투 데이터</div><div>탑 데이터</div></div>'+note('관측 범위','해당 경로에서 192KB 영역 교체를 확인했습니다. 전체 게임의 모든 로드가 같은 크기라는 뜻은 아닙니다.')+note('버린 전제','지금 비어 보이는 RAM을 영구적인 한글 저장소로 쓰기. 조사한 뱅크들에서는 상주 풀을 위한 영구 여유 뱅크를 찾지 못했습니다.','bad'),
        '공용 RAM에 계속 남겨두려던 방식이 장면 전환과 충돌하는 이유입니다. 크기 비례 배치도가 아닌 관측 경로의 수명 설명도입니다.')
    board(5,3,'장면이 쓰는 자산은 그 장면과 함께 내려가도록','상주 풀 대신 모듈 단위로 나눠 갖는 방향을 시도했습니다.',
        grid(note('초기 방식','공용 코드 + 전역 글꼴 → 장면 교체 후에도 남아 있어야 함','bad'),note('모듈 단위 방식','장면 코드 + 그 장면의 글꼴 → 장면 적재·해제와 수명을 맞춤'))+flow([('무변경 재조립','원본과 동일한 시작점'),('작은 표시 시험','필드 · 전투 · 메모 · 탑'),('패키지 확대','당시 1,053글리프 / 99패키지')])+note('다음 난관','문장 저장 길이와 디스크 공간, RAM 적재 위치를 함께 풀어야 했습니다. 99패키지는 작업 규모이며 완성률이 아닙니다.'),
        '모듈 단위 설계와 확인 순서입니다. 당시 1,053자·99패키지라는 수치의 범위도 함께 적었습니다. 기록 기반 설명도입니다.')
    b4='translation/b4_debug_2026-08-23/v9_probe/'
    board(6,2,'여러 번 고쳐도 전투 화면은 계속 깨졌습니다','같은 증상이 이어진 진단 캡처들입니다. 원인 분리는 다음 시험에서 이뤄졌습니다.',
        grid(shot(b4+'run2_origcard/mark1_f6573.png','원본 카드로 실행한 진단','카드를 원본으로 되돌린 조건에서도 전투 손상이 남았습니다.'),shot(b4+'run4_v14/mark1_f11605.png','V14 진단','코드 공간 가설을 분리한 뒤에도 손상이 보였습니다.'),shot(b4+'run5_v16/mark1_f6300.png','V16 진단','후속 진단에서도 전투 창과 그래픽 손상이 이어졌습니다.'))+note('캡처만으로 알 수 없는 것','반복된 깨짐만 보고 RAM 복원 실패로 확정할 수는 없었습니다. 각 시험의 조건과 바뀐 범위를 함께 봐야 했습니다.','bad'),
        '원본 카드·V14·V16 조건에서 남긴 실패 화면을 모았습니다. 같은 프레임 비교는 아니며, 반복된 증상을 보여주는 진단 자료입니다.')
    board(6,2,'V17: 게임 코드는 그대로 두고 14섹터만 바꿨습니다','LBA 5480..5493은 빈 공간이 아니라 전투가 소비하는 자산이었습니다.',
        grid(shot(b4+'run6_v17/mark1_f7294.png','V17 실제 전투 화면','원본 코드 상태에서 해당 14섹터만 교체한 시험입니다.'),shot(b4+'run6_v17/mark1_f7294.png','전투 창 주변 확대','같은 화면의 아래쪽 영역을 확대했습니다. 원본 픽셀은 바꾸지 않았습니다.',crop=[0,170,341,60]))+flow([('한 읽기 함수의 관측','이 구간 접근 0건'),('내용 교체로 확인','14섹터 변경만으로 손상 재현'),('수정한 결론','다른 읽기 경로가 사용하는 라이브 자산')])+note('오진 정정','이전 RAM 상주·복원 문제로 설명했던 b4 계열 전투 손상의 원인 귀속을 수정했습니다. $E009 훅만으로 모든 CD 읽기를 관측한 것은 아니었습니다.','bad'),
        '전투 손상의 원인을 분리한 V17 전체 화면과 부분 확대입니다. 14섹터 교체 결과와 읽기 관측의 한계를 같이 설명했습니다.')
    board(6,3,'반대로 ‘못 읽는다’고 버린 구간은 다시 쓸 수 있었습니다','9178+ 읽기 실패의 pregap 원인 설명도 나중에 정정했습니다.',
        flow([('초기 실패','ReadLBA_2048 예외 발생'),('당시 해석','트랙 3 오디오 pregap이라 사용 불가'),('재확인 / V18','디스크 처리 코드 확인 + 9178+ 실제 읽기 성공')])+table(['판정','정정한 내용'],[['남겨야 할 사실','초기 구조에서 읽기 예외가 났음'],['철회한 원인','9178+는 오디오라 읽을 수 없다는 설명'],['후속 근거','V18에서 해당 구간 적재를 실증']])+note('교훈','실패 로그를 보존하는 것과 그때 붙인 원인 설명을 유지하는 것은 별개였습니다.'),
        'LBA 9178 이후 구간의 사용 금지 판정을 정정한 흐름입니다. 예외가 났다는 사실과 잘못 붙인 원인을 나눠 적었습니다. 기록 기반 설명도입니다.')
    board(6,4,'전투만 넘겨도 새 마을과 탑에서 다시 막혔습니다','후속 b7 계열의 다른 장면 손상입니다. V17과 같은 원인으로 묶지 않았습니다.',
        grid(shot(b4+'run8_b7/mark1_f14865.png','b7 진단: 맵 손상','새 장면에서도 안전할 것이라는 가정을 다시 확인해야 했습니다.'),shot(b4+'run9_b73_tower/mark1_f22863.png','b7.3 진단: 탑 손상','전투 통과와 다른 맵의 자산 보존은 별개였습니다.'))+flow([('놓친 관측','장면 로드 직후의 그래픽 초기화'),('상태별 소비','아이템 아이콘 등 특정 상황의 데이터'),('넓힌 확인 범위','로드 직후 + 전투 + 맵 이동 + 메뉴·아이템')]),
        '후속 맵·탑 손상 캡처를 비교했습니다. 전투 손상 실험과 빌드가 다르며, 장면과 상태별 관측을 넓힌 이유를 보여줍니다.')
    bio='translation/bios_retest_2026-08-22/'
    board(7,2,'처음 포기했던 카드들을 같은 조건에서 다시 비교했습니다','2026.08.22 · f800 부팅 화면 · 당시 설정을 지정한 재검증',
        grid(*[shot(bio+f'{tag}_f800.png',label,'부팅 화면의 비교 표본입니다.') for tag,label in [('R0_original','R0 원본 카드'),('R1_two_glyph','R1 두 글자 카드'),('R2_18glyph','R2 18글자 카드'),('R4_diag896','R4 896슬롯 카드')]])+note('원본과 같은 결과','기록상 R0~R4 비교 화면은 픽셀 단위로 같았습니다. 현재 패키지에서도 이 네 f800 원본 PNG 해시가 같은지 검사합니다.')+note('범위','부팅 화면의 일치는 모든 글리프 호출과 장면 검수의 완료를 뜻하지 않습니다.'),
        '재검증 당시 원본·두 글자·18글자·896슬롯 카드의 부팅 화면을 한 장에 모았습니다. 현재 파일도 네 PNG의 해시 일치를 확인했습니다.')
    board(7,4,'카드 글꼴 공급은 가능했지만 문장 공간은 별도였습니다','남아 있는 b4 대사 캡처로 실제 한글 출력도 함께 확인할 수 있습니다.',
        grid(shot(bio+'b4_first_korean_dialogue.png','b4 첫 한글 대사 캡처','재검증 폴더에 보존된 b4 출력입니다. 초기 ‘가’ 한 글자 시험의 화면은 아닙니다.'),note('시스템 카드가 맡는 것','요청한 한글 코드의 글자 그림을 공급합니다. 게임 RAM에 전역 글꼴 풀을 상주시키는 문제를 줄일 수 있습니다.'))+note('남은 두 문제','길어진 번역문을 어디에 저장할지, 디스크 패치와 시스템 카드 패치를 어떻게 함께 적용할지는 따로 해결해야 했습니다.'),
        'b4에서 실제로 표시한 한글 대사와 시스템 카드 방식의 역할을 묶었습니다. 초기 한 글자 실험과 현재 b26 화면으로 오인하지 않도록 시점을 표시했습니다.')
    board(8,1,'화면 길이가 비슷해도 저장 바이트는 늘어났습니다','당시 필드 대사 235개 중 제자리 적합은 12개였습니다.',
        '<div class="ratio"><div style="width:5.106%"></div></div><div class="metrics"><b>12 / 235</b><span>약 5.1%만 제자리 적합</span><b>223개</b><span>당시 번역 기준 제자리 초과</span></div>'+table(['저장 방식','바이트 길이 문제'],[['원문','한자 2B + 가나 1B가 섞임'],['초기 한글','각 음절을 2B로 저장'],['일반 대사','원문 주소로 조회해 별도 저장소에서 읽기'],['직접 RAM 읽기 항목','제자리 치환·확인된 메뉴 공간 재배치']])+note('범위','이 수치는 당시 조사한 필드 레코드와 번역의 적합률입니다. 게임 전체 번역률이나 현재 최종 적합률이 아닙니다.'),
        '당시 필드 대사 235개와 12개 적합을 비율로 그렸습니다. 대사와 직접 RAM을 읽는 메뉴를 다른 경로로 처리한 이유입니다. 기록 기반 설명도입니다.')
    board(8,3,'파일에는 데이터가 있는데 실제 읽기는 0이었습니다','b9 카드 확장의 실패와 회피 배치 후 출력입니다. 같은 프레임 비교는 아닙니다.',
        grid(shot('translation/b9_runtime_v1_fail_2026-08-28/walk_f23998.png','b9 v1: 마지막 검은 화면','실패 런의 말미 캡처입니다. 검은 화면만으로 원인을 판별한 것은 아닙니다.'),shot('translation/b9_runtime_v3_pass_2026-08-28/pocserve_03_f03544.png','b9 v3: 첫 대사 표시','Arcade Card RAM에 가리는 뱅크를 피한 후 출력 경로를 확인했습니다.'))+flow([('확장 카드 파일','768KB 안에 데이터 존재'),('실제 버스 읽기','일부 뱅크 $40~$43은 RAM 창에 가림'),('회피 배치','가리는 구간을 건너뛰어 조회')])+note('확인 범위','54개 씬 대상 조회 구조를 만든 기록입니다. 이 두 화면으로 54개 씬 전체 검수를 주장하지 않습니다.'),
        'b9 v1 실패 런과 v3 출력 캡처를 비교했습니다. 파일의 데이터와 실제 버스 읽기가 달랐다는 당시 원인 기록을 곁들였습니다.')
    board(8,4,'일본어가 남았을 때 번역문부터 늘리지는 않았습니다','번역 누락과 ‘다른 사본을 읽음’을 구분해야 했습니다.',
        flow([('화면에 원문 잔존','어디에서 읽은 문장인가?'),('추출 목록과 대조','첫 이름 · 다른 사본 · 연결 레코드 누락 점검'),('실제 소비 주소 확인','그 주소의 레코드를 번역·패치')])+table(['원인 후보','필요했던 확인'],[['첫 이름 추출 누락','목록의 시작 경계'],['별도 사본 사용','런타임이 읽은 원래 주소'],['문장 연결 레코드 누락','여러 문장을 이은 구조']]),
        '번역이 있는데 화면에 원문이 남는 경우의 확인 순서입니다. 소비한 사본과 추출 경계를 먼저 찾았습니다. 기록 기반 설명도입니다.')
    board(9,2,'글자가 그려지는 순간과 창 위치는 바로 연결되지 않았습니다','Z11 자막 실험의 위치 추적 난관 · 당시 수확 캡처는 남아 있지 않습니다.',
        flow([('창을 열 때','배치표가 타일 슬롯을 가리킴'),('글자를 그릴 때','같은 슬롯의 글자 그림만 덮어씀'),('추적이 꼬인 이유','배경·초상화 갱신이 함께 섞임')])+table(['시도한 관측','당시 기록'],[['글자 직후 배치표 쓰기','277글자에 1건'],['창 영역에 한정한 배치표 비교','변경 0셀인 경우'],['영역 한정 + 타일 매칭','초상화 버스트 0셀 / 다른 버스트 509셀']])+note('이 자료의 종류','해당 Z11 관측 기록을 도식화했습니다. 게임 자막이나 실패 화면을 새로 합성하지 않았습니다.'),
        '폐기한 자막 경로의 위치 추적 실패를 수치와 구조로 정리했습니다. Z11 원본 캡처가 삭제된 상태라 기록 설명도로 표시했습니다.',records=['docs/HANDOFF.md','docs/retired/Z11_에뮬레이터_오버레이_설계.md'])
    board(9,3,'문장 매칭도 이름과 숫자가 들어가면 복잡해졌습니다','Z11에서 얻은 정보는 남겼지만 최종 경로로 채택하지 않았습니다.',
        flow([('원문 패턴 분리','고정 문장 + 이름·숫자 자리'),('매칭·치환','번역 후보 찾기 + 이름 채우기'),('남은 문제','잘못된 필터 / 앞 문맥까지 이름으로 포획')])+grid(note('후보 필터 오류','번역문이 있어도 사용하지 못하는 조건이 있었습니다.','bad'),note('치환 범위 오류','이름 자리에 앞 문맥까지 잡혀 일본어가 남기도 했습니다.','bad'))+note('2026.10.09 종료','에뮬레이터 자막 경로를 접고 수정 시스템 카드 + 디스크 패치 방식으로 돌아왔습니다.'),
        '자막 실험의 문장 매칭·치환 실패와 종료 결정을 정리했습니다. 실제 자막 화면의 복원 자료는 아닙니다.',records=['docs/HANDOFF.md','docs/retired/Z11_에뮬레이터_오버레이_설계.md'])
    board(10,2,'확인용 값이 그대로여도 훅에는 들어오고 있었습니다','초상화 대사를 별도 출력기로 판단했던 오진의 구조입니다.',
        flow([('실제 실행','훅에 진입'),('초기 조건문','해당 스트림 거부 → 바로 복귀'),('확인용 값 쓰기','앞에서 빠져나가므로 실행되지 않음')])+grid(note('처음 해석','값이 안 바뀜 → 훅을 전혀 타지 않는 다른 출력기','bad'),note('실행 추적 후','훅은 호출됨 → 진입 조건이 막고 있음'))+note('수정','누락된 스트림을 처리하도록 조건을 수정했습니다. 이미 카드에 있던 번역문을 읽을 수 있게 됐습니다.'),
        '초상화 대사에서 확인용 값이 변하지 않았던 이유입니다. ‘호출 안 됨’과 ‘호출 후 조기 복귀’를 구분했습니다. 기록 기반 설명도입니다.')
    portrait='translation/b13_fetch_trace/'
    board(10,3,'b13: 시작 스테이트의 일본어에서 한글 다음 페이지까지','한 검증 런의 진행 화면입니다. 서로 다른 실패·수정 빌드 비교가 아닙니다.',
        grid(shot(portrait+'portrait_b13_0.png','시작 시점: 이전 화면이 남아 있음','불러온 스테이트의 기존 일본어 화면입니다.'),shot(portrait+'portrait_b13_300.png','진행 후: 한글 초상화 대사','기억을 잃은 소녀에 관한 대사가 표시됐습니다.'),shot(portrait+'portrait_b13_750.png','다음 페이지: 길어진 한글 본문','원래 길이로 줄이지 않고 읽는 경로를 확인했습니다.'))+note('확인 범위','당시 83종으로 분류한 초상화 대사의 해결 경로를 확보했습니다. 이 표본이 83종 전수 플레이 검수는 아닙니다.'),
        'b13의 시작 화면·한글 대사·다음 페이지를 묶었습니다. 같은 런의 진행이며, 시작 일본어는 불러온 스테이트에 남은 화면입니다.')
    board(11,1,'1~3바이트 부족 때문에 이름 전체를 줄여야 했습니다','창의 크기보다 먼저 원래 저장 슬롯의 부족분을 계산했습니다.',
        table(['당시 비교','결과'],[['축약 후보 전체','94종'],['필요한 부족분만 해결한 단계','20종 축약 사용'],['메뉴·이름 슬롯','1~3B 부족도 제자리 삽입 불가']])+flow([('전체 축약 후보','뜻이 흐려지는 이름도 생김'),('슬롯별 부족분 계산','정말 초과한 항목만 선택'),('다음 접근','자주 쓰는 음절의 저장 바이트 줄이기')]),
        '축약 후보를 모두 쓰기보다 필요한 슬롯만 해결한 과정을 숫자로 정리했습니다. 당시 단계의 계산 기록이며 현재 이름 전수 검수는 아닙니다.')
    board(11,2,'글자 크기를 줄이지 않고 저장 바이트를 줄였습니다','기존 1바이트 카타카나 변환표의 55칸을 한글 음절에 활용했습니다.',
        flow([('문장에 저장','선택한 한글 음절은 1B 코드'),('기존 변환표','1B → 2B 글꼴 코드로 변환'),('시스템 카드','같은 크기의 한글 그림 출력')])+table(['방식','저장 크기','출력 크기'],[['보통 한글 음절','2B','기존 글리프 크기'],['선택된 55칸 음절','1B','같은 글리프 크기']])+note('후속 계산','b16 메뉴 작업: 축약 오버라이드 259종 중 227종을 전체 표기로 되돌릴 수 있다는 계산 결과를 얻었습니다. 실플레이 전수 확인 수치는 아닙니다.'),
        '1바이트 코드→변환표→한글 글꼴의 관계입니다. 글자 그림을 축소한 방식이 아니라 저장 길이를 줄인 방식입니다. 기록 기반 설명도입니다.')
    board(11,5,'이름 처리에서는 두 가지 다른 실패가 나왔습니다','옮긴 이름을 못 찾는 문제와, 누락된 원문이 새 표로 읽히는 문제입니다.',
        grid(note('재배치 실패: 이름 없는 ‘출현!’','이름 블록을 옮긴 뒤 원래 주소를 읽는 배틀 경로가 남았습니다. 옛 주소를 비우니 이름을 못 읽었습니다.','bad'),note('누락 실패: 뜻 없는 한글 이름','번역하지 않은 ‘패밀리어’의 1바이트 원문이 바꾼 변환표로 읽혔습니다. 원문 바이트 역산으로 누락 사본을 찾았습니다.','bad'))+flow([('재배치 실패의 수정','이름은 옮기지 않고 제자리 치환'),('누락 이름의 수정','실제 읽는 사본을 찾아 보완'),('공통 교훈','포인터 표 하나만으로 모든 참조를 설명할 수 없음')])+note('남은 자료의 한계','이 두 사례의 직접 오류 캡처는 이번 조사에서 확보하지 못했습니다. 이름 없는 창이나 뜻 없는 이름을 새로 만들어 넣지 않았습니다.'),
        '이름 재배치와 미번역 1바이트 사본의 실패를 분리했습니다. 직접 오류 화면은 없어 당시 기록으로만 설명했습니다.')
    title='translation/title_probe/'
    board(12,1,'타이틀은 배경 글자가 아니라 스프라이트 셀이었습니다','원본 실행 화면과 정적 셀 분석 자료를 함께 보면 작업 단위가 보입니다.',
        grid(shot(title+'shot_f3300.png','원본 타이틀 실행 화면','일본어 로고와 II, 금색 장식을 기준으로 삼았습니다.'),shot(title+'logo_cells_matched.png','셀 경계를 표시한 분석 이미지','분홍 격자는 작업용 표시입니다. 실제 게임 화면이 아닙니다.','static_resource_preview'),shot(title+'spr_sheet_pal0.png','팔레트 0 스프라이트 시트','타이틀 조각을 찾기 위한 정적 자원 미리보기입니다.','static_resource_preview'))+note('작업 단위','기존 셀 배치와 팔레트를 유지하고 33셀의 글자색 픽셀을 바꾸는 방식으로 진행했습니다.'),
        '원본 타이틀과 셀 경계·스프라이트 시트를 모았습니다. 분홍 격자와 시트는 분석용 정적 자료로 표시했습니다.')
    board(12,2,'시안에서 보인 파란 부분과 실제 화면은 달랐습니다','모형 이미지와 실행 캡처를 나란히 놓고 확인했습니다.',
        grid(shot(title+'mock_title_kr.png','정적 한글 시안','파란 부분은 시안 작업 표시입니다. 게임 화면의 잔재가 아닙니다.','static_mock'),shot('translation/b17_runtime/title_b17_b.png','b17 조정 후 실행 화면','실제 배경 위에서 로고가 보이는 결과입니다.'))+note('별도로 겪은 잘림 문제','좁은 캔버스에서 정렬·잘라내기를 하다 ‘시’의 ㅣ가 사라졌습니다. 글자 실제 폭을 먼저 재도록 고쳤습니다. 그 잘림 중간 화면은 여기의 시안과 동일하다고 주장하지 않습니다.','bad'),
        '파란 작업 표시가 있는 시안과 실제 실행 화면을 비교했습니다. ‘시’ 잘림 사례는 기록으로 적되, 이 시안을 그 오류 화면으로 제시하지 않았습니다.')
    board(12,3,'한글 본문 크기와 II를 포함한 가운데 정렬을 조정했습니다','두 장 모두 b17 단계의 실제 타이틀 캡처입니다.',
        grid(shot('translation/b17_runtime/title_b17.png','처음 표시한 한글 타이틀','본문이 크게 보이는 초기 출력입니다.'),shot('translation/b17_runtime/title_b17_b.png','크기·간격 조정 후','II 높이와 함께 묶어 중앙을 맞췄습니다.'))+note('비교한 것','원래 금색 장식과 빨간 II를 살리면서 본문 크기·간격·그룹 중심을 조절했습니다. 배경 프레임은 서로 다릅니다.'),
        '초기 한글 타이틀과 크기·배치 조정 후 화면입니다. 서로 다른 배경 프레임이며 서체·색감의 추가 검토는 남아 있습니다.')
    board(13,2,'조사 함수에 문자 대신 뱅크 번호가 들어갔습니다','뱅크를 바꾸는 코드 사이에서 반환 레지스터 A가 살아 있다고 가정했습니다.',
        flow([('원래 읽기 함수','문자 바이트 반환'),('뱅크 전환 코드','TMA / LDA #bank가 A를 덮음'),('조사 처리','문자가 아닌 $1F / $84를 받음')])+grid(note('상태값 문제','PRESENT는 게임 진행 여부가 아니라 씬 인덱스 유무였습니다. 전투 모듈 로드 때 0이 되어 조사를 막았습니다.','bad'),note('수정한 입력','디스패처가 저장해 둔 반환 바이트 $2D80을 읽도록 바꿨습니다.'))+note('왜 전투만 달랐나','전투는 이름을 조립한 문자열로 읽는 경로도 사용했습니다. 일반 대사의 임시 스트림 가정을 그대로 옮길 수 없었습니다.'),
        '조사 처리 초기의 레지스터·상태값·전투 이름 경로 문제를 정리했습니다. 같은 증상 안에도 원인이 여럿 있었습니다. 기록 기반 설명도입니다.')
    board(13,3,'b21에서는 조사가 나와도 ‘시온’ 이름이 깨졌습니다','한글 둘째 바이트와 조사 마커 $A0~$A3의 충돌이었습니다.',
        grid(shot('translation/b21_runtime/bprobe_04_f02157.png','b21: ‘벌룬이’와 깨진 파티 이름','헤더의 ‘시온’이 ‘시키 お’처럼 보이는 오류 표본입니다.'),shot('translation/b22_runtime/bprobe_01_f02693.png','b22: 둘째 바이트 보호 후','헤더의 ‘시온’과 ‘슈리커가’ 표시를 확인한 표본입니다.'))+grid(shot('translation/b21_runtime/bprobe_04_f02157.png','b21 이름 부분 확대','위 왼쪽 원본의 파티 헤더 부분입니다.',crop=[175,8,90,40]),shot('translation/b22_runtime/bprobe_01_f02693.png','b22 이름 부분 확대','위 오른쪽 원본의 같은 위치를 확대했습니다.',crop=[175,8,90,40]))+flow([('한글 2B 코드','첫째 바이트 → 둘째 바이트 대기'),('잘못된 순서','둘째 바이트도 조사 마커로 먼저 검사'),('수정한 순서','둘째 바이트 대기 중이면 마커 검사 생략')])+note('비교 조건','전투 종류와 프레임은 다릅니다. 헤더의 이름 손상·수정 표본 비교이며, HP/MP 수치는 진단 상태입니다.'),
        'b21의 깨진 ‘시온’과 b22의 정상 이름을 전체 전투 화면으로 비교했습니다. 적과 프레임이 다른 표본임을 표시했습니다.')
    board(13,3,'문자 읽기 함수는 장면 전환 명령도 읽고 있었습니다','공용 디스패처의 모든 바이트를 조사로 검사하면 안 됐습니다.',
        flow([('공용 읽기 함수','텍스트 + 비텍스트 바이트코드'),('마커 충돌','장면 전환 명령을 조사로 오해 → 멈춤'),('호출자 게이트','실제 프린터의 lead 읽기 $92F0에서만 처리')])+table(['관측한 호출','처리 범위'],[['$92F0 / $9334','글꼴 출력이 뒤따르는 lead / trail'],['메뉴 포맷·장면 명령 등','비텍스트 호출은 거부'],['거부 경로','뒤의 메모 문제에서 복원 위치를 추가 수정']])+note('한계','호출자 게이트로 범위를 줄인 뒤에도 메모 본문 결함이 남았습니다. 전투 출력 표본만으로 모든 경로가 안전하다고 보지 않았습니다.'),
        '문자와 장면 명령이 공유하는 읽기 경로를 나눴습니다. 호출 범위를 줄인 뒤 남은 메모 결함은 다음 절에서 설명했습니다. 기록 기반 설명도입니다.')
    board(13,4,'b22에서 확인한 조사 출력 표본을 모았습니다','각기 다른 메시지의 당시 실행 캡처입니다.',
        grid(shot('translation/b22_runtime/bprobe_01_f02693.png','슈리커가','받침 없는 이름 + 가'),shot('translation/b22_runtime/bprobe_03_f03548.png','네이짜리아가','다른 적 이름의 등장 메시지'),shot('translation/b22_runtime/bprobe_06_f05718.png','페이트는 7 피해','받침 없는 파티 이름 + 는'),shot('translation/b22_runtime/bprobe_07_f05835.png','시온은 8 피해','받침 있는 파티 이름 + 은'))+note('미완료 범위','이 빌드는 뒤에 메모·장면 전환 결함을 추가 수정했습니다. 띄어쓰기·문체와 전체 전투 검수는 별도 확인 대상입니다.'),
        'b22에서 남긴 등장·피해 메시지 네 화면을 모았습니다. 이름별 조사 표본이며 이후 메모 수정 전의 빌드입니다.')
    board(14,1,'메모 실패는 코드를 조금씩 빼보며 좁혔습니다','사용자 스테이트 + RAM 코드 변형 · 같은 출발점의 진단 비교',
        grid(shot('translation/b23_runtime/userstate_A/u_f090.png','A: 트램펄린에서 복귀','본문이 열린 PASS 표본입니다.'),shot('translation/b23_runtime/userstate_D/u_f090.png','D: 조사 실행 경로','본문 대신 목록에 남은 FAIL 표본입니다.'),shot('translation/b24_runtime/userstate_X/u_f090.png','X: 추적 경로만 실행','본문이 열린 PASS 표본입니다.'),shot('translation/b24_runtime/userstate_Y10/u_f090.png','Y10: 게이트에서 MPR5 복원','화면이 회색으로 무너진 FAIL 표본입니다.'))+table(['당시 변형','기록 판정'],[['A 복귀 / B post 제거 / C 조사 호출 제거','PASS'],['D · G · H 조사 실행','FAIL'],['X 추적만 / Y 마커만','PASS / FAIL'],['Z2 즉시 복귀 / Z3 인라인 브래킷','PASS'],['Y10 게이트에서 PLA TAM5','FAIL']])+note('판정 근거','PASS/FAIL은 당시 실행 추적·진단 기록의 판정입니다. f090의 정지 화면 하나만으로 행업을 판단한 것이 아닙니다.'),
        '메모 오류를 좁힌 A·D·X·Y10의 캡처와 당시 변형별 결과를 묶었습니다. 네 화면 모두 같은 사용자 스테이트 계열의 코드 변형 시험입니다.')
    board(14,2,'실행 중인 창의 뱅크를 바꾸면 다음 명령도 바뀝니다','메모의 거부 경로가 자기 실행 창을 복원하면서 탈선했습니다.',
        grid(note('실패한 복귀','카드 $5F의 MPR5 창에서 실행 → PLA TAM5 → 같은 주소가 원래 뱅크를 가리킴 → 이어질 PLX / CLC / RTS가 다른 바이트가 됨','bad'),note('b25 수정','거부 시 창 밖의 $1F gno 스텁으로 이동 → 거기서 MPR5 복원 → 원래 호출 경로로 복귀'))+flow([('메모 본문 사전 스캔','대량의 읽기 호출'),('텍스트 호출자 아님','모두 거부 경로로 감'),('고장 지점','수락 경로가 아닌 거부 복귀의 뱅크 복원')])+note('전투에서 덜 드러난 이유','조사를 제공하는 수락 경로는 다른 창으로 빠져나가 살아남았습니다. 같은 루틴도 어느 복귀 경로를 타느냐에 따라 결과가 달랐습니다.'),
        '메모에서 확정한 뱅크 복원 오류와 b25의 창 밖 복귀 스텁을 그렸습니다. 실제 메모 화면의 다음 명령을 새로 만들어 보여준 것은 아닙니다.')
    board(14,3,'b25에서는 메모 본문이 다시 열렸습니다','사용자 스테이트의 표시와 오래된 스테이트 사용의 한계를 나눴습니다.',
        grid(shot('translation/b25_runtime/userstate/u_f090.png','b25: 메모 항목의 초상화 본문','사용자 스테이트에서 다시 본문이 열린 화면입니다.'),shot('translation/b16_runtime/smoke_diag_status_150.png','별도 b16 스테이트 스모크','기존 이름 데이터가 섞여 보입니다. 새 게임의 패치 결과와 동일한 조건이 아닙니다.'))+note('당시 별도 새 게임 확인','b25 새 게임 메모 본문 런도 PASS로 기록됐습니다(서브 132건). 왼쪽은 사용자 스테이트 화면이며 그 새 게임 런의 캡처라고 제시하지 않습니다.')+note('스테이트 주의점','스테이트는 변경 전 엔진 RAM까지 되돌릴 수 있습니다. 디스크의 리더 코드를 고친 뒤 스테이트만 불러오면 옛 코드로 시험하게 될 수 있습니다.'),
        'b25의 메모 본문과 별도 b16 스테이트 화면을 묶었습니다. 두 화면은 전후 비교가 아니라, 메모 표시 확인과 검증 조건의 차이를 설명하는 자료입니다.')
    board(14,4,'마지막에는 짧은 헤더와 빠진 글꼴도 보완했습니다','b26의 메모 표시와 ‘겟’ 글리프 소스 누락을 각각 확인했습니다.',
        grid(shot('translation/b26_runtime/memonew/memo_list_full.png','b26: 주 메뉴의 ‘메모’ 항목','파일 이름과 달리 이 화면은 메모 본문이 아니라 주 메뉴입니다.'),note('‘겟피’ 첫 글자가 한자로 나온 이유','배정 코드 93CE는 있었지만 카드 소스 full_v3에는 ‘겟’ 그림이 없었습니다. 원래 한자 鳶가 출력됐고, full_v4를 생성해 실제 CARD_SRC를 바꿨습니다.','bad'))+table(['항목','원인','수정'],[['메모 헤더','3B 슬롯에 4B 한글 불가','메·모를 1B 맵에 편입'],['겟피의 겟','코드표와 카드 글꼴 소스 불일치','추가 글리프 포함 카드로 갱신']])+note('남은 검수','오류 상태의 ‘鳶피’ 직접 화면은 이번 자료에 없으므로 재현하지 않았습니다. 최신 b26 이름·메모·전투의 사용자 확인은 남아 있습니다.'),
        'b26의 주 메뉴 ‘메모’ 캡처와 헤더·글꼴 보완 기록입니다. ‘겟피’ 오류는 직접 화면 없이 코드와 글꼴 소스의 불일치로 설명했습니다.')
    board(15,3,'현재 준비된 것과 아직 확인할 것을 나눴습니다','2026.10.10 기준 · 게시 글을 위한 자료 정리에서 게임 검수를 추가하지 않았습니다.',
        flow([('입력','지원하는 원본 디스크 + 시스템 카드'),('패치 적용 도구','입력 해시 → 디스크·카드 패치 → 결과 해시'),('실행 환경','별도 설정 + BizHawk 바로가기')])+table(['구분','현재 기록'],[['적용·부팅 기록','명령줄 적용 / 결과 해시 / 타이틀 / 멀티 BIN 새 게임 진입'],['최신 플레이 게이트','메모 헤더·본문 / 겟피 / 조사 / 전환·상태창 확인 필요'],['후속 작업','선택지 / 길이 초과 비주얼 자막 / 일부 컨테이너 / 크레딧'],['완료 안내','전체 한글화·완주 검수 완료 단계 아님']])+note('공개 자료','이 작업기 묶음에는 글과 시각자료만 넣었습니다. 원본 디스크·시스템 카드·패치·패처·세이브 파일을 포함하지 않습니다.'),
        '적용 도구가 확인한 범위와 남은 플레이·번역 범위를 정리했습니다. 게시용 정리 중 새 게임 실행이나 추가 검수는 하지 않았습니다.')

CSS='''*{box-sizing:border-box}body{margin:0;background:#f2f5f7;color:#182631;font-family:"Malgun Gothic",sans-serif;font-size:23px;line-height:1.6}header{padding:32px 42px;background:#183b4b;color:white;border-top:10px solid #49b3a1}h1{font-size:35px;line-height:1.4;margin:8px 0}header p{margin:6px 0 0;color:#dcebea}.eyebrow{font-size:18px;letter-spacing:1px}main{padding:28px 34px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;margin:14px 0}.grid>article:last-child:nth-child(odd){grid-column:1/-1;max-width:590px;width:100%;justify-self:center}.capture{background:white;padding:18px;border:1px solid #c9d6dc;border-radius:10px}.capture h3{font-size:25px;margin:6px 0 14px;line-height:1.5}.tag{font-size:18px;color:#426375}.screen{display:block;width:100%;height:380px;object-fit:contain;image-rendering:pixelated;background:#e9edf1}.capture p{font-size:21px;margin:12px 0 0;line-height:1.6}.crop{position:relative;overflow:hidden;background:#111;max-height:380px}.crop img{position:absolute;max-width:none;height:auto;image-rendering:pixelated}.flow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:20px 0}.flow>div{background:#e2efee;border-top:6px solid #39897d;padding:20px}.flow b{font-size:25px}.flow p{margin:10px 0 0;font-size:23px}aside{padding:21px 25px;margin:17px 0;background:white;border-left:7px solid #39897d;border-radius:4px}.grid aside{margin:0}aside.bad{border-color:#b77545;background:#fff5ec}aside b{font-size:25px}aside p{margin:8px 0 0}table{width:100%;border-collapse:collapse;background:white;margin:22px 0;font-size:23px}th{text-align:left;background:#dce9ed}td,th{padding:15px 20px;border:1px solid #bfd0d8;vertical-align:top}th{font-weight:700}.specimen{background:white;text-align:center;padding:35px 15px;margin:20px 0;font-size:46px;font-weight:700;letter-spacing:2px}.banks{display:flex;margin:20px 0;gap:12px}.banks div{flex:1;text-align:center;padding:25px 10px;color:white;background:#397688}.banks div:nth-child(2){background:#9a634b}.banks div:nth-child(3){background:#557244}.ratio{height:44px;background:#d3dee4;border-radius:8px;overflow:hidden;margin:25px 0 15px}.ratio div{height:100%;background:#298b79}.metrics{display:grid;grid-template-columns:1fr 2fr;gap:10px;padding:20px;background:white}.metrics b{font-size:34px;color:#267566}.metrics span{align-self:center}footer{padding:18px 34px;color:#4a616e;border-top:1px solid #c5d1d8;font-size:18px;background:#e8eef2}p,td,th{overflow-wrap:anywhere}'''

def main():
    (PUB/'images').mkdir(parents=True,exist_ok=True)
    (QA/'boards').mkdir(parents=True,exist_ok=True)
    define()
    assert len(BOARDS)==36,len(BOARDS)
    renderer=Renderer(QA)
    try:
        for b in BOARDS:
            n=b['number']
            types=sorted(set(s['kind'] for s in b['sources']))
            badge='기록 기반 설명도' if not types else '기존 캡처·자료 비교 / 종류는 각 패널에 표시'
            page=f'<!doctype html><html lang="ko"><meta charset="utf-8"><style>{CSS}</style><header><div class="eyebrow">천사의 시 II 한국어화 작업기 · {b["section"]}절 · 자료 {n:02} · {badge}</div><h1>{E(b["title"])}</h1><p>{E(b["subtitle"])}</p></header><main>{b["body"]}</main><footer>당시 빌드·실험 기록을 정리한 자료입니다. 최신 b26 전체 플레이 검수의 증거는 아닙니다.</footer></html>'
            target=QA/'boards'/f'{n:02}.html';target.write_text(page,encoding='utf-8')
            renderer.load(target,1280,200)
            clipped=renderer.evaluate('Array.from(document.querySelectorAll("h1,h3,p,td,th,aside,.tag")).filter(e=>e.scrollWidth>e.clientWidth+1).length')
            assert clipped==0,(n,clipped)
            renderer.shot(PUB/'images'/f'{n:02}.png',True)
            b.update(image=f'images/{n:02}.png',sha256=base.sha(PUB/'images'/f'{n:02}.png'),
                renderer='headless_edge_html_layout',b26_full_qa_evidence=False,
                source_records=[dict(path=p,sha256=base.sha(ROOT/p)) for p in b['records']])
            b.pop('body');b.pop('records')
        hashes=[base.sha(ROOT/'translation/bios_retest_2026-08-22'/f'{t}_f800.png') for t in ['R0_original','R1_two_glyph','R2_18glyph','R4_diag896']]
        assert len(set(hashes))==1,hashes
    finally:renderer.close()
    (QA/'visual_manifest.json').write_text(json.dumps(BOARDS,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    stats=dict(boards=len(BOARDS),source_occurrences=sum(len(b['sources']) for b in BOARDS),
        unique_sources=len(set(s['source'] for b in BOARDS for s in b['sources'])),
        unique_emulator_captures=len(set(s['source'] for b in BOARDS for s in b['sources'] if s['kind']=='actual_emulator_capture')),
        explanatory_boards=sum(not b['sources'] for b in BOARDS),boot_png_identity='PASS')
    (QA/'visual_stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(stats))

if __name__=='__main__':main()
