from pathlib import Path
from hashlib import sha256
from io import BytesIO
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from .config import settings

OUT = Path(__file__).parent / "generated"
OUT.mkdir(exist_ok=True)
FONT = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
FONT_B = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
try:
    pdfmetrics.registerFont(TTFont("Noto", FONT)); pdfmetrics.registerFont(TTFont("NotoB", FONT_B))
except Exception:
    pass

def _qr(url: str):
    img = qrcode.make(url)
    buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return ImageReader(buf)

def _verdict_text(v):
    return {"AUTHENTIC":"ПОДЛИННОСТЬ ПОДТВЕРЖДЕНА", "NOT_AUTHENTIC":"ПОДЛИННОСТЬ НЕ ПОДТВЕРЖДЕНА", "INCONCLUSIVE":"НЕДОСТАТОЧНО ДАННЫХ", "PHYSICAL_REVIEW":"ТРЕБУЕТСЯ ОЧНАЯ ЭКСПЕРТИЗА"}.get(v, "ЗАКЛЮЧЕНИЕ НЕ ВЫПУЩЕНО")

def make_certificate(cert, case):
    path = OUT / f"{cert.certificate_number}_certificate.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    w,h=A4
    c.setStrokeColor(colors.HexColor('#b79a57')); c.setLineWidth(1); c.rect(24,24,w-48,h-48)
    c.setFont("NotoB", 22); c.drawCentredString(w/2,h-78,"THE VERUM")
    c.setFont("Noto", 8); c.drawCentredString(w/2,h-96,"НЕЗАВИСИМАЯ ЭКСПЕРТИЗА ПРЕДМЕТОВ РОСКОШИ")
    c.setFont("NotoB", 24); c.drawCentredString(w/2,h-155,"СЕРТИФИКАТ ПОДЛИННОСТИ")
    c.setFont("Noto", 11); c.setFillColor(colors.HexColor('#8a6c2d')); c.drawCentredString(w/2,h-178,cert.certificate_number)
    c.setFillColor(colors.black)
    photo = getattr(case, "photo_path", "") or ""
    left = 72
    if photo and Path(photo).exists():
        try:
            c.drawImage(photo, w-210, h-360, width=130, height=160, preserveAspectRatio=True, mask='auto')
            left = 72
        except Exception:
            photo = ""
    y=h-235
    fields=[("Бренд",case.brand),("Модель",case.model),("Категория",case.category),("Цвет",case.color),("Материал",case.material),("Идентификатор",case.serial_display),("Дата проверки",cert.issued_at.strftime('%d.%m.%Y'))]
    for label,val in fields:
        c.setFont("NotoB",8); c.drawString(left,y,label.upper())
        c.setFont("Noto",10); c.drawString(left+133,y,str(val)[:40 if photo else 48]); c.setStrokeColor(colors.HexColor('#ded9ce')); c.line(left,y-7,(w-220 if photo else w-72),y-7); y-=34
    verdict=_verdict_text(case.verdict)
    c.setFillColor(colors.HexColor('#176b39') if case.verdict=='AUTHENTIC' else colors.HexColor('#8b2e2e'))
    c.roundRect(55,210,w-110,76,8,stroke=1,fill=0)
    c.setFont("NotoB",18); c.drawCentredString(w/2,252,verdict)
    c.setFont("Noto",9); c.drawCentredString(w/2,232,"Результат независимой экспертной проверки The Verum")
    url=f"{settings.app_url}/v/{cert.public_token}"
    c.drawImage(_qr(url),65,70,90,90)
    c.setFillColor(colors.black); c.setFont("NotoB",8); c.drawString(168,135,"ПРОВЕРИТЬ СЕРТИФИКАТ")
    c.setFont("Noto",8); c.drawString(168,118,url[:70])
    c.setFont("Noto",7); c.setFillColor(colors.HexColor('#666666'))
    c.drawCentredString(w/2,42,"Документ отражает независимое экспертное мнение на дату проверки и не является сертификатом производителя.")
    c.save()
    data=path.read_bytes(); return str(path), sha256(data).hexdigest()

def make_report(cert, case):
    path=OUT/f"{cert.certificate_number}_report.pdf"
    c=canvas.Canvas(str(path),pagesize=A4); w,h=A4
    def header(page):
        c.setFont("NotoB",14); c.drawString(45,h-48,"THE VERUM")
        c.setFont("NotoB",14); c.drawString(45,h-82,"ОТЧЕТ ОБ ЭКСПЕРТИЗЕ")
        c.setFont("Noto",8); c.drawRightString(w-45,h-48,f"{cert.certificate_number}  •  стр. {page}")
        c.setStrokeColor(colors.HexColor('#d9d4ca')); c.line(45,h-92,w-45,h-92)
    header(1); y=h-125
    c.setFont("NotoB",11); c.drawString(45,y,"1. ИЗДЕЛИЕ"); y-=28
    for label,val in [("Бренд",case.brand),("Модель",case.model),("Категория",case.category),("Цвет",case.color),("Материал",case.material),("Идентификатор",case.serial_display)]:
        c.setFont("NotoB",8); c.drawString(55,y,label.upper()); c.setFont("Noto",10); c.drawString(190,y,str(val)[:55]); y-=24
    y-=18; c.setFont("NotoB",11); c.drawString(45,y,"2. РЕЗУЛЬТАТ"); y-=40
    c.setFillColor(colors.HexColor('#176b39') if case.verdict=='AUTHENTIC' else colors.HexColor('#8b2e2e')); c.setFont("NotoB",19); c.drawString(55,y,_verdict_text(case.verdict)); y-=32
    c.setFillColor(colors.black); c.setFont("Noto",10)
    conclusion=case.conclusion or "По результатам анализа представленных материалов существенных признаков, противоречащих указанному выводу, не выявлено."
    for line in _wrap(conclusion,88): c.drawString(55,y,line); y-=16
    y-=20; c.setFont("NotoB",11); c.drawString(45,y,"3. КРАТКОЕ ОБОСНОВАНИЕ"); y-=30
    evidence=case.notable_features or "Исследование выполнено по совокупности применимых признаков. Отдельный серийный номер, NFC-метка или их отсутствие не рассматриваются изолированно от модели и периода выпуска."
    c.setFont("Noto",10)
    for line in _wrap(evidence,88): c.drawString(55,y,line); y-=16
    y-=24; c.setFillColor(colors.HexColor('#f5f2ec')); c.roundRect(45,y-105,w-90,105,7,stroke=0,fill=1)
    c.setFillColor(colors.black); c.setFont("NotoB",9); c.drawString(60,y-24,"ВАЖНО")
    c.setFont("Noto",8)
    note="Отчет относится только к описанному изделию и материалам, доступным на дату проверки. При появлении новых сведений заключение может быть пересмотрено; актуальный статус доступен по QR-коду."
    yy=y-44
    for line in _wrap(note,100): c.drawString(60,yy,line); yy-=14
    c.showPage(); header(2); y=h-128
    c.setFont("NotoB",11); c.drawString(45,y,"4. ИДЕНТИФИКАТОРЫ И ОСОБЕННОСТИ"); y-=32
    c.setFont("Noto",10)
    ident = case.identifier_notes or "Для данной модели идентификатор может отсутствовать либо отличаться в зависимости от периода выпуска. Вывод не основан на одном номере или NFC-метке."
    for line in _wrap(ident,90): c.drawString(55,y,line); y-=16
    y-=24; c.setFont("NotoB",11); c.drawString(45,y,"5. МАТЕРИАЛЫ ПРОВЕРКИ"); y-=30
    c.setFont("Noto",10)
    for text in ["Общий вид изделия", "Маркировка и логотипы", "Конструкция и материалы", "Идентификаторы - при наличии"]:
        c.circle(60,y+3,3,stroke=1,fill=0); c.drawString(75,y,text); y-=25
    y-=20; c.setFont("NotoB",11); c.drawString(45,y,"6. СТАТУС ДОКУМЕНТА"); y-=35
    c.setFont("NotoB",14); c.setFillColor(colors.HexColor('#176b39')); c.drawString(55,y,"ДЕЙСТВИТЕЛЕН" if cert.status=='ACTIVE' else cert.status)
    c.setFillColor(colors.black); y-=28; c.setFont("Noto",9); c.drawString(55,y,f"Дата выдачи: {cert.issued_at.strftime('%d.%m.%Y %H:%M')}")
    c.drawString(55,y-18,f"Версия: {cert.version}")
    url=f"{settings.app_url}/v/{cert.public_token}"; c.drawImage(_qr(url),55,90,105,105)
    c.setFont("Noto",8); c.drawString(180,160,"Актуальный статус и PDF доступны на публичной странице:")
    c.drawString(180,142,url[:70])
    c.save(); return str(path)

def _wrap(text, width):
    words=text.replace('\n',' ').split(); lines=[]; cur=[]
    for word in words:
        if len(' '.join(cur+[word]))>width:
            lines.append(' '.join(cur)); cur=[word]
        else: cur.append(word)
    if cur: lines.append(' '.join(cur))
    return lines
