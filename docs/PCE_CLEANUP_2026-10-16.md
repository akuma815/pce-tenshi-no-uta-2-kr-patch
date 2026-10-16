# 2026-10-16 PCE CD판 작업 폴더 삭제 완료

사용자가 원본은 나중에 다시 준비하겠다고 명시하고, 삭제 가능하면 폴더 전체를 삭제하도록 요청했다. 이전 인계의 원본 보존 조건은 이 요청으로 변경됐다. **2026-10-16 19:52:32 KST에 `Games/Tenshi no Uta II - Datenshi no Sentaku (Japan)` 전체를 삭제했다.** 그 안의 `Original`과 루트 원본 BIN/CUE도 삭제 대상에 포함됐다.

## 삭제 전 보존·검증

- 재현용 Git 소스: `742fd1aad9e85c6784827cd335d1a3f4aff2550a`의 원격 일치와 빌드 입력 1,146개 크기·SHA-256을 재확인했다. 이 입력의 원격 새 복제본으로 공식 v1.0(b64) BIN·CUE·시스템 카드·Redump Track 02가 정확히 재현된 근거는 [재빌드 검증](rebuild_verification_2026-10-16.json)에 있다.
- Git에 없는 편집 자료·번역 원장 이력·QA·작업기·기존 배포 패키지 등을 비공개 백업으로 보존했다. 원본 디스크 전체·추출 캐시·Switch 원본 자산·외부 BizHawk 전체 소스·패키지 캐시는 제외했다. 게임 폴더 전체 백업은 아니다.
- 기존 보존 대상 b10을 포함한 과거 빌드와 시스템 카드 등 30개는 원본 단일 BIN 또는 원본 BIOS를 소스로 요구하는 xdelta로 보존했다. 각 차분을 적용해 원래 파일의 크기·SHA-256 일치를 확인했다.
- 백업은 프로젝트 기록 4,581개와 차분 30개, 매니페스트를 포함한다. ZIP CRC 및 4,611개 항목 전체 크기·SHA-256을 검증했다. 별도 디렉터리에 편집 기록과 과거 빌드 전체를 실제 복원한 테스트도 통과했다. 테스트용 복원본은 삭제하고 백업과 근거를 남겼다.

비공개 보관 위치는 작업 루트 아래 `work/cleanup_pce_tenshi2_20261016/`이다.

| 항목 | 값 |
| --- | --- |
| 파일 | `Tenshi2_PCE_authoring_records_20261016.zip` |
| 크기 | 457,757,259바이트 |
| SHA-256 | `41db4c24da4f39ed68c5e5da02de5d6dfef2c356d60e7c45a6f9f42eb0f05d1e` |

백업에는 사용자 작업 자료와 비공개 QA 자료가 있으므로 공개 Git에 올리지 않는다. 복원 도구는 `recovery/restore_authoring_backup.py`에 공개했다.

## 삭제 범위와 결과

실제 게임 트리의 파일은 13,541개·6,751,560,687바이트다. 이 수치는 재분석 지점의 외부 파일을 따라가지 않은 목록이다. 앞선 22,066개 목록은 외부 `node_modules` 내용이 포함된 것이므로 삭제 파일 수로 사용하지 않는다.

`archive/tools_task0_7/task6_workbook_runtime/node_modules`는 게임 폴더 밖 Codex 런타임 캐시로 연결되는 junction이었다. 정확한 링크 경로를 확인한 뒤 비재귀 디렉터리 삭제로 링크만 제거했다. 외부 대상은 유지됐고 최상위 항목 목록·속성·파일 크기가 삭제 전후 동일함을 확인했다. 이어 남은 재분석 지점이 0개임을 검사한 후 정확한 게임 경로만 삭제했다.

삭제 후 대상 폴더 부재와 다른 게임 디렉터리 목록의 동일성을 확인했다. H: 원본·모드·세이브를 수정하지 않았다. 세부 근거는 `cleanup_completed_2026-10-16.json`, 로컬의 `inventory_before_backup.json`, `authoring_manifest.json`, `backup_verification.json`, `deletion_preflight.json`, `deletion_result.json`이다.

이번 삭제는 새로운 게임 실행·장면 검수·완주 검증이 아니다. 공식 v1.0 릴리즈와 배포 ZIP은 변경하지 않았다.

## 다시 작업할 때

최신 v1.0 코어는 Git과 [재빌드 안내](REBUILD_B64_2026-10-16.md), 지원 원본·외부 도구로 재현한다. 이전 로컬 경로를 그대로 사용하는 런처는 게임 폴더가 삭제됐으므로 바로 실행되지 않는다.

백업 검사만 하려면 다음을 실행한다. 실제 ZIP 경로를 지정한다.

```powershell
python -X utf8 recovery/restore_authoring_backup.py `
  --archive 'D:\Backup\Tenshi2_PCE_authoring_records_20261016.zip' `
  --sha256 41db4c24da4f39ed68c5e5da02de5d6dfef2c356d60e7c45a6f9f42eb0f05d1e
```

편집 기록만 복원하려면 `--output 'D:\Restore\Tenshi2_PCE'`를 추가한다. 출력 디렉터리는 새 경로여야 한다. 과거 빌드도 복원하려면 다음 인수를 추가한다.

```powershell
--restore-history `
--source-bin 'D:\Owned\Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin' `
--source-bios 'D:\Owned\SystemCard3_original_noheader.pce' `
--xdelta 'D:\Tools\xdelta3.exe'
```

단일 BIN과 262,144바이트 무헤더 BIOS의 크기·SHA-256을 검사한다. 원본 프로필은 `config/rebuild_b64.json`과 백업 매니페스트에 있다. Redump 세트와 원본 단일 BIN의 레이아웃은 다르므로 서로 대체한다고 가정하지 않는다. 원본 게임과 외부 도구 전체를 복구하는 백업은 아니다.

**정확한 다음 행동 하나:** 재작업할 때 필요한 원본의 크기·SHA-256을 프로필과 대조하고 Git의 격리 재빌드 명령을 실행한다.
