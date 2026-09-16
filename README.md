# 유페이퍼 EPUB 검수기 (upaper-epub-check)

유페이퍼(upaper.net)에 전자책을 올리기 **전에** EPUB 파일이 유페이퍼 검수 기준에 맞는지 미리 검사하는 프로그램입니다.
검수에서 반려되면 다시 고쳐 올리고 며칠을 더 기다려야 하므로, 올리기 전에 한 번 돌려 보는 용도입니다.

기준 문서: 유페이퍼 검수 기준(2015.01.12, `edit.upaper.net/help/regchk.pdf`) · 유페이퍼 EPUB 저작툴 제작 도움말.

## 무엇을 검사하나

| 구분 | 검사 항목 | 등급 |
|---|---|---|
| EPUB 버전 | `<package version>` 이 2.0 계열인지 (EPUB 3 이면 오류), toc.ncx 존재 | 오류 |
| 표지 | 표지 이미지 존재, **파일 첫 장이 표지인지**, 표지 중복, 가로 600~1000px(권장 700x1000), RGB(CMYK 오류), JPG 권장 | 오류/경고/정보 |
| 표지 문구 | 도서명·저자명·출판사명이 표지 그림에 있는지 → HTML 보고서에 표지를 띄워 눈으로 확인 | 수동확인 |
| 출판사명 | OPF `<dc:publisher>` 와 판권 페이지 모두 **'유페이퍼'** 인지 (등록 출판사는 `--publisher` 로 변경) | 오류 |
| 판권 페이지 | 존재·중복, **도서명·저자명·출판사명·출간일·정가** 5요소, ISBN 체크디지트, 마지막 위치 권장. 판권이 이미지뿐이면 수동확인 | 오류/수동확인/정보 |
| 목차 | html 100개 이하, 목차명 빈 항목, 링크 대상 없음, 깊이 3단계 초과, 내용 없는 빈 html | 오류/경고 |
| 크기 | EPUB 30MB 이하, html 각 300KB 이하 | 오류 |
| 금지 태그 | script·iframe·object·embed·form·video·audio 등, onclick 류 이벤트 속성, `javascript:` 링크 | 오류 |
| 비권장 태그 | ul/ol/li(제휴사 뷰어 문제), table(이미지 권장), svg/math/HTML5 구조 태그(EPUB2 미지원) | 경고 |
| 스타일 | 글자색 `#000000`/black 지정(야간모드 → 승인 거부), pt/px 고정 글자 크기(em/% 권장) | 오류/경고 |
| 문서 | XHTML well-formed 여부(적합성 검사), `xml:lang` 언어 설정, 스타일시트 링크 깨짐 | 오류/경고 |
| 이미지·폰트 | 깨진 이미지 참조, CSS 가 가리키는 폰트 파일 없음, manifest 미등록, CMYK 이미지, 안 쓰는 이미지·폰트 | 오류/경고 |
| 메타데이터 | dc:title / dc:creator / dc:language / dc:identifier / dc:date | 오류/경고/정보 |
| (선택) epubcheck | `epubcheck.jar` 가 있으면 유페이퍼 적합성 검사와 같은 엔진으로 추가 검사 | 오류/경고 |

등급 의미 — **오류**: 승인 거부 사유가 될 수 있음(반드시 수정) · **경고**: 권장 규격 이탈·제휴사 문제 · **수동확인**: 사람이 봐야 함 · **정보**: 참고.

## 사용법

### 1) EXE (파이썬 없이)
최신 EXE 내려받기: https://github.com/microhan1/upaper-epub-check/releases/latest/download/upaper-epub-check.zip
(zip 을 풀면 `유페이퍼EPUB검수.exe` 와 이 README 가 있습니다. 직접 만들려면 `빌드.bat`.)
- **더블클릭하면 창이 뜹니다.** 창 안으로 EPUB 파일을 끌어다 놓으면(여러 개 가능) 바로 검사하고, 결과 요약이 창에 적히면서 `<이름>_검수보고서.html` 이 EPUB 옆에 생기고 브라우저로 열립니다. 드롭 영역을 클릭하면 파일 선택 창이 뜹니다.
- EPUB 파일을 EXE 아이콘 위로 끌어다 놓아도 됩니다(창 없이 검사 후 보고서를 브라우저로 엽니다).
- EXE 는 창 모드라 콘솔 출력이 없습니다. 콘솔 출력·`--json` 등 명령줄 기능은 파이썬 소스로 쓰세요.

### 2) 파이썬
```
pip install lxml pillow tkinterdnd2
python upaper_check.py                         # 끌어다 놓기 창
python upaper_check.py 책.epub                 # 콘솔 출력
python upaper_check.py 책.epub --html          # 책_검수보고서.html 생성
python upaper_check.py 책.epub --html 보고서.html --json 결과.json
python upaper_check.py 책.epub --publisher "내출판사"   # 출판사 등록자
python upaper_check.py 책.epub --epubcheck C:\tools\epubcheck.jar
python upaper_check.py a.epub b.epub --quiet   # 여러 권 요약만
```
`검수.bat` 에 EPUB 을 끌어다 놓아도 됩니다.

종료 코드: 0 = 오류 없음, 1 = 오류 있음, 2 = EPUB 을 열 수 없음.

### 기준값 바꾸기
`upaper_check/default_rules.json` 을 복사해 값을 고친 뒤 `--rules 내규칙.json` 으로 넘기면 덮어씁니다
(표지 크기 범위, 파일 크기 한도, 금지/비권장 태그 목록, 판권 키워드 등).

## 테스트
```
python -m unittest discover -s tests -v
```
`tests/make_fixtures.py` 가 규정 준수본(good.epub)과 위반 모음(bad.epub)을 만들어 각 규칙이 잡히는지 확인합니다.

## 구조
```
upaper_check.py            루트 진입점
upaper_check/
  cli.py                   명령줄·창 분기, 보고서 저장
  gui.py                   끌어다 놓기 창 (tkinterdnd2)
  epub.py                  ZIP/OPF/NCX 파서
  xhtml.py                 XHTML 텍스트·이미지·스타일 추출
  context.py               규칙 로드, 문서 파싱 캐시
  checks/                  structure · metadata · cover · colophon · toc · markup · images
  report.py                콘솔 / JSON / HTML 보고서
  epubcheck.py             (선택) epubcheck.jar 연동
  default_rules.json       기준값
tests/                     픽스처 생성기 + 단위 테스트
```

## 라이선스

MIT License — 자유롭게 쓰고 고치고 나눠도 됩니다. 저작자 표시(microhan)만 남겨 주세요. 전문은 [LICENSE](LICENSE).
