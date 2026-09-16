"""검수 결과 출력 — 콘솔·JSON·HTML."""
from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
from datetime import datetime

from upaper_check import __version__
from upaper_check.findings import Finding, Level, count_by_level, sort_findings

FINAL_CHECKLIST = (
    "표지는 제대로 들어가 있는가 (도서명·저자명·출판사명 포함)",
    "목차의 이름은 제대로 들어가 있는가",
    "판권의 내용은 올바르게 들어가 있는가 (도서명·저자명·출판사명·출간일·정가)",
    "오탈자를 포함한 본문의 편집은 완료되었는가",
    "도서소개·저자소개는 4000bytes 이내인가 (등록 화면 입력값)",
)
LEVEL_MARK = {Level.ERROR: "[오류]", Level.WARN: "[경고]", Level.MANUAL: "[확인]", Level.INFO: "[정보]"}
LEVEL_CSS = {Level.ERROR: "error", Level.WARN: "warn", Level.MANUAL: "manual", Level.INFO: "info"}


class Report:
    def __init__(self, epub_path: str, findings: list[Finding], meta: dict, cover_bytes: bytes | None = None,
                 cover_name: str = ""):
        self.epub_path = epub_path
        self.findings = sort_findings(findings)
        self.meta = meta
        self.cover_bytes = cover_bytes
        self.cover_name = cover_name
        self.counts = count_by_level(self.findings)
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    @property
    def passed(self) -> bool:
        return self.counts[Level.ERROR] == 0

    # ---------- 콘솔 ----------
    def to_console(self) -> str:
        lines = [f"유페이퍼 EPUB 검수 v{__version__} — {os.path.basename(self.epub_path)}", ""]
        lines.extend(f"  {k}: {v}" for k, v in self.meta.items() if v)
        lines.append("")
        lines.append(self.summary_line())
        lines.append("")
        for finding in self.findings:
            lines.append(f"{LEVEL_MARK[finding.level]} {finding.code}  {finding.message}")
            if finding.location:
                lines.append(f"        위치: {finding.location}")
            if finding.hint:
                lines.append(f"        조치: {finding.hint}")
        lines.append("")
        lines.append("판매신청 전 마지막 확인 (유페이퍼 검수 기준):")
        lines.extend(f"  [ ] {item}" for item in FINAL_CHECKLIST)
        return "\n".join(lines)

    def summary_line(self) -> str:
        verdict = "통과 (오류 없음)" if self.passed else "수정 필요"
        return (f"결과: {verdict} — 오류 {self.counts[Level.ERROR]} · 경고 {self.counts[Level.WARN]} · "
                f"수동확인 {self.counts[Level.MANUAL]} · 정보 {self.counts[Level.INFO]}")

    # ---------- JSON ----------
    def to_json(self) -> str:
        payload = {
            "tool": f"upaper-epub-check {__version__}",
            "file": self.epub_path,
            "generated_at": self.generated_at,
            "passed": self.passed,
            "counts": {level.value: n for level, n in self.counts.items()},
            "metadata": self.meta,
            "findings": [f.to_dict() for f in self.findings],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    # ---------- HTML ----------
    def to_html(self) -> str:
        rows = "\n".join(self._row(f) for f in self.findings) or '<tr><td colspan="4">지적 사항 없음</td></tr>'
        meta_rows = "\n".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
                              for k, v in self.meta.items())
        checklist = "\n".join(f"<li><label><input type=\"checkbox\"> {html.escape(item)}</label></li>"
                              for item in FINAL_CHECKLIST)
        verdict_class = "pass" if self.passed else "fail"
        return HTML_TEMPLATE.format(
            title=html.escape(os.path.basename(self.epub_path)), version=__version__,
            generated=self.generated_at, verdict_class=verdict_class,
            summary=html.escape(self.summary_line()), meta_rows=meta_rows, cover=self._cover_html(),
            rows=rows, checklist=checklist)

    def _row(self, finding: Finding) -> str:
        return (f'<tr class="{LEVEL_CSS[finding.level]}"><td class="lv">{html.escape(finding.level.value)}</td>'
                f"<td><code>{html.escape(finding.code)}</code></td>"
                f"<td>{html.escape(finding.message)}"
                + (f'<div class="hint">조치: {html.escape(finding.hint)}</div>' if finding.hint else "")
                + f"</td><td class=\"loc\">{html.escape(finding.location)}</td></tr>")

    def _cover_html(self) -> str:
        if not self.cover_bytes:
            return "<p>표지 이미지를 찾지 못했습니다.</p>"
        mime = mimetypes.guess_type(self.cover_name)[0] or "image/jpeg"
        data = base64.b64encode(self.cover_bytes).decode("ascii")
        return (f'<img src="data:{mime};base64,{data}" alt="표지">'
                f"<p class=\"cap\">{html.escape(self.cover_name)} — 도서명·저자명·출판사명이 보이는지 확인</p>")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>유페이퍼 EPUB 검수 — {title}</title>
<style>
:root {{ --paper:#FAF6EF; --ink:#2C2822; --brown:#6B4F3B; --gold:#C9A66B; --red:#8E2B2B; }}
body {{ font-family: "Noto Serif KR", "Malgun Gothic", serif; background: var(--paper); color: var(--ink);
       margin: 0; padding: 24px 16px; line-height: 1.6; }}
main {{ max-width: 1100px; margin: 0 auto; }}
h1 {{ color: var(--brown); font-size: 1.5em; margin: 0 0 4px; }}
.sub {{ color: #6B6257; font-size: .9em; margin-bottom: 16px; }}
.verdict {{ padding: 12px 16px; border-radius: 8px; font-weight: bold; margin-bottom: 20px; }}
.verdict.pass {{ background: #E3EFD9; color: #2F5D2A; }}
.verdict.fail {{ background: #F5DEDE; color: var(--red); }}
.grid {{ display: grid; grid-template-columns: 1fr 240px; gap: 20px; margin-bottom: 20px; }}
@media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} }}
table {{ width: 100%; border-collapse: collapse; background: #fff; }}
th, td {{ border: 1px solid #E0D8C8; padding: 8px 10px; text-align: left; vertical-align: top; font-size: .93em; }}
th {{ background: #F5F1E8; white-space: nowrap; }}
.cover img {{ max-width: 100%; border: 1px solid #E0D8C8; }}
.cap {{ font-size: .8em; color: #6B6257; }}
tr.error td.lv {{ color: var(--red); font-weight: bold; }}
tr.warn td.lv {{ color: #9A6A1B; font-weight: bold; }}
tr.manual td.lv {{ color: #3B5B8E; font-weight: bold; }}
tr.info td.lv {{ color: #6B6257; }}
td.loc {{ font-family: Consolas, monospace; font-size: .82em; word-break: break-all; }}
.hint {{ color: #6B6257; font-size: .88em; margin-top: 4px; }}
code {{ background: #F5F1E8; padding: 1px 4px; border-radius: 3px; }}
ul.check {{ list-style: none; padding: 0; }}
ul.check li {{ padding: 4px 0; }}
</style></head><body><main>
<h1>유페이퍼 EPUB 검수 보고서</h1>
<div class="sub">{title} · upaper-epub-check v{version} · {generated}</div>
<div class="verdict {verdict_class}">{summary}</div>
<div class="grid">
  <div><table>{meta_rows}</table></div>
  <div class="cover">{cover}</div>
</div>
<table>
<thead><tr><th>등급</th><th>코드</th><th>내용 / 조치</th><th>위치</th></tr></thead>
<tbody>
{rows}
</tbody></table>
<h2 style="font-size:1.1em;color:var(--brown);margin-top:28px">판매신청 전 마지막 확인</h2>
<ul class="check">
{checklist}
</ul>
<p class="cap">기준: 유페이퍼 검수 기준(2015.01.12, edit.upaper.net/help/regchk.pdf) · 유페이퍼 EPUB 저작툴 제작 도움말</p>
</main></body></html>
"""
