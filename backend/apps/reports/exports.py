"""Excel and PDF writers. They only format a ReportData that build_report() already limited to what the user may see;
they never query anything themselves."""
import io
from pathlib import Path

from django.conf import settings
from django.utils import timezone
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
    "employees_active": "Faol xodimlar", "employees_total": "Xodimlar (arxivdan tashqari)", "tasks_total": "Davrda yaratilgan topshiriqlar",
    "tasks_done": "Shundan bajarilgan", "tasks_done_rate": "Bajarilish ulushi, %", "tasks_overdue_open": "Muddati o‘tgan (ochiq)",
    "tasks_done_late": "Kechikib bajarilgan", "tasks_completed_in_period": "Davrda yakunlangan topshiriqlar", "documents_total": "Davrda yuklangan hujjatlar",
}
DANGEROUS_START = ("=", "+", "-", "@", "\t", "\r", "\n")


def excel_safe(value):
    """Spreadsheet programs run text that starts with = + - @ as a formula. Data here comes from the database
    (names typed by users), so such text is stored as plain text with a leading apostrophe-like guard."""
    if isinstance(value, str) and value.startswith(DANGEROUS_START):
        return "'" + value
    return value


def filter_lines(data, user):
    f = data.filters
    lines = [
        f"Davr: {f['date_from']:%d.%m.%Y} – {f['date_to']:%d.%m.%Y}",
        f"Doira: {data.scope_note}",
        f"Bo‘lim filtri: {f['department'].name if f.get('department') else 'barchasi'}",
        f"Topshiriq holati: {dict(Task.Status.choices).get(f.get('status'), 'barchasi') if f.get('status') else 'barchasi'}",
        f"Hujjat turkumi: {f['category'].name if f.get('category') else 'barchasi'}",
        f"Tayyorlangan: {timezone.localtime():%d.%m.%Y %H:%M} ({user.get_username()})",
    ]
    return lines


def to_xlsx(data, user) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Umumiy"
    ws.append(["Hisobot"])
    ws["A1"].font = Font(bold=True, size=14)
    for line in filter_lines(data, user):
        ws.append([excel_safe(line)])
    ws.append([])
    ws.append(["Ko‘rsatkich", "Qiymat"])
    for c in ws[ws.max_row]:
        c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="E8EEF9")
    for key, val in data.kpis.items():
        ws.append([KPI_LABELS.get(key, key), val])
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 18
    if data.timeline:
        sheet = wb.create_sheet("Dinamika")
        sheet.append(["Davr", "Yaratilgan", "Yakunlangan"])
        for row in data.timeline:
            sheet.append(list(row))
        _style(sheet)
    for t in data.tables:
        sheet = wb.create_sheet(t.title.replace(":", " –")[:31])
        sheet.append(t.columns)
        for row in t.rows:
            sheet.append([excel_safe(c) for c in row])
        if t.truncated:
            sheet.append([f"… yana {t.total_rows - len(t.rows)} ta qator ko‘rsatilmadi (chegara {len(t.rows)})"])
        if t.note:
            sheet.append([t.note])
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
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title="Hisobot", author="")
    h1 = ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=11, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", fontName="DejaVu", fontSize=8.5, leading=11)
    cell = ParagraphStyle("cell", fontName="DejaVu", fontSize=8, leading=10)
    story = [Paragraph("Hisobot", h1)]
    story += [Paragraph(_esc(line), body) for line in filter_lines(data, user)]
    story.append(Spacer(1, 6))

    def make_table(columns, rows, widths=None):
        head = [Paragraph(f"<b>{_esc(c)}</b>", cell) for c in columns]
        t = Table([head] + [[Paragraph(_esc(c), cell) for c in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF9")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C2D6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    story.append(Paragraph("Asosiy ko‘rsatkichlar", h2))
    story.append(make_table(["Ko‘rsatkich", "Qiymat"], [(KPI_LABELS.get(k, k), v) for k, v in data.kpis.items()], [110 * mm, 40 * mm]))
    limit = settings.REPORT_PDF_MAX_ROWS
    if data.timeline:
        story.append(Paragraph("Topshiriqlar dinamikasi", h2))
        rows = data.timeline[:limit]
        story.append(make_table(["Davr", "Yaratilgan", "Yakunlangan"], rows, [50 * mm, 40 * mm, 40 * mm]))
        if len(data.timeline) > limit:
            story.append(Paragraph(f"… yana {len(data.timeline) - limit} ta davr ko‘rsatilmadi (to‘liq ro‘yxat Excel faylida).", body))
    for t in data.tables:
        story.append(Paragraph(_esc(t.title), h2))
        rows = t.rows[:limit]
        if rows:
            story.append(make_table(t.columns, rows))
        else:
            story.append(Paragraph("Ma’lumot yo‘q.", body))
        if t.total_rows > len(rows):
            story.append(Paragraph(f"… yana {t.total_rows - len(rows)} ta qator ko‘rsatilmadi (to‘liq ro‘yxat Excel faylida).", body))
        if t.note:
            story.append(Paragraph(_esc(t.note), body))
    doc.build(story)
    return buf.getvalue()
