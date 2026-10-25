"""Rich fictitious content for the demo site (LOCAL DEVELOPMENT ONLY; called by seed_demo).

News with cover pictures, achievements with certificates, photos and videos, a media gallery, documents, more tasks with comments, chat
conversations, notifications, staff cards with portraits and a week of attendance. Everything is fictitious and drawn (apps.core.demo_art);
nothing here is a real person, award or photograph. Idempotent: each block runs only when its own marker is missing."""
import datetime
import hashlib
import random
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.achievements.models import Achievement, AchievementImage, AchievementVideo
from apps.attendance.models import AttendanceEvent, AttendanceNoticeAcceptance, WorkZone
from apps.chat import services as chat_services
from apps.content.models import News, NewsCategory
from apps.core import demo_art as art
from apps.documents.models import Document, DocumentCategory
from apps.documents.services import add_version
from apps.documents.storage import new_storage_name
from apps.documents.validation import CheckedUpload
from apps.gallery.models import MediaItem
from apps.notifications.models import Notification
from apps.organization.access import school_staff_department
from apps.organization.models import Department, Employee, Institution, Position
from apps.tasks.models import Task, TaskComment

User = get_user_model()
ASSETS = Path(__file__).resolve().parent / "demo_assets"
VIDEOS = ["video_ceremony.mp4", "video_sport.mp4", "video_lesson.mp4"]

MORE_SCHOOLS = [
    ("DEMO 4-sonli maktab", "school", "Namunaviy Direktor 4", True),
    ("DEMO 5-ixtisoslashtirilgan maktab", "specialized", "Namunaviy Direktor 5", True),
    ("DEMO 12-sonli maktabgacha ta’lim muassasasi", "preschool", "Namunaviy Mudira 12", True),
    ("DEMO Ijod maktabi", "arts", "Namunaviy Rahbar", True),
    ("DEMO Kasb-hunar maktabi", "vocational", "Namunaviy Direktor KH", True),
]

STAFF = [  # last, first, middle, position, school index (0-based into the schools list), phone tail
    ("Karimova", "Gulnora", "Akbarovna", "O‘qituvchi", 0), ("Rahimov", "Bekzod", "Olimovich", "Direktor o‘rinbosari (o‘quv ishlari bo‘yicha)", 0),
    ("Tursunova", "Madina", "Rustamovna", "Kutubxonachi", 0), ("Yusupov", "Anvar", "Karimovich", "O‘qituvchi", 1),
    ("Qodirova", "Dilnoza", "Sobirovna", "Amaliy psixolog", 1), ("Normatov", "Sherzod", "Baxtiyorovich", "O‘qituvchi", 1),
    ("Ergasheva", "Sevinch", "Nodirovna", "O‘qituvchi", 3), ("Abdullayev", "Otabek", "Ilhomovich", "Ijtimoiy pedagog", 3),
    ("Sodiqova", "Zilola", "Ravshanovna", "Tarbiyachi", 5), ("Hamidov", "Jamshid", "Umidovich", "O‘qituvchi", 4),
    ("Ismoilova", "Nargiza", "Alisherovna", "Metodist", None), ("Ortiqov", "Farhod", "Davronovich", "Buxgalter", None),
    ("Mamatqulova", "Shahnoza", "Otabekovna", "Inspektor", None), ("Zokirov", "Ulug‘bek", "Sanjarovich", "Bosh mutaxassis", None),
    ("Nazarova", "Feruza", "Jahongirovna", "O‘qituvchi", 6), ("Saidov", "Doston", "Mirzoyevich", "Direktor o‘rinbosari (moliya-xo‘jalik ishlari bo‘yicha)", 4),
]

NEWS_ITEMS = [  # slug, title, category, excerpt, scene, seed, days ago, status
    ("demo-yangi-oquv-yiliga-tayyorgarlik", "Yangi o‘quv yiliga tayyorgarlik bo‘yicha tuman yig‘ilishi o‘tkazildi", "E’lonlar",
     "Yig‘ilishda maktablarning tayyorgarlik holati, o‘quv xonalari va darsliklar bilan ta’minlanish masalalari muhokama qilindi.", "building", 1, 2, "published"),
    ("demo-ustozlar-kuni-tantanasi", "Ustozlar va murabbiylar kuni tantanali nishonlandi", "Tadbirlar",
     "Tuman madaniyat markazida o‘tgan tadbirda eng yaxshi o‘qituvchilar va murabbiylar mukofotlandi.", "ceremony", 2, 5, "published"),
    ("demo-fan-olimpiadasi-goliblari", "Tuman fan olimpiadasi g‘oliblari taqdirlandi", "Yutuqlar",
     "Matematika, fizika va ona tili fanlaridan o‘tkazilgan olimpiadada 120 dan ortiq o‘quvchi ishtirok etdi.", "olympiad", 3, 8, "published"),
    ("demo-sogalom-avlod-musobaqalari", "Maktablarda «Sog‘lom avlod» sport musobaqalari boshlandi", "Sport",
     "Futbol, voleybol va yengil atletika bo‘yicha musobaqalar tuman stadionida davom etmoqda.", "sport", 4, 11, "published"),
    ("demo-axborot-texnologiyalari-malaka", "Axborot texnologiyalari o‘qituvchilari malaka oshirdi", "Metodika",
     "Ikki haftalik kursda o‘qituvchilar zamonaviy o‘quv platformalari va raqamli resurslar bilan ishlashni o‘rgandi.", "computer", 5, 14, "published"),
    ("demo-kitobxon-oila-tanlovi", "Maktab kutubxonalarida «Kitobxon oila» tanlovi", "Tadbirlar",
     "Tanlov doirasida o‘quvchilar ota-onalari bilan birgalikda o‘qigan kitoblari haqida taqdimot tayyorladi.", "library", 6, 18, "published"),
    ("demo-yosh-kimyogarlar", "Yosh kimyogarlar tuman tanlovida", "Yutuqlar",
     "Ixtisoslashtirilgan maktab o‘quvchilari laboratoriya tajribalari bo‘yicha loyihalarini taqdim etdi.", "lab", 7, 22, "published"),
    ("demo-yashil-makon-aksiyasi", "Bog‘chalarda «Yashil makon» ekish aksiyasi", "Tadbirlar",
     "Tarbiyalanuvchilar va ularning ota-onalari bog‘cha hovlilariga ko‘chatlar o‘tqazdi.", "garden", 8, 27, "published"),
    ("demo-hisobot-konserti", "San’at maktablari hisobot konserti o‘tkazildi", "Tadbirlar",
     "Konsertda 200 dan ortiq yosh ijrochi qatnashdi, eng yaxshi chiqishlar maxsus diplom bilan taqdirlandi.", "music", 9, 33, "published"),
    ("demo-metodik-tavsiyalar-yangilandi", "2026–2027 o‘quv yili uchun metodik tavsiyalar yangilandi", "Metodika",
     "Yangilangan tavsiyalar «Hujjatlar» bo‘limida e’lon qilingan. Maktab rahbarlaridan ularni o‘quv rejalariga kiritish so‘raladi.", "classroom", 10, 38, "published"),
    ("demo-ochiq-darslar-haftaligi", "Ochiq darslar haftaligi yakunlandi", "Metodika",
     "Haftalik davomida 40 dan ortiq ochiq dars o‘tkazildi; eng yaxshi ishlanmalar tuman metodik markaziga topshirildi.", "classroom", 11, 45, "published"),
    ("demo-bosh-ish-orinlari", "Bo‘sh ish o‘rinlari to‘g‘risida e’lon", "E’lonlar",
     "Tuman maktablarida o‘qituvchi, kutubxonachi va tarbiyachi lavozimlariga ariza qabul qilinmoqda.", "building", 12, 3, "review"),
    ("demo-qishki-tanaffus-rejasi", "Qishki tanaffus tadbirlari rejasi (qoralama)", "E’lonlar",
     "Reja tayyorlanmoqda: musobaqalar, ko‘rgazmalar va ochiq eshiklar kuni.", "ceremony", 13, 1, "draft"),
]
NEWS_BODY = (
    "{excerpt}\n\n"
    "Tadbirda tuman Xalq ta’limi bo‘limi xodimlari, maktab rahbarlari, o‘qituvchilar va o‘quvchilar ishtirok etdi. Ishtirokchilar ta’lim sifatini oshirish, "
    "o‘quvchilarning bilim va ko‘nikmalarini rivojlantirish bo‘yicha fikr almashdi.\n\n"
    "Bo‘lim vakillari bunday tadbirlar muntazam o‘tkazib borilishini ta’kidladi. Batafsil ma’lumot va keyingi e’lonlar rasmiy saytda e’lon qilinadi.\n\n"
    "(Namunaviy matn: bu demonstratsiya uchun yozilgan, haqiqiy yangilik emas.)"
)

# title, kind, level, person_kind, name, position, school index, art, days ago, video index
ACHIEVEMENTS = [
    ("Respublika fan olimpiadasida 1-o‘rin", "medal", "republic", "student", "Aliyev Jasur", "9-sinf, matematika", 0, "olympiad", 6, 0),
    ("Yilning eng yaxshi o‘qituvchisi: tuman bosqichi", "award", "district", "teacher", "Karimova Gulnora", "Ona tili o‘qituvchisi", 1, "ceremony", 9, None),
    ("Viloyat informatika tanlovi g‘olibi", "diploma", "region", "student", "Rahimov Bekzod", "11-sinf", 0, "computer", 13, None),
    ("Xalqaro «Kenguru» matematika musobaqasi sertifikati", "certificate", "international", "student", "Tursunova Madina", "7-sinf", 1, "classroom", 17, None),
    ("Innovatsion dars ishlanmasi tanlovi: 2-o‘rin", "certificate", "region", "teacher", "Yusupov Anvar", "Fizika o‘qituvchisi", 3, "lab", 21, None),
    ("Sport o‘yinlari tuman bosqichi: jamoa g‘olibligi", "medal", "district", "team", "5-maktab futbol jamoasi", "O‘smirlar jamoasi", 4, "sport", 25, 1),
    ("Eng yaxshi maktab kutubxonasi", "award", "district", "team", "1-maktab kutubxonasi", "Kutubxona jamoasi", 0, "library", 29, None),
    ("«Yosh iste’dod» ijodiy tanlovi: Gran-pri", "diploma", "republic", "student", "Ergasheva Sevinch", "Tasviriy san’at", 5, "music", 34, None),
    ("Maktabgacha ta’lim muassasalari ko‘rik-tanlovi: 1-o‘rin", "certificate", "region", "team", "12-sonli bog‘cha jamoasi", "Tarbiyachilar jamoasi", 6, "garden", 38, None),
    ("Kasb-hunar olimpiadasi: oltin medal", "medal", "region", "student", "Hamidov Jamshid", "2-kurs", 7, "lab", 42, None),
    ("Respublika «Eng yaxshi ustoz» ko‘rigi finalchisi", "certificate", "republic", "teacher", "Normatov Sherzod", "Tarix o‘qituvchisi", 1, "ceremony", 47, None),
    ("Tuman ochiq darslar tanlovi: 1-o‘rin", "diploma", "district", "teacher", "Qodirova Dilnoza", "Boshlang‘ich sinf o‘qituvchisi", 1, "classroom", 52, 2),
]
LEVEL_LABEL = {"institution": "Muassasa darajasi", "district": "Tuman darajasi", "region": "Viloyat darajasi", "republic": "Respublika darajasi", "international": "Xalqaro daraja"}

GALLERY = [  # scene, seed, title, school index (None = all), days ago, video index handled separately
    ("ceremony", 21, "Ustozlar kuni: tantanali yig‘ilish", None, 5), ("olympiad", 22, "Fan olimpiadasi: bahs paytida", None, 8),
    ("sport", 23, "Sport musobaqasi: finaldan lavha", 4, 11), ("computer", 24, "Kompyuter sinfida mashg‘ulot", 0, 14),
    ("library", 25, "Kutubxonada kitobxonlik kuni", 0, 18), ("lab", 26, "Laboratoriya tajribalari", 3, 22),
    ("garden", 27, "Yashil makon aksiyasi", 6, 27), ("music", 28, "Hisobot konserti", 5, 33),
    ("classroom", 29, "Ochiq dars", 1, 38), ("building", 30, "Maktab binosi", 1, 45),
    ("ceremony", 31, "Mukofotlash marosimi", None, 50), ("sport", 32, "Yengil atletika bo‘yicha jamoa", 4, 55),
    ("garden", 33, "Bog‘cha hovlisida ekish", 6, 60), ("music", 34, "Sinf xori", 5, 64),
    ("lab", 35, "Yosh kimyogarlar", 3, 68), ("classroom", 36, "Yangi o‘quv yiliga tayyorgarlik", None, 3),
]
GALLERY_VIDEOS = [("Ustozlar kuni tantanasi", 0, None, 5, "published"), ("Tuman sport musobaqasi", 1, 4, 11, "published"), ("Ochiq dars lavhasi", 2, 1, 38, "draft")]

DOCS = [  # category, title, number, days ago, lines
    ("Buyruqlar", "Yangi o‘quv yilini tashkil etish to‘g‘risida buyruq", "12-son", 60, ["Tuman maktablarida 2026–2027 o‘quv yilini tashkil etish tartibi belgilanadi.", "Mas’ul shaxslar: maktab direktorlari."]),
    ("Buyruqlar", "Fan olimpiadalarini o‘tkazish tartibi", "15-son", 45, ["Tuman bosqichidagi fan olimpiadalari jadvali va ishtirokchilar ro‘yxati."]),
    ("Nizomlar va yo‘riqnomalar", "Maktab kutubxonalari faoliyati to‘g‘risida nizom", "—", 90, ["Kutubxona fondini shakllantirish, hisobga olish va foydalanish qoidalari."]),
    ("Nizomlar va yo‘riqnomalar", "Ochiq darslar o‘tkazish bo‘yicha yo‘riqnoma", "—", 70, ["Ochiq dars rejasi, baholash mezonlari va hujjatlashtirish tartibi."]),
    ("Hisobotlar", "2026-yil I yarim yillik faoliyat hisoboti", "—", 20, ["Asosiy ko‘rsatkichlar: o‘quvchilar soni, o‘qituvchilar, olimpiada natijalari.", "Raqamlar namunaviy."]),
    ("Hisobotlar", "Maktablar bo‘yicha o‘quv yiliga tayyorgarlik holati", "—", 10, ["Har bir maktab uchun tayyorgarlik bandlari va kamchiliklar ro‘yxati."]),
    ("Shablonlar va namunalar", "Yutuq to‘g‘risida ma’lumotnoma shabloni", "—", 30, ["Maktab yutuqni saytga yuborishda shu namunadan foydalanadi."]),
    ("Boshqa", "Metodik tavsiyalar: 2026–2027 o‘quv yili", "—", 7, ["O‘quv rejalari, dars soatlari va baholash bo‘yicha yangilangan tavsiyalar."]),
]


def _now_minus(days, hour=10):
    return timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0) - datetime.timedelta(days=days)


def _staff_cards(schools):
    dept = Department.objects.get_or_create(name="DEMO bo‘lim", parent=None)[0]
    school_dept = school_staff_department()
    made = 0
    for i, (last, first, middle, pos, school_idx) in enumerate(STAFF):
        institution = schools[school_idx] if school_idx is not None and school_idx < len(schools) else None
        if Employee.objects.filter(last_name=last, first_name=first).exists():
            continue
        emp = Employee.objects.create(
            last_name=last, first_name=first, middle_name=middle, department=school_dept if institution else dept, institution=institution,
            position=Position.objects.filter(name=pos).first(), status=Employee.Status.ACTIVE, work_phone=f"+998 00 000 {10 + i:02d} {20 + i:02d}",
            hired_at=datetime.date(2015 + i % 9, 1 + i % 12, 1 + i % 27),
        )
        emp.photo.save(new_storage_name("jpg"), ContentFile(art.portrait_jpeg(100 + i)), save=True)
        made += 1
    for k, emp in enumerate(Employee.objects.filter(user__isnull=False, photo="")):  # demo accounts get portraits too
        emp.photo.save(new_storage_name("jpg"), ContentFile(art.portrait_jpeg(200 + k)), save=True)
        made += 1
    return made


def _news(admin):
    cats = {name: NewsCategory.objects.get_or_create(slug=slug, defaults={"name": name})[0]
            for name, slug in (("Tadbirlar", "tadbirlar"), ("E’lonlar", "elonlar"), ("Yutuqlar", "yutuqlar"), ("Sport", "sport"), ("Metodika", "metodika"))}
    made = 0
    for slug, title, cat, excerpt, kind, seed, days, status in NEWS_ITEMS:
        if News.objects.filter(slug=slug).exists():
            continue
        news = News(slug=slug, title=title, excerpt=excerpt, body=NEWS_BODY.format(excerpt=excerpt), category=cats[cat], status=status,
                    publish_at=_now_minus(days) if status == "published" else None, author=admin)
        full, _thumb = art.scene_jpeg(kind, seed)
        news.cover.save(new_storage_name("jpg"), ContentFile(full), save=False)
        news.save()
        made += 1
    return made


def _achievements(admin, schools, directors):
    made = 0
    for title, kind, level, person_kind, name, position, school_idx, scene_kind, days, video_idx in ACHIEVEMENTS:
        institution = schools[min(school_idx, len(schools) - 1)]
        if Achievement.objects.filter(title=title).exists():
            continue
        a = Achievement.objects.create(
            institution=institution, created_by=directors[0] if institution == schools[0] else admin, kind=kind, title=title, person_kind=person_kind,
            person_name=name, person_position=position, level=level, awarded_on=timezone.localdate() - datetime.timedelta(days=days + 3),
            description=f"{name} {title.lower()} natijasiga erishdi. Bu yutuq muassasa va tuman uchun faxr. (Namunaviy ma’lumot, haqiqiy emas.)",
            consent_confirmed=True, status="published", publish_at=_now_minus(days),
        )
        pics = []
        if kind in ("certificate", "diploma", "medal", "award"):
            pics.append(art.certificate_jpeg(kind, title, name, LEVEL_LABEL[level], timezone.localdate().year, seed=days))
        pics.append(art.scene_jpeg(scene_kind, days)[0])
        for pos, data in enumerate(pics):
            img = AchievementImage(achievement=a, position=pos)
            img.file.save(new_storage_name("jpg"), ContentFile(data), save=False)
            img.save()
        if video_idx is not None:
            data = (ASSETS / VIDEOS[video_idx]).read_bytes()
            v = AchievementVideo(achievement=a, content_type="video/mp4", size=len(data), sha256=hashlib.sha256(data).hexdigest())
            v.file.save(new_storage_name("mp4"), ContentFile(data), save=False)
            v.save()
        made += 1
    # a few in other states, so the review queue and the school lists are not empty
    pending = [("Respublika tanlovi: ishtirokchi sertifikati (tekshiruvda)", "submitted", "certificate", "student", "Sodiqov Akmal", "10-sinf"),
               ("Viloyat ko‘rik-tanlovi (tekshiruvda)", "submitted", "diploma", "teacher", "Mirzayeva Dilfuza", "Biologiya o‘qituvchisi"),
               ("Tuman chempionati (tuzatish talab etiladi)", "changes_requested", "medal", "team", "2-maktab voleybol jamoasi", "Qizlar jamoasi"),
               ("Yangi yutuq (qoralama)", "draft", "other", "student", "Namunaviy O‘quvchi", "8-sinf")]
    for title, status, kind, pk, name, position in pending:
        if Achievement.objects.filter(title=title).exists():
            continue
        a = Achievement.objects.create(institution=schools[1] if "2-maktab" in name else schools[0], created_by=directors[0], title=title, kind=kind, person_kind=pk, person_name=name,
                                       person_position=position, level="district", description="Namunaviy yutuq (haqiqiy emas).", consent_confirmed=status != "draft", status=status)
        img = AchievementImage(achievement=a, position=0)
        img.file.save(new_storage_name("jpg"), ContentFile(art.certificate_jpeg(kind, title, name, "Tuman darajasi", timezone.localdate().year, seed=len(title))), save=False)
        img.save()
        made += 1
    return made


def _gallery(admin, schools):
    made = 0
    MediaItem.objects.filter(title__startswith="DEMO: Namunaviy rasm").delete()  # the plain coloured circles of the first version
    for scene_kind, seed, title, school_idx, days in GALLERY:
        t = f"{title}"
        if MediaItem.objects.filter(title=t).exists():
            continue
        full, thumb = art.scene_jpeg(scene_kind, seed)
        status = "published" if seed % 7 else "draft"
        item = MediaItem(kind="photo", title=t, institution=schools[school_idx] if school_idx is not None and school_idx < len(schools) else None,
                         taken_on=timezone.localdate() - datetime.timedelta(days=days), content_type="image/jpeg", size=len(full), sha256=hashlib.sha256(full).hexdigest(),
                         scan_status="not_scanned", consent_confirmed=True, status=status, publish_at=_now_minus(days) if status == "published" else None, uploaded_by=admin)
        item.file.save(new_storage_name("jpg"), ContentFile(full), save=False)
        item.thumb.save(new_storage_name("jpg"), ContentFile(thumb), save=False)
        item.save()
        made += 1
    for title, idx, school_idx, days, status in GALLERY_VIDEOS:
        if MediaItem.objects.filter(title=title, kind="video").exists():
            continue
        data = (ASSETS / VIDEOS[idx]).read_bytes()
        item = MediaItem(kind="video", title=title, institution=schools[school_idx] if school_idx is not None else None, taken_on=timezone.localdate() - datetime.timedelta(days=days),
                         content_type="video/mp4", size=len(data), sha256=hashlib.sha256(data).hexdigest(), scan_status="not_scanned", consent_confirmed=True, status=status,
                         publish_at=_now_minus(days) if status == "published" else None, uploaded_by=admin)
        item.file.save(new_storage_name("mp4"), ContentFile(data), save=False)
        item.save()
        made += 1
    return made


def _documents(admin):
    made = 0
    cats = {c.name: c for c in DocumentCategory.objects.all()}
    for cat, title, number, days, lines in DOCS:
        if Document.objects.filter(title=title).exists() or cat not in cats:
            continue
        doc = Document.objects.create(title=title, description=lines[0], number="" if number == "—" else number, category=cats[cat],
                                      doc_date=timezone.localdate() - datetime.timedelta(days=days), access_level=Document.Access.GENERAL, created_by=admin)
        data = art.pdf_bytes(title, lines + ["Ushbu hujjat demonstratsiya uchun yaratilgan."])
        add_version(doc, CheckedUpload(display_name=f"{title[:40]}.pdf", extension="pdf", kind="pdf", size=len(data), data=data), actor=admin, comment="Birinchi versiya")
        made += 1
    return made


def _tasks(admin, users, directors):
    if Task.objects.filter(title__startswith="DEMO: Qo‘shimcha").exists():
        return 0
    emp, head, hr = users["demo_employee"], users["demo_head"], users["demo_hr"]
    today = timezone.localdate()
    day = lambda n: today + datetime.timedelta(days=n)
    specs = [
        ("Metodik tavsiyalar bo‘yicha taqdimot tayyorlash", [emp], "in_progress", 4, None, "normal", "Taqdimot 10 slaydgacha bo‘lsin."),
        ("Maktablar kesimida o‘quvchilar sonini yig‘ish", [head], "new", 6, datetime.time(15, 0), "high", "Ma’lumot Excel jadvalida bo‘lsin."),
        ("Kadrlar hujjatlarini tekshirish", [hr], "review", 1, None, "normal", "Tekshiruvga topshirildi."),
        ("Olimpiada ishtirokchilari ro‘yxatini tasdiqlash", [directors[0], directors[1]], "in_progress", 3, datetime.time(12, 0), "urgent", "Ro‘yxat ertaga ertalabgacha kerak."),
        ("Sinf xonalarini qishga tayyorlash", [directors[1]], "new", 12, None, "low", ""),
        ("Bayramona tadbir rejasini yuborish", [directors[0]], "done", -3, None, "normal", "Reja qabul qilindi."),
        ("Yoz oromgohi bo‘yicha ma’lumot", [emp, head], "done", -9, None, "low", ""),
        ("Eskirgan hujjatlarni arxivlash", [emp], "cancelled", -5, None, "low", "Muddat kechiktirildi."),
    ]
    for title, who, status, due, time, priority, text in specs:
        t = Task.objects.create(title="DEMO: Qo‘shimcha — " + title, description=text or "Namunaviy topshiriq (haqiqiy emas).", created_by=admin, status=status, priority=priority,
                                due_date=day(due), due_time=time, closed_at=timezone.now() if status in ("done", "cancelled") else None)
        t.assignees.set(who)
        TaskComment.objects.create(task=t, author=admin, body="Iltimos, muddatga e’tibor bering va natijani shu yerga yozing.")
        if who and status in ("in_progress", "review", "done"):
            TaskComment.objects.create(task=t, author=who[0], body="Qabul qildim, ishni boshladim." if status == "in_progress" else "Ish bajarildi, natijani biriktirdim.")
        for u in who:
            Notification.objects.create(user=u, kind="task_assigned", title=t.title, task=t)
    return len(specs)


def _chat(users, directors):
    admin, emp, head = users["demo_admin"], users["demo_employee"], users["demo_head"]
    for u in (admin, emp, head, *directors):
        chat_services.accept_notice(u)
    made = 0
    scripts = [
        (directors[0], directors[1], [(0, "Assalomu alaykum! Ertangi yig‘ilish soat nechada boshlanadi?"), (1, "Salom. Soat 10:00 da, tuman bo‘limida."),
                                     (0, "Rahmat. Hisobotni olib kelaymi?"), (1, "Ha, chorak hisoboti bilan birga olib keling."), (0, "Tushunarli, kelamiz.")]),
        (admin, directors[0], [(0, "Olimpiada ro‘yxatini yubordingizmi?"), (1, "Ha, bugun ertalab yubordim. Tekshirib ko‘ring."), (0, "Ko‘rdim, rahmat. Bitta o‘quvchining sinfi yozilmagan.")]),
        (head, emp, [(0, "Taqdimot tayyormi?"), (1, "Deyarli, soat 15:00 gacha yuboraman."), (0, "Yaxshi, kutaman.")]),
    ]
    for a, b, lines in scripts:
        conv = chat_services.start(a, b)
        if conv.messages.exists():
            continue
        for i, (who, text) in enumerate(lines):
            msg = chat_services.send(a if who == 0 else b, conv, text)
            when = timezone.now() - datetime.timedelta(minutes=(len(lines) - i) * 7 + 20)
            type(msg).objects.filter(pk=msg.pk).update(created_at=when)
            type(conv).objects.filter(pk=conv.pk).update(last_message_at=when)
        made += 1
    return made


def _attendance(users, directors):
    zones = list(WorkZone.objects.filter(is_active=True))
    if not zones:
        return 0
    rng = random.Random(42)
    made = 0
    for user in (users["demo_employee"], users["demo_head"], users["demo_hr"], users["demo_content"], *directors):
        emp = Employee.objects.filter(user=user).first()
        if emp is None or AttendanceEvent.objects.filter(employee=emp, source="self").exists():
            continue
        AttendanceNoticeAcceptance.objects.get_or_create(user=user)
        zone = next((z for z in zones if z.institution_id and z.institution_id == emp.institution_id), None) or next((z for z in zones if z.institution_id is None), zones[0])
        for back in range(1, 9):
            day = timezone.localdate() - datetime.timedelta(days=back)
            if day.weekday() >= 5:
                continue
            start = timezone.make_aware(datetime.datetime.combine(day, datetime.time(8, 45))) + datetime.timedelta(minutes=rng.randint(0, 30))
            end = timezone.make_aware(datetime.datetime.combine(day, datetime.time(17, 40))) + datetime.timedelta(minutes=rng.randint(0, 40))
            outside = rng.random() < 0.12
            lat0, lon0 = float(zone.latitude), float(zone.longitude)
            def pos(far, lat0=lat0, lon0=lon0):
                k = 0.012 if far else 0.0006
                return f"{lat0 + rng.uniform(-k, k):.6f}", f"{lon0 + rng.uniform(-k, k):.6f}"
            la, lo = pos(outside)
            AttendanceEvent.objects.create(employee=emp, kind="in", at=start, zone=zone, latitude=la, longitude=lo, accuracy_m=rng.randint(8, 40), inside_zone=not outside,
                                           distance_m=900 if outside else 0, note="Tuman bo‘limiga chaqirilgan edim" if outside else "")
            la, lo = pos(False)
            AttendanceEvent.objects.create(employee=emp, kind="out", at=end, zone=zone, latitude=la, longitude=lo, accuracy_m=rng.randint(8, 40), inside_zone=True, distance_m=0)
            made += 2
    return made


def _notifications(users, directors):
    made = 0
    for ach in Achievement.objects.filter(status="published")[:3]:
        for u in directors:
            if not Notification.objects.filter(user=u, achievement=ach).exists():
                Notification.objects.create(user=u, kind="achievement_published", title=ach.title, achievement=ach)
                made += 1
    return made


def seed_rich(admin, users, schools, directors, stdout=None):
    """Add the large demo content. `schools` = the three base schools; the extra ones are created here."""
    extra = [Institution.objects.get_or_create(name=n, defaults={"kind": k, "head_name": h, "is_published": p})[0] for n, k, h, p in MORE_SCHOOLS]
    all_schools = list(schools) + extra
    counts = {
        "staff cards/portraits": _staff_cards(all_schools),
        "news": _news(admin),
        "achievements": _achievements(admin, all_schools, directors),
        "gallery items": _gallery(admin, all_schools),
        "documents": _documents(admin),
        "tasks": _tasks(admin, users, directors),
        "chats": _chat(users, directors),
        "attendance marks": _attendance(users, directors),
        "notifications": _notifications(users, directors),
    }
    if stdout is not None:
        stdout.write("Rich content added: " + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    return counts
