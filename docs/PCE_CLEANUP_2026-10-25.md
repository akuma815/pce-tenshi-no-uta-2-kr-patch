# 2026-10-25 로컬 정리 (v1.0.1 배포 뒤)

사용자 요청으로 로컬 작업 자료를 삭제했다. 삭제 전에 **원본 + GitHub 만으로 복원되는지** 확인했다.

## 복원 검증 (삭제 직전, 새 클론)

- `git clone` 새 사본(커밋 a516ae5) + 원본 단일 BIN(SHA-256 d16d29eb…)·CUE(`release/app/cue_template.cue` 의 {BIN} 치환, LF)·원본 System Card 3.0(e11527b3…)·Redump Track 02(1e69de05…) → `python -X utf8 tools/rebuild_b64.py --build b65 --no-expect …` → 디스크 52f20028…, 카드 5632f388…, Track 02 61c99c4f… = 공개 v1.0.1 과 일치.
- GitHub Release v1.0.1 ZIP 의 xdelta 3종을 같은 원본에 적용한 결과도 위와 일치.
- 외부 도구: Python 3.11+(Pillow), .NET SDK 8, xdelta3, (패처 exe 재빌드 시) PyInstaller·tkinterdnd2.

## 삭제한 것

- `Games/pce-tenshi-no-uta-2-kr-patch` 전체(레포 클론 + `Original/`·`bios/`·`build/`·`save/`·`release/dist/`), 검증용 `Games/_verify_restore`.
- 제보 재현 환경 `Tools/RetroArch/`(RetroArch 1.21 + Beetle PCE 코어, work/ 스테이트·스크린샷)과 내려받기 `Tools/retroarch_dl/`.
- 사용자가 원본은 다시 구하기로 했다. 단일 BIN 원본이 전 트랙 2352B .iso 형태라면 데이터 트랙(섹터 3365~12692)만 2048B 로 변환하면 지원 단일 BIN 과 일치한다(2026-10-22 실측).

## 남긴 것 (삭제 범위 밖)

- `Games/_backup_pce_tenshi2_qa_20261025.zip`(약 1.2MB, 비공개): 제보자 세이브(.srm/.state8), 카지노 도박사 앞 스테이트(`casino_front_kr.state`, Beetle PCE 코어·b65 디스크에서 로드 가능) 등 QA 스테이트, 비교 스크린샷, 배포 파일 해시 JSON, RetroArch cfg 2종. 재현 환경을 다시 만들 때 `docs/HANDOFF_2026-10-22.md` 의 환경 절과 함께 쓴다.
- 공개 사이트 레포 `web/akuma815.github.io` 는 다른 게임도 쓰므로 그대로 둔다.

## 다시 작업할 때

1. 레포를 클론하고 지원 원본 3종을 준비한다(해시는 README·`config/rebuild_b65.json`).
2. `tools/rebuild_b64.py --build b65 --no-expect` 로 재현하고 위 해시를 확인한다.
3. 제보 재현이 필요하면 RetroArch + `mednafen_pce_libretro.dll` 을 설치하고 백업 ZIP 의 스테이트·cfg 를 쓴다(cfg 안의 경로는 새 위치로 고친다).
