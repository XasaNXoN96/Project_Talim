"""Excel and PDF writers. They only format a ReportData that build_report() already limited to what the user may see;
they never query anything themselves."""
import datetime
import io
from pathlib import Path

from django.conf import settings
from django.utils.functional import Promise
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from apps.tasks.models import Task
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_DIR = Path(settings.BASE_DIR) / "assets" / "fonts"
KPI_LABELS = {
    "employees_active": _("Faol xodimlar"), "employees_total": _("Xodimlar (arxivdan tashqari)"), "tasks_total": _("Davrda yaratilgan topshiriqlar"),
    "tasks_done": _("Shundan bajarilgan"), "tasks_done_rate": _("Bajarilish ulushi, %"), "tasks_overdue_open": _("Muddati o‘tgan (ochiq)"),
    "tasks_done_late": _("Kechikib bajarilgan"), "tasks_completed_in_period": _("Davrda yakunlangan topshiriqlar"), "documents_total": _("Davrda yuklangan hujjatlar"),
}
DANGEROUS_START = ("=", "+", "-", "@", "\t", "\r", "\n")


def excel_safe(value):
    """Spreadsheet programs run text that starts with = + - @ as a formula. Data here comes from the database
    (names typed by users), so such text is stored as plain text with a leading apostrophe-like guard."""
    if isinstance(value, Promise):
        value = str(value)
    if isinstance(value, str) and value.startswith(DANGEROUS_START):
        return "'" + value
    return value


def filter_lines(data, user):
    f = data.filters
    all_ = gettext("barchasi")
    status = dict(Task.Status.choices).get(f.get("status")) if f.get("status") else None
    lines = [
        gettext("Davr: %(a)s – %(b)s") % {"a": f"{f['date_from']:%d.%m.%Y}", "b": f"{f['date_to']:%d.%m.%Y}"},
        gettext("Doira: %(scope)s") % {"scope": data.scope_note},
        gettext("Bo‘lim filtri: %(v)s") % {"v": f["department"].name if f.get("department") else all_},
        gettext("Topshiriq holati: %(v)s") % {"v": status or all_},
        gettext("Hujjat turkumi: %(v)s") % {"v": f["category"].name if f.get("category") else all_},
        gettext("Tayyorlangan: %(when)s (%(user)s)") % {"when": f"{timezone.localtime():%d.%m.%Y %H:%M}", "user": user.get_username()},
    ]
    return lines


def to_xlsx(data, user) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = gettext("Umumiy")
    ws.append([gettext("Hisobot")])
    ws["A1"].font = Font(bold=True, size=14)
    for line in filter_lines(data, user):
        ws.append([excel_safe(line)])
    ws.append([])
    ws.append([gettext("Ko‘rsatkich"), gettext("Qiymat")])
    for c in ws[ws.max_row]:
        c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="E8EEF9")
    for key, val in data.kpis.items():
        ws.append([excel_safe(KPI_LABELS.get(key, key)), val])
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 18
    if data.timeline:
        sheet = wb.create_sheet(gettext("Dinamika"))
        sheet.append([gettext("Davr"), gettext("Yaratilgan"), gettext("Yakunlangan")])
        for row in data.timeline:
            sheet.append(list(row))
        _style(sheet)
    for t in data.tables:
        sheet = wb.create_sheet(str(t.title).replace(":", " –")[:31])
        sheet.append([excel_safe(c) for c in t.columns])
        for row in t.rows:
            sheet.append([excel_safe(c) for c in row])
        if t.truncated:
            sheet.append([gettext("… yana %(n)d ta qator ko‘rsatilmadi (chegara %(limit)d)") % {"n": t.total_rows - len(t.rows), "limit": len(t.rows)}])
        if t.note:
            sheet.append([excel_safe(t.note)])
        _style(sheet)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _style(sheet):
    for c in sheet[1]:
        c.font, c.fill, c.alignment = Font(bold=True), PatternFill("solid", fgColor="E8EEF9"), Alignment(wrap_text=True, vertical="top")
    for i, col in enumerate(sheet.columns, 1):
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        sheet.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)
    sheet.freeze_panes = "A2"


_fonts_ready = False


def _fonts():
    global _fonts_ready
    if not _fonts_ready:
        pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")
        _fonts_ready = True


def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_pdf(data, user) -> bytes:
    _fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=gettext("Hisobot"), author="")
    h1 = ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=11, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", fontName="DejaVu", fontSize=8.5, leading=11)
    cell = ParagraphStyle("cell", fontName="DejaVu", fontSize=8, leading=10)
    story = [Paragraph(gettext("Hisobot"), h1)]
    story += [Paragraph(_esc(line), body) for line in filter_lines(data, user)]
    story.append(Spacer(1, 6))

    def make_table(columns, rows, widths=None):
        head = [Paragraph(f"<b>{_esc(c)}</b>", cell) for c in columns]
        t = Table([head] + [[Paragraph(_esc(c), cell) for c in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF9")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C2D6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    story.append(Paragraph(gettext("Asosiy ko‘rsatkichlar"), h2))
    story.append(make_table([gettext("Ko‘rsatkich"), gettext("Qiymat")], [(str(KPI_LABELS.get(k, k)), v) for k, v in data.kpis.items()], [110 * mm, 40 * mm]))
    limit = settings.REPORT_PDF_MAX_ROWS
    if data.timeline:
        story.append(Paragraph(gettext("Topshiriqlar dinamikasi"), h2))
        rows = data.timeline[:limit]
        story.append(make_table([gettext("Davr"), gettext("Yaratilgan"), gettext("Yakunlangan")], rows, [50 * mm, 40 * mm, 40 * mm]))
        if len(data.timeline) > limit:
            story.append(Paragraph(gettext("… yana %(n)d ta davr ko‘rsatilmadi (to‘liq ro‘yxat Excel faylida).") % {"n": len(data.timeline) - limit}, body))
    for t in data.tables:
        story.append(Paragraph(_esc(str(t.title)), h2))
        rows = t.rows[:limit]
        if rows:
            story.append(make_table(t.columns, rows))
        else:
            story.append(Paragraph(gettext("Ma’lumot yo‘q."), body))
        if t.total_rows > len(rows):
            story.append(Paragraph(gettext("… yana %(n)d ta qator ko‘rsatilmadi (to‘liq ro‘yxat Excel faylida).") % {"n": t.total_rows - len(rows)}, body))
        if t.note:
            story.append(Paragraph(_esc(t.note), body))
    doc.build(story)
    return buf.getvalue()


MAX_DETAIL_ROWS = 5000  # per sheet of the school workbook; the totals sheet is never cut


def schools_to_xlsx(rows, total, user) -> bytes:
    """Workbook of the statistics by school: totals per school, then the tasks and the achievements behind them (what the administrator may see).
    Written from rows that apps.reports.schools already computed; names of staff are never included. Text from the database goes through excel_safe."""
    from apps.achievements.models import Achievement
    from . import schools as school_stats

    wb = Workbook()
    ws = wb.active
    ws.title = gettext("Maktablar")
    ws.append([gettext("Maktablar bo‘yicha statistika")])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([gettext("Hisoblash butun tarix bo‘yicha; bir nechta muassasaga berilgan topshiriq har biriga hisoblanadi.")])
    ws.append([gettext("Tayyorlangan: %(when)s (%(user)s)") % {"when": f"{timezone.localtime():%d.%m.%Y %H:%M}", "user": excel_safe(user.get_username())}])
    ws.append([])
    ws.append([gettext("Muassasa"), gettext("Turi"), gettext("Faol direktor hisoblari"), gettext("Xodimlar"), gettext("Topshiriqlar"), gettext("Bajarilgan"),
               gettext("Bajarilish ulushi, %"), gettext("Jarayonda"), gettext("Muddati o‘tgan"), gettext("Kechikkan"), gettext("Yutuqlar"),
               gettext("Nashr etilgan yutuqlar"), gettext("Tekshiruvni kutmoqda")])
    header_row = ws.max_row
    for c in ws[header_row]:
        c.font, c.fill, c.alignment = Font(bold=True), PatternFill("solid", fgColor="E8EEF9"), Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append([excel_safe(r.institution.name), excel_safe(r.institution.get_kind_display()), r.directors, r.staff, r.tasks, r.done, r.rate, r.open, r.overdue, r.late,
                   r.ach_total, r.ach_published, r.ach_pending])
    ws.append([gettext("Jami"), "", total.directors, total.staff, total.tasks, total.done, total.rate, total.open, total.overdue, total.late, total.ach_total,
               total.ach_published, total.ach_pending])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for i, col in enumerate(ws.iter_cols(min_row=header_row), 1):
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 12), 40)
    ws.column_dimensions["A"].width = 44
    ws.freeze_panes = ws.cell(row=header_row + 1, column=2)

    tasks = wb.create_sheet(gettext("Topshiriqlar"))
    tasks.append([gettext("Muassasa"), gettext("Topshiriq"), gettext("Muddat"), gettext("Holat"), gettext("Muddati o‘tgan"), gettext("Ustuvorlik")])
    cut = False
    names = {r.institution.pk: r.institution.name for r in rows}
    pairs = sorted(school_stats.school_tasks(), key=lambda p: (names.get(p[0], "").lower(), p[1].due_date is None, p[1].due_date or datetime.date.min, p[1].due_time or datetime.time.min))
    for n, (inst_id, t) in enumerate(pairs):
        if n >= MAX_DETAIL_ROWS:
            cut = True
            break
        name = names.get(inst_id, "")
        due = ""
        if t.due_date:
            due = f"{t.due_date:%d.%m.%Y}" + (f" {t.due_time:%H:%M}" if t.due_time else "")
        tasks.append([excel_safe(name), excel_safe(t.title), due, excel_safe(t.get_status_display()), gettext("ha") if t.is_overdue else "", excel_safe(t.get_priority_display())])
    if cut:
        tasks.append([gettext("… ro‘yxat %(limit)d qatorda to‘xtatildi") % {"limit": MAX_DETAIL_ROWS}])
    _style(tasks)

    ach = wb.create_sheet(gettext("Yutuqlar"))
    ach.append([gettext("Muassasa"), gettext("Sarlavha"), gettext("Kim"), gettext("Turi"), gettext("Daraja"), gettext("Holat")])
    qs = Achievement.objects.exclude(status=Achievement.Status.DRAFT).select_related("institution").order_by("institution__name", "-created_at")[:MAX_DETAIL_ROWS]
    for a in qs:  # unsent drafts are not for the administrator: they stay out of the file too
        ach.append([excel_safe(a.institution.name), excel_safe(a.title), excel_safe(a.person_name), excel_safe(a.get_kind_display()), excel_safe(a.get_level_display()), excel_safe(a.get_status_display())])
    _style(ach)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def schools_to_pdf(rows, total, user) -> bytes:
    """A short printable summary of the statistics by school: the figures per school and the open tasks that are past their deadline.
    The complete lists (every task, every achievement) are in the Excel file; the page says so. No staff names. Same rows as the page."""
    from . import schools as school_stats

    _fonts()
    buf = io.BytesIO()
    title = gettext("Maktablar bo‘yicha statistika")
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=title, author="")
    h1 = ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=11, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", fontName="DejaVu", fontSize=8.5, leading=11)
    cell = ParagraphStyle("cell", fontName="DejaVu", fontSize=8, leading=10)
    num = ParagraphStyle("num", parent=cell, alignment=2)
    hcell = ParagraphStyle("hcell", parent=cell, fontSize=7, leading=8.5)  # header cells: smaller, so whole words fit the narrow figure columns
    hnum = ParagraphStyle("hnum", parent=hcell, alignment=2)
    bad = ParagraphStyle("bad", parent=num, fontName="DejaVu-Bold", textColor=colors.HexColor("#B42318"))

    def table(columns, data, widths, numeric_from=1):
        head = [Paragraph(f"<b>{_esc(c)}</b>", hcell if i < numeric_from else hnum) for i, c in enumerate(columns)]
        t = Table([head] + data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF9")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C2D6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    story = [Paragraph(_esc(title), h1),
             Paragraph(_esc(gettext("Tayyorlangan: %(when)s (%(user)s)") % {"when": f"{timezone.localtime():%d.%m.%Y %H:%M}", "user": user.get_username()}), body),
             Paragraph(_esc(gettext("Hisoblash butun tarix bo‘yicha; bir nechta muassasaga berilgan topshiriq har biriga hisoblanadi.")), body), Spacer(1, 6)]
    cols = [gettext("Muassasa"), gettext("Direktor hisobi"), gettext("Xodimlar"), gettext("Topshiriqlar"), gettext("Bajarilgan"), gettext("Bajarilgan, %"),
            gettext("Jarayonda"), gettext("Muddati o‘tgan"), gettext("Kechikkan"), gettext("Yutuqlar"), gettext("Tekshiruvni kutmoqda")]
    P = lambda v, style=num: Paragraph(_esc("" if v is None else v), style)
    data = [[P(r.institution.name, cell), P(r.directors), P(r.staff), P(r.tasks), P(r.done), P(r.rate), P(r.open), P(r.overdue, bad if r.overdue else num), P(r.late), P(f"{r.ach_published} / {r.ach_total}"), P(r.ach_pending)] for r in rows]
    bold = ParagraphStyle("b", parent=num, fontName="DejaVu-Bold")
    data.append([Paragraph(f"<b>{_esc(gettext('Jami'))}</b>", cell)] + [P(v, bold) for v in (total.directors, total.staff, total.tasks, total.done, total.rate, total.open, total.overdue, total.late, f"{total.ach_published} / {total.ach_total}", total.ach_pending)])
    # each figure column is as wide as the longest WORD of its header (in this language) needs, so no word is ever torn apart; the name column takes the rest
    usable = (297 - 28) * mm
    figure_w = [max(max(pdfmetrics.stringWidth(w, "DejaVu-Bold", 7) for w in c.split()) + 15, 15 * mm) for c in cols[1:]]
    widths = [max(usable - sum(figure_w), 40 * mm)] + figure_w
    story.append(table(cols, data, widths))
    story.append(Paragraph(_esc(gettext("Yutuqlar: nashr etilgan / jami.")), body))

    names = {r.institution.pk: r.institution.name for r in rows}
    overdue = sorted(((names.get(i, ""), t) for i, t in school_stats.school_tasks() if t.is_overdue), key=lambda p: (p[0].lower(), p[1].deadline))
    story.append(Paragraph(_esc(gettext("Muddati o‘tgan ochiq topshiriqlar")), h2))
    limit = settings.REPORT_PDF_MAX_ROWS
    if overdue:
        story.append(table([gettext("Muassasa"), gettext("Topshiriq"), gettext("Muddat"), gettext("Holat"), gettext("Ustuvorlik")],
                           [[P(n, cell), P(t.title, cell), P(f"{t.due_date:%d.%m.%Y}" + (f" {t.due_time:%H:%M}" if t.due_time else ""), cell), P(t.get_status_display(), cell), P(t.get_priority_display(), cell)] for n, t in overdue[:limit]],
                           [60 * mm, 100 * mm, 32 * mm, 35 * mm, 35 * mm], numeric_from=5))
        if len(overdue) > limit:
            story.append(Paragraph(_esc(gettext("… yana %(n)d ta qator ko‘rsatilmadi (to‘liq ro‘yxat Excel faylida).") % {"n": len(overdue) - limit}), body))
    else:
        story.append(Paragraph(_esc(gettext("Muddati o‘tgan topshiriqlar yo‘q.")), body))
    story.append(Spacer(1, 6))
    story.append(Paragraph(_esc(gettext("Barcha topshiriqlar va yutuqlar ro‘yxati — Excel faylida.")), body))
    doc.build(story)
    return buf.getvalue()
