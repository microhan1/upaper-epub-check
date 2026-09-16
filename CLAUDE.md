# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## What This Is

**유페이퍼 EPUB 검수기** — 유페이퍼(upaper.net) 업로드 전에 EPUB 이 유페이퍼 검수 기준에 맞는지 검사하는 Python CLI(+EXE). 기준의 단일 출처는 `upaper_check/default_rules.json` 과 각 `checks/*.py` 의 규칙 설명 문자열이며, 근거 문서는 유페이퍼 검수 기준 PDF(2015.01.12)와 도움말 페이지다. README 의 표가 사람용 요약.

- 스택: Python 3.10+ · lxml · Pillow · (빌드) PyInstaller. 외부 서비스 없음, 네트워크 없음.
- 실행: `python upaper_check.py 책.epub [--html] [--json] [--publisher NAME] [--rules JSON] [--epubcheck JAR]`. 인자 없으면 끌어다 놓기 창(`gui.py`, tkinterdnd2). `UPAPER_SELFTEST=1` 로 실행하면 창을 만들었다 닫고 `dnd:available` 여부만 출력한다 — EXE 빌드 후 반드시 이걸로 드롭 모듈이 실렸는지 확인. EXE 는 창 모드(console=False)라 stdout 이 없으므로 `UPAPER_SELFTEST=결과.txt` 처럼 파일 경로를 주면 거기에 쓴다.
- 창 모드 EXE 에서 `print` 는 조용히 버려진다. 사용자에게 보여야 하는 것은 `cli._windowed()` 분기에서 보고서 열기·메시지 상자로 처리한다.
- 테스트: `python -m unittest discover -s tests -v` — `tests/make_fixtures.py` 가 good/bad EPUB 을 생성해 규칙별로 검증한다. **규칙을 추가·변경하면 bad.epub 에 위반 사례를 넣고 테스트를 함께 고친다.**
- 실전 기준 파일: 유페이퍼 승인(2026-09-05)된 `D:\my\PDF To Epub\dist\스캔북 컨버터\doc\하늘은 왜 파래요 - microhan.epub` 은 **오류 0 으로 통과해야 한다**(회귀 기준). 규칙을 바꾸면 이 파일로도 돌려 본다.

## Non-Obvious Rules

- **등급 체계**(`findings.Level`): 오류 = 유페이퍼 검수 기준에 "승인 거부"로 명시되었거나 적합성 검사(epubcheck)를 못 넘는 것 · 경고 = 권장 규격·제휴사 뷰어 문제 · 수동확인 = 표지 문구처럼 프로그램이 판단 못 하는 것 · 정보 = 참고. 문서에 근거 없는 항목을 오류로 올리지 않는다.
- **출판사명 기본값은 '유페이퍼'** (개인 출판자 규정). 출판사 등록자는 `--publisher`, 검사 생략은 `--any-publisher`. 판권 페이지와 OPF 두 곳 모두 검사한다.
- **판권 페이지 탐지**(`checks/colophon.py`): 6000자 이하 문서 중 구조 신호(발행일 표기·날짜 값·펴낸곳·저자·정가·ISBN·연락처 정규식) + `colophon.page_keywords` 점수가 3 이상이고 **날짜·ISBN·정가·연락처 중 하나(hard datum)** 가 있는 문서가 후보, 최고점이 판권. 제목/파일명/첫 40자에 "판권"이 있으면 가산. **중복 판정은 '확실한 판권'끼리만** — "판권" 제목이거나 발행일 표기+날짜+펴낸곳+(ISBN·연락처·정가) 를 모두 갖춘 페이지. 이렇게 조인 이유: 상용 EPUB 167권 테스트에서 저자 소개("2000년 창해출판사"), 본문("1929년 10월 … 채권 발행"), 김영사식 저작권 고지 페이지가 판권 중복으로 오탐됐다(v0.2.2). 텍스트 판권이 없고 끝부분에 이미지만 있는 페이지가 있으면 오류 대신 수동확인(COLOPHON-IMAGE).
- **표지 중복은 같은 표지 이미지를 두 문서가 쓸 때만** 오류. "이미지 한 장짜리 페이지가 더 있다"는 휴리스틱은 속표지·출판사 로고 페이지를 107권에서 오탐해 제거했다. 첫 장이 이미지 한 장짜리인데 OPF 표지 이미지와 다른 파일이면 오류가 아니라 정보.
- **날짜 정규식**(`DATE_VALUE`)은 월 1~12·일 1~31 로 제한 — 출판등록번호 "제2006-000017호"가 날짜로 잡히던 문제.
- 상용 EPUB 대량 테스트 방법: `C:\Users\micro\Desktop\Books\*.epub`(167권)을 돌려 코드별 파일 수를 보고, 갑자기 늘어난 코드는 오탐을 의심한다. 상용본은 출판사명·정가·검정 글자색 때문에 대부분 "수정 필요"가 정상이다.
- **표지 탐지 순서**: `<meta name="cover">` → `properties="cover-image"` → guide type=cover → 첫 spine 문서의 단일 이미지 → id/href 에 cover. 첫 spine 문서가 표지가 아니면 오류.
- **비권장 태그(ul/li/table)는 파일별이 아니라 태그별로 한 건**으로 묶어 보고한다(승인된 책도 table 42개를 쓰고 통과했으므로 경고 등급 유지).
- 검정 글자색 정규식은 `background-color:#000` 을 잡지 않도록 `(?<![-\w])color` 를 쓴다. 테스트에 회귀 케이스 있음.
- EXE 빌드는 `upaper_check.spec`(onefile, console) — `default_rules.json` 을 `upaper_check/` 밑에 datas 로 싣는다. 경로를 바꾸면 `context.DEFAULT_RULES_PATH` 도 같이.

## 공통 원칙 (책갈피 프로젝트와 동일)

- Early Return / Guard Clause, `else` 최소화 · 단일 책임 · 함수 30줄 이내(50줄 초과 시 분리) · 매직 넘버·스트링은 상수나 `default_rules.json` 으로.
- 사용자 대면 문자열(메시지·조치·보고서)은 한국어, 코드 식별자는 영어. 메시지에는 "무엇이 문제"와 "어떻게 고치나"(hint)를 함께.
- 요청 범위 외 기능·리팩토링 임의 추가 금지. 변경 시 `docs/change_history.md` 맨 위에 항목 추가(형식: `## vX.Y (YYYY-MM-DD) — 제목` → `### 추가 / 변경 / 제거 / 수정`).
- 테스트는 실제 EPUB 픽스처로 규칙을 검증한다. 통과만을 위한 하드코딩 금지.
