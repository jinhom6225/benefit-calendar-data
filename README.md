# benefit-calendar-data

「놓치지마 신청달력」 앱(`com.joe.benefitcalendar`, 앱 저장소 `benefit_calendar`)이 읽는 **사람이 관리하는 정적 일정 데이터**. 수집기·API 키·서버는 없다(앱 research.md §6).

- 앱이 읽는 주소: **https://jinhom6225.github.io/benefit-calendar-data/schedule.json** (GitHub Pages, ETag)
- 앱 번들 사본: 앱 `assets/data/schedule.json`(빌드 때 이 저장소에서 복사)
- 이 파일 하나만 Pages에 올라간다. `ops/evidence/`(근거 기록)·`tools/`·`tests/`는 올라가지 않는다.

## 흐름

```
schedule.json 편집 → python3 -I tools/validate.py schedule.json
                   → python3 -I -m unittest discover -s tests
                   → git add <경로> && git commit   (push는 저장소 소유자)
push → Actions "validate" → 테스트·검증 통과 시에만 deploy 단계가 Pages에 schedule.json을 올림
       (검증 실패 → deploy 안 함 → Pages는 마지막 정상 파일 유지 → 앱은 캐시 유지)
```

일정·상태를 바꿀 때는 근거를 `ops/evidence/`에 먼저 적는다(`ops/evidence/README.md`).

## schedule.json (schemaVersion 1)

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-15T01:00:00Z",
  "programs": [ { "id": "hope2", "name": "…", "summary": {…}, "channels": […], "eligibility": {…}, "sources": [{"label": "…", "url": "https://…"}], "lastChecked": "2026-11-15" } ],
  "items":    [ { "id": "hope2-2027-1", "programId": "hope2", "label": "2027년 1차", "status": "expected", "start": null, "end": null, "expectedMonth": "2027-02", "referenceWindow": {"start": "2026-02-02", "end": "2026-02-24"}, "sourceUrl": "https://…", "lastChecked": "2026-11-15", "note": "…" } ]
}
```

### programs[] (제도 7개)

| 필드 | 규칙 |
|---|---|
| `id` | `[A-Za-z0-9_-]{1,40}`, 중복 없음. 지금: `hope1` `hope2` `eduBenefit` `eitc` `youthSaving` `energyVoucher` `cultureCard` |
| `name` | 제도명(30자 이하) |
| `summary.who` / `amount` / `where` / `caution` | 짧은 문장(각 120·120·80·160자 이하). 금액은 2026년 기준이라고 문장 안에 적는다 |
| `summary.bring` | 준비물 목록(빈 목록 가능 — 공식 출처로 확인 못 한 것은 쓰지 않는다) |
| `channels` | `visit`(읍면동 방문) · `online`(복지로 등) · `hometax`(홈택스·손택스·ARS) · `site`(제도 누리집) — 1개 이상 |
| `eligibility` | 아래 "자격 규칙" |
| `sources` | `{label, url}` 1개 이상, https + 허용 호스트만 |
| `lastChecked` | 제도 설명을 마지막으로 확인한 날 `YYYY-MM-DD` |

### items[] (회차)

| 필드 | 규칙 |
|---|---|
| `id` | `<programId>-<연도>-<회차>`, 중복 없음 |
| `programId` | `programs[].id` 중 하나 |
| `label` | 회차 이름(40자 이하) |
| `status` | `confirmed`(확정) · `expected`(예정, 월만) · `partialSuspended`(일부 지역 중단) · `suspended`(전국 중단) · `closed`(마감) |
| `start` / `end` | 서울 날짜 `YYYY-MM-DD`. `expected` 말고는 둘 다 필수, `start ≤ end`. `expected`면 둘 다 `null` |
| `endTime` | 선택 `HH:MM`(서울) — 마감 시각이 따로 있을 때(문화누리 18:00). 날짜 있는 상태에서만 |
| `expectedMonth` | `expected`면 필수 `YYYY-MM`, 나머지는 `null` |
| `referenceWindow` | 선택 `{start, end}` — 작년 같은 회차 날짜. 앱은 "2026년에는 …였어요 (올해 일정 미정)"을 회색으로 보인다(R3 a) |
| `sourceUrl` | 회차 날짜의 근거, https + 허용 호스트 |
| `lastChecked` | 이 회차를 마지막으로 확인한 날. 앱의 **14일 규칙**(열린 회차가 14일 넘게 확인 안 됐으면 "열렸어요" 알림을 보내지 않음)과 주간 점검(10일)이 이 값을 쓴다 |
| `note` | 선택 짧은 문장(120자 이하) |

- 앱은 데이터가 `confirmed`여도 **`end` 다음 날부터 마감**으로 보인다(서울 날짜). 그래서 지난 회차를 서둘러 `closed`로 바꾸지 않아도 되지만, 운영 때 바꿔 둔다.
- 금지 문구(검증 스크립트가 모든 글에서 거름): `받을 수 있습니다` · `가입하기` · `계좌 개설` · `공식 앱`.

### 허용 링크 호스트 (앱 `AppProfile.dataLinkHosts`와 같아야 함)

`hope.welfareinfo.or.kr` · `www.mohw.go.kr` · `www.bokjiro.go.kr` · `www.hometax.go.kr` · `www.nts.go.kr` · `www.energyv.or.kr` · `www.mnuri.kr` · `www.korea.kr` · `www.moe.go.kr` · `oneclick.neis.go.kr`

(research §6-4의 `oneclick.moe.go.kr`는 열리지 않는다 — 교육비 원클릭은 `oneclick.neis.go.kr`, 2026-11-15 확인.) 시군구 공지 링크는 넣지 않는다 → `ops/evidence/`에만.

## 자격 규칙 (`programs[].eligibility`) — 앱이 평가하는 방법

```json
{
  "anyBenefit": ["housing", "education", "nearPoor"],
  "needsEarner": true,
  "anyMember": [],
  "softMiss": [],
  "maxResult": "likely",
  "alwaysShowNote": false,
  "checkNote": "…"
}
```

사용자 답(3문항, research §4):
- `benefits`: 받고 있는 지원 — `livelihood`(생계) · `medical`(의료) · `housing`(주거) · `education`(교육) · `nearPoor`(차상위). "없음/모름"을 고르거나 건너뛰면 **답 없음**.
- `earner`: 일해서 버는 가구원이 있나 — 예/아니오.
- `members`: 가구원 — `youth`(청년) · `student`(초중고 학생) · `vulnerable`(65세 이상·장애·영유아·임산부).

조건 세 개:
| 조건 | 데이터 | 충족 |
|---|---|---|
| `benefit` | `anyBenefit` (빈 목록 = 조건 없음) | 답의 `benefits`와 하나라도 겹침. `anyRecipient`는 `livelihood`·`medical`·`housing`·`education` 네 개로 펼친다 |
| `earner` | `needsEarner` (`false` = 조건 없음) | `earner`가 예 |
| `member` | `anyMember` (빈 목록 = 조건 없음) | 답의 `members`와 하나라도 겹침 |

판정(순서대로, 결과는 `likely` 해당될 수 있어요 / `check` 조건을 확인하세요 / `unlikely` 숨김):
1. `benefits` 답 없음(건너뛰기·없음/모름) → **모든 제도 `check`** (데이터와 상관없는 앱 규칙).
   - 2·3번 문항만 건너뛰면(답 없음) 그 문항 때문에 못 맞춘 조건은 `softMiss`처럼 본다 — `check`까지만 내리고 `unlikely`로 숨기지 않는다(앱 규칙 2026-11-15).
2. 못 맞춘 조건 중 하나라도 `softMiss`에 **없으면** → `unlikely`.
3. 못 맞춘 조건이 있고 모두 `softMiss`에 있으면 → `check`.
4. 다 맞으면 → `likely`. 단 `maxResult: "check"`이면 `check`로 낮춘다(기본 `"likely"`).
5. 화면 문구: 결과가 `check`이면 `checkNote`를 함께 보인다. `alwaysShowNote: true`면 `likely`일 때도 보인다(근로·자녀장려금 — 소득·재산 상한 문장).

`softMiss` 값은 `benefit` · `earner` · `member` 중에서, 그 조건이 실제로 있는 규칙에만 쓴다(검증 스크립트가 막음).

참조 구현: `tests/eligibility_reference.py`, research §4 표 고정: `tests/test_eligibility.py`(31줄 + 건너뛰기 7개 + R1 김씨 장면).

## 워크플로

| 파일 | 언제 | 하는 일 |
|---|---|---|
| `.github/workflows/validate.yml` | push · PR · 수동 | 단위 테스트 + `tools/validate.py`. **main push에서만, 검증 통과 뒤** `deploy` 잡이 Pages(Actions 배포)에 `schedule.json`만 올림 |
| `.github/workflows/stale_check.yml` | 매주 월 09:17 KST · 수동 | `tools/stale_check.py`: 열린 회차·30일 안에 열릴 회차(`expected`는 그 달 1일이 30일 안이고 그 달이 안 끝난 것) 중 `lastChecked`가 10일 넘은 것 → Telegram `[신청달력] 확인 필요 N건` + id 목록. 0건이면 보내지 않음. 실패하면 실패 알림 |
| `.github/workflows/keepalive.yml` | 매주 월 09:47 KST · 수동 | 예약 워크플로가 60일 비활동으로 멈추지 않게 `stale_check.yml`·`keepalive.yml`을 다시 켬(mountain-stamp-data 방식) |

## 저장소 소유자가 할 일 (업로드 직전 묶음 B — 아직 안 함)

1. GitHub에 **Public** 저장소 `jinhom6225/benefit-calendar-data` 만들기(README·.gitignore 추가 없이 빈 저장소).
2. push 전에 **Settings → Pages → Build and deployment → Source: "GitHub Actions"** 선택(브랜치 배포 아님 — 브랜치 배포를 고르면 검증 실패한 파일도 그대로 올라감).
3. **Settings → Secrets and variables → Actions → New repository secret** 2개: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`(다른 데이터 저장소와 같은 값).
4. 로컬 저장소에서 remote 추가 + push:
   `git remote add origin git@github.com:jinhom6225/benefit-calendar-data.git`
   `git push -u origin main`
   (2번보다 먼저 push하면 첫 validate 실행의 deploy 잡이 "Pages 꺼짐"으로 실패한다 — 2번을 한 뒤 5번으로 다시 돌리면 된다.)
5. push가 validate를 자동으로 돌린다(안 돌았으면 **Actions → validate → Run workflow**, main). 끝나면 몇 분 뒤 https://jinhom6225.github.io/benefit-calendar-data/schedule.json 이 200.
6. (선택) Actions → stale-check → Run workflow로 알림 확인(지금 데이터는 0건이라 "nothing to send").

Settings → Actions → General의 Workflow permissions는 기본값(읽기)으로 둔다 — 각 잡이 필요한 권한만 `permissions:`로 받는다.

## 로컬 확인

```bash
python3 -I tools/validate.py schedule.json
python3 -I -m unittest discover -s tests
python3 -I tools/stale_check.py schedule.json --today 2027-01-20
```

파이썬 표준 라이브러리만 쓴다.
