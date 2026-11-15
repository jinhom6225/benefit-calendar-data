# ops/evidence — 운영 근거 기록 (앱은 읽지 않음)

이 폴더는 `schedule.json`의 날짜·상태·문구가 **어디서 왔는지** 사람이 다시 확인할 수 있게 남기는 곳이다. 앱은 `schedule.json`만 읽고, Pages에도 `schedule.json`만 올라간다(`validate.yml` deploy 단계).

## 무엇을 어디에

| 파일 | 내용 |
|---|---|
| `sources_YYYYMMDD.md` | 그날 확인한 공식 출처: URL · 페이지 제목 · 게시일 · 원문 문장 · 접속일. `schedule.json`의 `sources`·`sourceUrl`·`lastChecked`의 근거 |
| `suspensions.md` | 회차 중단 근거(지자체 공지 URL · 접속일 · 원문 요지). `partialSuspended` 판정 기록 |
| `raw/` | 브라우저 캡처 원문(로컬 전용, `.gitignore`). 공개 저장소라 커밋하지 않는다 |

## 상태 판정 규칙 (research.md §5)

- 공식 안내(지침·기관 공지)에 중단·마감이 있으면 그대로 따른다.
- 공식 안내가 없으면 **서로 다른 시군구 공지 3곳 이상**에서 중단을 확인했을 때 `partialSuspended`.
- 공식 마감 공지가 있거나 마감일이 지나면 `closed`(앱도 마감일 다음 날부터 마감으로 보인다).
- 시군구 공지 링크는 앱 데이터(`sources`·`sourceUrl`)에 넣지 않는다 — 허용 호스트 목록이 커지기 때문. 여기에만 적는다.

## 기록 순서

1. 공식 페이지를 연다(로그인·제출 없음). 원문 문장을 그대로 옮긴다.
2. `sources_YYYYMMDD.md`(또는 `suspensions.md`)에 한 줄씩 추가한다.
3. `schedule.json`의 해당 회차 `status`·날짜·`lastChecked`를 고친다.
4. `python3 -I tools/validate.py schedule.json` → `python3 -I -m unittest discover -s tests` → 커밋.
