# 천사의 시 II ~타천사의 선택~ — PC Engine Super CD-ROM²

PC Engine Super CD-ROM² **천사의 시 II ~타천사의 선택~** 한글 번역 패치 프로젝트입니다. 마을과 필드를 탐험하며 이야기를 진행하는 판타지 RPG 시리즈 두 번째 작품의 PC Engine CD판입니다.

> **정식 배포 v1.0.1** (2026-10-22: 펨브로크 카지노 진입 검은 화면 수정. v1.0 결과물은 패처로 그 자리에서 올릴 수 있습니다)

개발용: [v1.0(b64) 소스 재빌드 안내](docs/REBUILD_B64_2026-10-16.md) — v1.0.1(b65)은 같은 명령에 `--build b65 --no-expect`, 고정 출력은 [config/rebuild_b65.json](config/rebuild_b65.json). 수정 경위는 [2026-10-22 인계](docs/HANDOFF_2026-10-22.md).

2026-10-16 로컬 게임 폴더는 사용자 요청으로 삭제했다. [정리·복원 인계](docs/PCE_CLEANUP_2026-10-16.md)에 보존 자료와 복원 방법을 기록했다.

<!-- game-preview:start -->
<p align="center">
  <img src="img/preview.png" alt="천사의 시 II ~타천사의 선택~ — 한글 타이틀 · v1.0" width="512">
</p>

**한글 타이틀 · v1.0** — release_Tenshi2_KR_v1.0_20261014 pce_fast 캡처
<!-- game-preview:end -->

## 다운로드 및 적용 방법

1. 아래 체크섬 또는 상세 안내와 일치하는 원본을 준비합니다.
2. [최종 배포 패치 다운로드](https://github.com/akuma815/pce-tenshi-no-uta-2-kr-patch/releases/tag/v1.0.1)에서 ZIP을 받아 모두 압축 해제합니다.
3. `Tenshi2KR_Patcher.exe`에서 원본 CUE와 원본 시스템 카드 PCE를 선택합니다.
4. 필요하면 BizHawk 실행 파일을 지정하고, 패치 및 바로가기를 생성합니다.
5. 에뮬레이터에 생성된 `_KR.cue`와 `SystemCard3_KR.pce`를 함께 지정합니다.

## 주의사항

- 원본 디스크와 일본판 Super System Card 3.0을 직접 준비해야 합니다.
- 단일 BIN과 Redump 멀티 BIN은 각 전용 패치를 사용합니다.
- 에뮬레이터에는 패치된 디스크와 패치된 시스템 카드를 함께 지정합니다.
- 이전 버전의 세이브스테이트는 사용하지 마세요(v1.0 것도 포함). 지원 에뮬레이터와 세이브 이전은 동봉 안내를 따르세요.
- 원본 게임·BIOS 및 패치가 적용된 게임 이미지는 포함하지 않습니다.

## 체크섬

| 구분 | SHA-256 |
| --- | --- |
| 원본 단일 BIN | `d16d29eb80b1b74a2ec929924349256b50b8f9f5c9a3fa37b6fcc08b059b22c5` |
| 원본 System Card 3.0 (J), 헤더 없음 | `e11527b3b96ce112a037138988ca72fd117a6b0779c2480d9e03eaebece3d9ce` |
| 원본 Redump Track 02 | `1e69de05aaf1171e4a3347a146d5967c796e312ca0c53cebb267c5ffe0684034` |
| 패치 파일 `SystemCard3_KR.xdelta` | `89addf9867ba86edaea2652d45e0b8e3479f52ea3adfb11ddde0b51249edd992` |
| 패치 파일 `SystemCard3_KR_from_v0.3.xdelta` | `e40c7a3c36d33c9ddc17730c9156fd98bc49bfde7e97c56e1bb2bd731807f05d` |
| 패치 파일 `Tenshi_no_Uta_II_KR_disc.xdelta` | `924cd6f4a50d8ad19512020ddb2b9f440ee17d5c6a51a1fc115a732c61b4217f` |
| 패치 파일 `Tenshi_no_Uta_II_KR_disc_from_v1.0.xdelta` | `ca171ff31b651b6497dccfc4144c8709c2d1cc571d4001799e366487ef00ca2c` |
| 패치 파일 `Tenshi_no_Uta_II_KR_track02_redump.xdelta` | `139f9302bc26e78778194564a46d7a41d6f1bdca92cb5927245b3abc8bcf8f55` |
| 패치 파일 `Tenshi_no_Uta_II_KR_track02_redump_from_v1.0.xdelta` | `d88910764faf9ecbd0821dd6c7a93f0ff9d310dd63f891cc65dd262789a48da6` |
| 패처 `Tenshi2KR_Patcher.exe` | `097888e9008d0436f7e5157cce5105f1e92b90fca7ff9641c9c643c3cfb6dad0` |
| 배포 압축 파일 `Tenshi2_KR_v1.0.1_20261022.zip` | `db44a24383e2881e8d7b164c3cc4a0fa2e5c862f0ca1516ae1d8f9bf2effb848` |
| 결과 단일 BIN (v1.0.1) | `52f2002829b83edcb32b5932513f3f857c15cc02771be54d4e750919760b9c3f` |
| 결과 Redump Track 02 (v1.0.1) | `61c99c4f8d216c25311af9f8c324d4756e4703faf6878dafab4212876e951e3c` |
| 결과 시스템 카드 (v1.0 과 동일) | `5632f388ae2f0fce9e435134ee89b825172e9b2a08bae5f7b5856a9807f21274` |

지원 원본의 세트·리비전 및 해시는 [상세 패치 안내](docs/PATCH_GUIDE.txt)를 확인하세요.

## 소스 및 작업 기록

[공개 소스 구성과 빌드 전제](docs/SOURCE_GUIDE.md) · [상세 패치 안내](docs/PATCH_GUIDE.txt)
