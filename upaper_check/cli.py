"""명령줄 진입점.

사용 예:
  python upaper_check.py 책.epub
  python upaper_check.py 책.epub --html            # 책_검수보고서.html 을 옆에 생성
  python upaper_check.py 책.epub --html 보고서.html --json 결과.json
  python upaper_check.py 책.epub --publisher "내출판사"   # 등록된 출판사인 경우
"""
from __future__ import annotations

import argparse
import os
import sys

from upaper_check import __version__, epubcheck
from upaper_check.checks import run_all
from upaper_check.checks.cover import find_cover_image
from upaper_check.context import Context, load_rules
from upaper_check.epub import EpubLoadError, EpubPackage
from upaper_check.findings import Finding, Level
from upaper_check.report import Report

AUTO = "auto"
REPORT_SUFFIX = "_검수보고서"
SELFTEST_ENV = "UPAPER_SELFTEST"
EXIT_PASS, EXIT_FAIL, EXIT_LOAD_ERROR = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upaper_check", description="유페이퍼 업로드 전 EPUB 검수")
    parser.add_argument("epub", nargs="+", help="검사할 EPUB 파일(여러 개 가능). 인자 없이 실행하면 파일 선택 창이 열립니다.")
    parser.add_argument("--html", nargs="?", const=AUTO, metavar="PATH",
                        help="HTML 보고서 저장 (경로 생략 시 EPUB 옆에 <이름>_검수보고서.html)")
    parser.add_argument("--json", nargs="?", const=AUTO, metavar="PATH", help="JSON 결과 저장")
    parser.add_argument("--publisher", metavar="NAME", help="기대하는 출판사명 (기본: 유페이퍼)")
    parser.add_argument("--any-publisher", action="store_true", help="출판사명 일치 검사 생략")
    parser.add_argument("--rules", metavar="JSON", help="기준값 덮어쓰기 파일 (default_rules.json 형식)")
    parser.add_argument("--epubcheck", metavar="JAR", help="epubcheck.jar 경로 (있으면 적합성 검사도 함께 실행)")
    parser.add_argument("--no-epubcheck", action="store_true", help="epubcheck.jar 가 있어도 실행하지 않음")
    parser.add_argument("--quiet", action="store_true", help="콘솔에는 요약만 출력")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _force_utf8_console() -> None:
    """Windows 콘솔(cp949)에서 ·, — 같은 문자로 죽지 않도록. EXE 는 PYTHONIOENCODING 을 무시한다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_console()
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return _run_gui()
    args = build_parser().parse_args(argv)
    rules = _rules_from_args(args)
    worst = EXIT_PASS
    for epub_path in args.epub:
        code = _check_one(epub_path, rules, args)
        worst = max(worst, code)
    return worst


def _run_gui() -> int:
    """인자 없이 실행(더블클릭): 끌어다 놓기 창을 띄운다."""
    from upaper_check import gui
    selftest_target = os.environ.get(SELFTEST_ENV)
    if selftest_target:
        _report_selftest(gui.selftest(), selftest_target)
        return EXIT_PASS
    gui.run_window(check_file_for_gui)
    return EXIT_PASS


def _report_selftest(result: str, target: str) -> None:
    """창 모드 EXE 는 콘솔이 없으므로 환경변수 값이 경로면 그 파일에 결과를 쓴다."""
    print(result)
    if target != "1":
        _write(target, result)


def _windowed() -> bool:
    """PyInstaller console=False 로 빌드된 EXE 는 stdout 이 없다."""
    return sys.stdout is None


def check_file_for_gui(epub_path: str, rules: dict | None = None) -> tuple[str, str, bool]:
    """창에서 쓰는 검사 함수: HTML 보고서를 EPUB 옆에 쓰고 (요약, 보고서 경로, 오류 없음) 을 돌려준다."""
    pkg = EpubPackage(epub_path)
    ctx = Context(pkg, rules or load_rules())
    findings = run_all(ctx)
    jar = epubcheck.find_jar(None)
    if jar:
        findings.extend(epubcheck.run(epub_path, jar))
    report = Report(epub_path, findings, _meta_summary(ctx), *_cover_preview(ctx))
    report_path = _output_path(AUTO, epub_path, ".html")
    _write(report_path, report.to_html())
    return f"{os.path.basename(epub_path)}: {report.summary_line()}", report_path, report.passed


def _rules_from_args(args) -> dict:
    rules = load_rules(args.rules)
    if args.any_publisher:
        rules["publisher_expected"] = ""
    elif args.publisher:
        rules["publisher_expected"] = args.publisher
    return rules


def _check_one(epub_path: str, rules: dict, args) -> int:
    try:
        pkg = EpubPackage(epub_path)
    except EpubLoadError as exc:
        message = f"[오류] {epub_path}: {exc}"
        print(message)
        if _windowed():
            from upaper_check import gui
            gui.show_message(message)
        return EXIT_LOAD_ERROR
    ctx = Context(pkg, rules)
    findings = run_all(ctx)
    findings.extend(_maybe_epubcheck(epub_path, args))
    report = Report(epub_path, findings, _meta_summary(ctx), *_cover_preview(ctx))
    _emit(report, epub_path, args)
    return EXIT_PASS if report.passed else EXIT_FAIL


def _maybe_epubcheck(epub_path: str, args) -> list[Finding]:
    if args.no_epubcheck:
        return []
    jar = epubcheck.find_jar(args.epubcheck)
    if jar is None:
        if args.epubcheck:
            return [Finding("EPUBCHECK", Level.WARN, f"epubcheck.jar 를 찾을 수 없습니다: {args.epubcheck}", "")]
        return []
    return epubcheck.run(epub_path, jar)


def _meta_summary(ctx: Context) -> dict:
    meta = ctx.pkg.metadata
    return {
        "도서명": meta.title,
        "저자": ", ".join(meta.creators),
        "출판사": meta.publisher,
        "언어": meta.language,
        "발행일(OPF)": meta.date,
        "EPUB 버전": ctx.pkg.version,
        "본문 파일 수": len(ctx.docs()),
        "목차 항목 수": len(ctx.pkg.nav_points()),
        "파일 크기": f"{os.path.getsize(ctx.pkg.path) / (1024 * 1024):.2f} MB",
    }


def _cover_preview(ctx: Context) -> tuple[bytes | None, str]:
    cover = find_cover_image(ctx)
    if cover is None:
        return None, ""
    path = ctx.path(cover)
    return (ctx.pkg.read(path) if ctx.pkg.exists(path) else None), path


def _emit(report: Report, epub_path: str, args) -> None:
    if args.quiet:
        print(f"{os.path.basename(epub_path)}: {report.summary_line()}")
    else:
        print(report.to_console())
    if _windowed():
        args.html = args.html or AUTO   # 콘솔이 없으면(아이콘 위에 끌어다 놓기) 보고서를 만들어 열어 준다
    if args.html:
        path = _output_path(args.html, epub_path, ".html")
        _write(path, report.to_html())
        print(f"HTML 보고서: {path}")
        if _windowed():
            from upaper_check import gui
            gui.open_report(path)
    if args.json:
        path = _output_path(args.json, epub_path, ".json")
        _write(path, report.to_json())
        print(f"JSON 결과: {path}")


def _output_path(option: str, epub_path: str, ext: str) -> str:
    if option != AUTO:
        return option
    base, _ = os.path.splitext(epub_path)
    return f"{base}{REPORT_SUFFIX}{ext}"


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


if __name__ == "__main__":
    sys.exit(main())
