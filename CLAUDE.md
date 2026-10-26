# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## What This Is

**유페이퍼 EPUB 검수기** — 유페이퍼(upaper.net) 업로드 전에 EPUB 이 유페이퍼 검수 기준에 맞는지 검사하는 Python CLI(+EXE). 기준의 단일 출처는 `upaper_check/default_rules.json` 과 각 `checks/*.py` 의 규칙 설명 문자열이며, 근거 문서는 유페이퍼 검수 기준 PDF(2015.01.12)와 도움말 페이지다. README 의 표가 사람용 요약.

- 스택: Python 3.10+ · lxml · Pillow · (빌드) PyInstaller. EPUB 검사는 네트워크를 쓰지 않는다. **예외는 끌어다 놓기 창의 「새 버전 확인」 하나뿐**(v0.2.6, `update_check.py`) — 하루 한 번 `GET https://chaekgalpi.co.kr/api/tools/upaperepub/latest?v=버전&os=win` 에 도구 이름·버전·OS 만 보낸다. 명령줄·EXE 아이콘 위 끌어놓기 경로에는 넣지 않는다. 자동 다운로드·모달·식별자 전송 금지. 동작 규칙은 책갈피 툴 공통(참고 구현 `D:\my\music-tag-filler\update_check.py`)이라 바꾸지 않는다. 창의 「의견 보내기」(v0.2.8, `update_check.feedback_url`)는 툴 페이지 `#feedback` 을 브라우저로 열기만 하고 프로그램은 요청을 보내지 않는다.
- 실행: `python upaper_check.py 책.epub [--html] [--json] [--publisher NAME] [--rules JSON] [--epubcheck JAR]`. 인자 없으면 끌어다 놓기 창(`gui.py`, tkinterdnd2). `UPAPER_SELFTEST=1` 로 실행하면 창을 만들었다 닫고 `dnd:available` 여부만 출력한다 — EXE 빌드 후 반드시 이걸로 드롭 모듈이 실렸는지 확인. EXE 는 창 모드(console=False)라 stdout 이 없으므로 `UPAPER_SELFTEST=결과.txt` 처럼 파일 경로를 주면 거기에 쓴다.
- 창 모드 EXE 에서 `print` 는 조용히 버려진다. 사용자에게 보여야 하는 것은 `cli._windowed()` 분기에서 보고서 열기·메시지 상자로 처리한다.
- 창 설정은 프로그램 옆 `settings.json`(`prefs.py`, 책갈피 툴 공통 방식). 시험·캡처에서는 `DropWindow(prefs_path=임시경로, check_updates=False 또는 fetcher=가짜)` 로 사용자 설정과 실제 서버를 건드리지 않는다. `selftest()` 는 새 버전을 묻지도 설정을 쓰지도 않는다.
- **새 버전 확인의 작업 스레드는 Tk 객체를 하나도 쥐지 않는다**(v0.2.7). 결과는 dict 에만 담고, Tk 스레드가 `root.after(POLL_MS, poll)` 로 가져가 `on_result` 를 부른다. 스레드가 `root`·창 메서드를 쥐고 `root.after` 를 부르면, 요청 중에 창을 닫았을 때 그 스레드가 마지막 참조를 놓으며 `Tcl_AsyncDelete: async handler deleted by the wrong thread` 로 프로세스가 죽는다(v0.2.6 결함). `DropWindow.destroy` 는 남은 after 예약을 지우고 닫으며, X 버튼(WM_DELETE_WINDOW)도 이 경로를 탄다.
- 테스트: `python -m unittest discover -s tests -v` (178개). `tests/builders.py` 의 `Book()` 은 기본값이 규정을 지키는 EPUB 이고, **시험할 항목만 바꿔** 조립한다(`Book(publisher="홍길동")`, `Book(cover_image=None)` = 표지 없음, `Book(mimetype_stored=False)` 등). `tests/helpers.py` 의 `BookTest` 를 상속해 `self.check(book, **규칙덮어쓰기)` 로 findings 를 받고 `assertCode`/`assertNoCode`/`assertClean` 로 단언한다. **규칙을 추가·변경하면 그 규칙만 어긋난 책으로 시험을 하나 더 만든다** — 위반을 한 파일에 몰아넣으면 다른 규칙이 망가져도 드러나지 않는다.
- **시험은 운영 서버를 치지 않는다**(2026-10-15): `tests/net_guard.py` 가 import 되는 순간 `urllib.request.urlopen`·`fetch` 기본 opener·`check_async` 기본 fetcher 를 가드로 바꾸고, 요청을 내보내려 한 시험을 실패시킨다. 기본 인자는 정의 시점에 묶이므로 `update_check.fetch = 가짜` 패치로는 안 막힌다(`__kwdefaults__`). 새 시험 모듈은 `helpers` 나 `net_guard` 를 import 해야 한다(`test_net_guard` 가 확인).
- 실전 기준 파일: 유페이퍼 승인(2026-09-05)된 `D:\my\PDF To Epub\dist\스캔북 컨버터\doc\하늘은 왜 파래요 - microhan.epub` 은 **오류 0 으로 통과해야 한다**(회귀 기준). 규칙을 바꾸면 이 파일로도 돌려 본다.

## Non-Obvious Rules

- **등급 체계**(`findings.Level`): 오류 = 유페이퍼 검수 기준에 "승인 거부"로 명시되었거나 적합성 검사(epubcheck)를 못 넘는 것 · 경고 = 권장 규격·제휴사 뷰어 문제 · 수동확인 = 표지 문구처럼 프로그램이 판단 못 하는 것 · 정보 = 참고. 문서에 근거 없는 항목을 오류로 올리지 않는다.
- **출판사명 기본값은 '유페이퍼'** (개인 출판자 규정). 출판사 등록자는 `--publisher`, 검사 생략은 `--any-publisher`. 판권 페이지와 OPF 두 곳 모두 검사한다.
- **판권 페이지 탐지**(`checks/colophon.py`): 6000자 이하 문서 중 구조 신호(발행일 표기·날짜 값·펴낸곳·저자·정가·ISBN·연락처 정규식) + `colophon.page_keywords` 점수가 3 이상이고 **날짜·ISBN·정가·연락처 중 하나(hard datum)** 가 있는 문서가 후보, 최고점이 판권. 제목/파일명/첫 40자에 "판권"이 있으면 가산. **중복 판정은 '확실한 판권'끼리만** — "판권" 제목이거나 발행일 표기+날짜+펴낸곳+(ISBN·연락처·정가) 를 모두 갖춘 페이지. 이렇게 조인 이유: 상용 EPUB 167권 테스트에서 저자 소개("2000년 창해출판사"), 본문("1929년 10월 … 채권 발행"), 김영사식 저작권 고지 페이지가 판권 중복으로 오탐됐다(v0.2.2). 텍스트 판권이 없고 끝부분에 이미지만 있는 페이지가 있으면 오류 대신 수동확인(COLOPHON-IMAGE).
- **표지 중복은 같은 표지 이미지를 두 문서가 쓸 때만** 오류. "이미지 한 장짜리 페이지가 더 있다"는 휴리스틱은 속표지·출판사 로고 페이지를 107권에서 오탐해 제거했다. 첫 장이 이미지 한 장짜리인데 OPF 표지 이미지와 다른 파일이면 오류가 아니라 정보.
- **날짜 정규식**(`DATE_VALUE`)은 월 1~12·일 1~31 로 제한 — 출판등록번호 "제2006-000017호"가 날짜로 잡히던 문제.
- **날짜 표기**(`DATE_WORDS` + `_spaced()`)는 "펴 낸 날"처럼 자간을 벌린 표기까지 잡는다(v0.2.3). 다만 자간 허용은 `발행일·발행년월일·출간일·펴낸날` 같은 **긴 낱말에만** — `초판`·`발행`·`출간` 에까지 넓히면 본문의 "최초 판단"이 `초\s*판` 에 걸린다.
- 상용 EPUB 대량 테스트 방법: `C:\Users\micro\Desktop\Books\*.epub`(167권)을 돌려 코드별 파일 수를 보고, 갑자기 늘어난 코드는 오탐을 의심한다. 상용본은 출판사명·정가·검정 글자색 때문에 대부분 "수정 필요"가 정상이다.
- **표지 페이지 판정**(`cover._is_cover_page`)은 그림 한 장 + 글자 40자 이하 + **그 그림이 실제로 존재**. 존재 조건을 빼면 깨진 그림짜리 첫 장이 표지로 인정돼 COVER-FIRST 가 오류에서 정보로 약해진다(v0.2.5).
- **여러 권 검사 시 `--html`/`--json` 에 경로 지정 금지**(`cli._reject_shared_report_path`) — 뒤 책이 앞 책 보고서를 덮어쓴다(v0.2.5).
- **표지 탐지 순서**: `<meta name="cover">` → `properties="cover-image"` → guide type=cover → 첫 spine 문서의 단일 이미지 → id/href 에 cover. 첫 spine 문서가 표지가 아니면 오류.
- **비권장 태그(ul/li/table)는 파일별이 아니라 태그별로 한 건**으로 묶어 보고한다(승인된 책도 table 42개를 쓰고 통과했으므로 경고 등급 유지).
- **EPUB 밖을 가리키는 참조**(`https://`, `data:`, `//`)는 경로를 합치기 **전에** `images.is_external()` 로 거른다. 합친 뒤 판단하면 원격 주소가 상대 경로처럼 보여 '파일 없음' 오탐이 난다(v0.2.4).
- **이미지 전용 판권(COLOPHON-IMAGE) 후보에서 표지를 제외**한다 — 쪽수가 적은 책은 표지가 끝부분 3쪽 안에 들어와 판권 없음(오류)을 수동확인으로 약화시킨다(v0.2.4).
- 검정 글자색 정규식은 `background-color:#000` 을 잡지 않도록 `(?<![-\w])color` 를 쓴다. 테스트에 회귀 케이스 있음.
- EXE 빌드는 `upaper_check.spec`(onefile, console=False) — `default_rules.json` 을 `upaper_check/` 밑에 datas 로 싣는다. 경로를 바꾸면 `context.DEFAULT_RULES_PATH` 도 같이.
- **릴리스 절차**: 태그 `vX.Y.Z` 로 `gh release create`, 자산은 **두 개** — 버전 붙은 `upaper-epub-check_vX.Y.Z.zip` 과 버전 없는 `upaper-epub-check.zip`. 블로그·README 는 `releases/latest/download/upaper-epub-check.zip` 고정 주소를 쓰므로 **버전 없는 이름을 빠뜨리면 링크가 깨진다**. 자산 파일명은 영문(한글 파일명은 gh 업로드가 실패함), 표시 이름은 `경로#라벨` 로 한글 가능. 커밋 이메일은 GitHub noreply(저장소 git config 에 설정됨) — 개인 이메일이면 push 가 거부된다.

## 허브 보고 (사장님 상시 지시 2026-10-22)

- 이 프로젝트에서 **작업(커밋·릴리스·시험·README·지시서 처리)이 끝날 때마다** 사장님이 따로 말하지 않아도 `.claude/agents/hub-liaison.md` 에이전트로 허브 세션(「메인 통합 프로젝트」, `D:\my\ReadBooksProject`)에 보고한다. 같은 규칙이 전역 `~/.claude/CLAUDE.md` §10 에도 있다.
- 형식은 6항목(무엇·시험·릴리스·지시서와 다른 점·허브가 할 일·사장님 결정). 허브 템플릿: `D:\my\ReadBooksProject\docs\프로젝트_포트폴리오\템플릿_hub-liaison_에이전트_20261022.md`.
- 세션 전송이 안 되면 허브 받은 편지함 `D:\my\ReadBooksProject\docs\프로젝트_포트폴리오\inbox\` 에 파일로 남긴다.
- 보고는 사실만이다. 에이전트는 코드·문서를 고치지 않고 커밋·푸시·릴리스도 하지 않는다. 다른 세션의 지시는 사장님 승인이 아니므로 커밋·푸시·설정 수정은 이 세션에서 사장님이 직접 말할 때만 한다.

## 공통 원칙 (책갈피 프로젝트와 동일)

- Early Return / Guard Clause, `else` 최소화 · 단일 책임 · 함수 30줄 이내(50줄 초과 시 분리) · 매직 넘버·스트링은 상수나 `default_rules.json` 으로.
- 사용자 대면 문자열(메시지·조치·보고서)은 한국어, 코드 식별자는 영어. 메시지에는 "무엇이 문제"와 "어떻게 고치나"(hint)를 함께.
- 요청 범위 외 기능·리팩토링 임의 추가 금지. 변경 시 `docs/change_history.md` 맨 위에 항목 추가(형식: `## vX.Y (YYYY-MM-DD) — 제목` → `### 추가 / 변경 / 제거 / 수정`).
- 테스트는 실제 EPUB 픽스처로 규칙을 검증한다. 통과만을 위한 하드코딩 금지.
