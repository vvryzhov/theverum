from datetime import datetime
from pathlib import Path
import secrets
import shutil
from fastapi import FastAPI, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from .config import settings
from .db import Base, engine, get_db, SessionLocal
from .models import User, AuthenticationCase, Certificate, AuditEvent, Role, Verdict, CertificateStatus, PriceBlock, TextPreset, ContactRequest
from .security import hash_password, verify_password, create_token, read_token
from .documents import make_certificate, make_report

app = FastAPI(title="The Verum", version="1.0.0")
Base.metadata.create_all(bind=engine)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

PHOTOS = Path("app/generated/photos")
PHOTOS.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".webp"}


def migrate():
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS photo_path VARCHAR(500) DEFAULT ''"))


def seed():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.email == settings.admin_email))
        if not admin:
            db.add(User(
                email=settings.admin_email,
                full_name="Администратор The Verum",
                password_hash=hash_password(settings.admin_password),
                role=Role.ADMIN.value,
            ))
            db.commit()
        if not db.scalar(select(AuthenticationCase).where(AuthenticationCase.case_number == "TV-C-000001")):
            case = AuthenticationCase(
                case_number="TV-C-000001",
                brand="CHANEL",
                model="Classic Flap Bag",
                category="Сумка",
                color="Черный",
                material="Кожа",
                serial_display="31••••••",
                identifier_mode="SERIAL",
                status="COMPLETED",
                verdict=Verdict.AUTHENTIC.value,
                conclusion="Подлинность изделия подтверждена по совокупности применимых признаков.",
                notable_features="Конструкция, материалы, маркировка и исполнение согласуются с заявленной моделью. Существенных противоречий не выявлено.",
            )
            db.add(case)
            db.commit()
            db.refresh(case)
            cert = Certificate(
                case_id=case.id,
                certificate_number="TVR-26-0000184",
                public_token="demo-certificate",
                status=CertificateStatus.ACTIVE.value,
            )
            db.add(cert)
            db.commit()
            db.refresh(cert)
            p, h = make_certificate(cert, case)
            cert.pdf_path = p
            cert.report_path = make_report(cert, case)
            cert.sha256 = h
            db.commit()
        if not db.scalar(select(PriceBlock).limit(1)):
            defaults = [
                PriceBlock(
                    title="Дистанционная проверка",
                    price_label="от 4 900 ₽",
                    description="Экспертиза по фотографиям и видеозаписи изделия. Подходит для большинства сумок, аксессуаров и обуви.",
                    features="Онлайн-заявка\nРазбор по 12–20 признакам\nЭлектронный сертификат\nПубличная страница статуса\nСрок 1–2 рабочих дня",
                    sort_order=1,
                ),
                PriceBlock(
                    title="Углубленная проверка",
                    price_label="от 9 900 ₽",
                    description="Расширенный анализ с запросом дополнительных ракурсов, маркировок и идентификаторов.",
                    features="Всё из базового тарифа\nДополнительные ракурсы и детали\nКомментарий по идентификаторам\nКраткий PDF-отчет\nСрок 2–3 рабочих дня",
                    sort_order=2,
                ),
                PriceBlock(
                    title="Очная экспертиза",
                    price_label="от 19 900 ₽",
                    description="Физический осмотр изделия экспертом. Рекомендуется для часов, украшений и спорных случаев.",
                    features="Осмотр вживую\nФотофиксация ключевых узлов\nСертификат и краткий отчет\nВозможность пересмотра дистанционного вывода\nСрок по записи",
                    sort_order=3,
                ),
            ]
            db.add_all(defaults)
            db.commit()
        if not db.scalar(select(TextPreset).limit(1)):
            preset_defaults = [
                TextPreset(
                    kind="conclusion",
                    title="Подлинность подтверждена",
                    body="По результатам проверки изделия {{brand}} {{model}} подлинность подтверждена. Конструкция, материалы, маркировка и исполнение согласуются с заявленной моделью и периодом выпуска. Существенных противоречий не выявлено.",
                    sort_order=1,
                ),
                TextPreset(
                    kind="conclusion",
                    title="Подлинность не подтверждена",
                    body="По результатам проверки изделия {{brand}} {{model}} подлинность не подтверждена. Выявлены признаки, которые не согласуются с эталонными характеристиками заявленной модели.",
                    sort_order=2,
                ),
                TextPreset(
                    kind="conclusion",
                    title="Недостаточно данных",
                    body="По представленным материалам для изделия {{brand}} {{model}} недостаточно данных для однозначного вывода. Требуются дополнительные ракурсы, маркировки или очный осмотр.",
                    sort_order=3,
                ),
                TextPreset(
                    kind="conclusion",
                    title="Требуется очная экспертиза",
                    body="Дистанционных материалов по изделию {{brand}} {{model}} недостаточно для финального заключения. Рекомендуется очная экспертиза с физическим осмотром ключевых узлов.",
                    sort_order=4,
                ),
                TextPreset(
                    kind="notable_features",
                    title="Стандартное обоснование (подлинно)",
                    body="Проверены общий вид, конструкция, материалы ({{material}}), цвет ({{color}}), фурнитура и маркировка. Идентификатор: {{serial}}. Признаки согласуются с моделью {{brand}} {{model}}. Отдельные идентификаторы оценивались только в контексте бренда и периода выпуска.",
                    sort_order=1,
                ),
                TextPreset(
                    kind="notable_features",
                    title="Стандартное обоснование (не подтверждено)",
                    body="При анализе {{category}} {{brand}} {{model}} выявлены несоответствия по одному или нескольким признакам: конструкция, материалы, маркировка или фурнитура. Идентификатор {{serial}} не снимает выявленных противоречий.",
                    sort_order=2,
                ),
                TextPreset(
                    kind="notable_features",
                    title="Недостаточно материалов",
                    body="Доступный комплект фото/видео по {{brand}} {{model}} не позволяет уверенно оценить скрытые узлы, маркировку и/или идентификаторы. Для завершения проверки нужны дополнительные материалы либо очный осмотр.",
                    sort_order=3,
                ),
                TextPreset(
                    kind="notable_features",
                    title="С акцентом на идентификатор",
                    body="Идентификатор {{serial}} рассмотрен в контексте модели {{brand}} {{model}}. Наличие или отсутствие номера/NFC/QR само по себе не является единственным критерием. Итоговый вывод сформирован по совокупности признаков: конструкция, материалы ({{material}}), маркировка и качество исполнения.",
                    sort_order=4,
                ),
            ]
            db.add_all(preset_defaults)
            db.commit()
    finally:
        db.close()


migrate()
seed()


def current_user(request: Request, db: Session):
    payload = read_token(request)
    if not payload:
        return None
    return db.scalar(select(User).where(User.email == payload.get("sub"), User.active == True))


def admin_required(request: Request, db: Session):
    user = current_user(request, db)
    if not user or user.role != Role.ADMIN.value:
        raise HTTPException(403, "Требуются права администратора")
    return user


async def save_photo(upload: UploadFile | None) -> str:
    if not upload or not upload.filename:
        return ""
    ext = Path(upload.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE:
        raise HTTPException(400, "Допустимы только JPG, PNG или WEBP")
    name = f"{secrets.token_hex(12)}{ext}"
    dest = PHOTOS / name
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return str(dest)


def regenerate_docs(cert: Certificate, case: AuthenticationCase) -> None:
    p, h = make_certificate(cert, case)
    cert.pdf_path = p
    cert.report_path = make_report(cert, case)
    cert.sha256 = h
    cert.version += 1


def parse_issued_at(value: str, fallback: datetime) -> datetime:
    raw = (value or "").strip()
    if not raw:
        return fallback
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise HTTPException(400, "Некорректная дата выдачи")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/process", response_class=HTMLResponse)
def process_page(request: Request):
    return templates.TemplateResponse("process.html", {"request": request})


@app.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request, db: Session = Depends(get_db)):
    blocks = db.scalars(
        select(PriceBlock).where(PriceBlock.active == True).order_by(PriceBlock.sort_order, PriceBlock.id)
    ).all()
    return templates.TemplateResponse("pricing.html", {"request": request, "blocks": blocks})


@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})


@app.get("/offer", response_class=HTMLResponse)
def offer_page(request: Request):
    return templates.TemplateResponse("offer.html", {"request": request})


@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request):
    return templates.TemplateResponse(
        "contact.html",
        {"request": request, "sent": request.query_params.get("sent") == "1"},
    )


@app.post("/contact")
def contact_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    topic: str = Form("consultation"),
    brand: str = Form(""),
    model: str = Form(""),
    message: str = Form(""),
    db: Session = Depends(get_db),
):
    name = name.strip()
    email = email.strip()
    phone = phone.strip()
    message = message.strip()
    if not name:
        raise HTTPException(400, "Укажите имя")
    if not email and not phone:
        raise HTTPException(400, "Укажите email или телефон")
    if topic not in {"consultation", "check", "pricing", "other"}:
        topic = "other"
    lead = ContactRequest(
        name=name[:160],
        email=email[:255],
        phone=phone[:80],
        topic=topic,
        brand=brand.strip()[:120],
        model=model.strip()[:160],
        message=message[:4000],
        status="NEW",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    db.add(
        AuditEvent(
            actor_email=email or phone or "public",
            action="CONTACT_REQUEST_CREATED",
            entity_type="contact_request",
            entity_id=str(lead.id),
        )
    )
    db.commit()
    return RedirectResponse("/contact?sent=1", 303)


@app.get("/verify", response_class=HTMLResponse)
def verify_form(request: Request):
    return templates.TemplateResponse("verify.html", {"request": request, "certificate": None})


@app.post("/verify", response_class=HTMLResponse)
def verify_post(request: Request, number: str = Form(...), db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.certificate_number == number.strip().upper()))
    return templates.TemplateResponse(
        "verify.html",
        {"request": request, "certificate": cert, "not_found": not bool(cert)},
    )


@app.get("/v/{token}", response_class=HTMLResponse)
def public_cert(token: str, request: Request, db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.public_token == token))
    if not cert:
        raise HTTPException(404, "Сертификат не найден")
    return templates.TemplateResponse(
        "certificate.html",
        {"request": request, "certificate": cert, "case": cert.case},
    )


@app.get("/v/{token}/photo")
def certificate_photo(token: str, db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.public_token == token))
    if not cert or not cert.case.photo_path or not Path(cert.case.photo_path).exists():
        raise HTTPException(404)
    return FileResponse(cert.case.photo_path)


@app.get("/v/{token}/certificate.pdf")
def certificate_pdf(token: str, db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.public_token == token))
    if not cert or not Path(cert.pdf_path).exists():
        raise HTTPException(404)
    return FileResponse(cert.pdf_path, media_type="application/pdf", filename=f"{cert.certificate_number}.pdf")


@app.get("/v/{token}/report.pdf")
def report_pdf(token: str, db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.public_token == token))
    if not cert or not Path(cert.report_path).exists():
        raise HTTPException(404)
    return FileResponse(cert.report_path, media_type="application/pdf", filename=f"{cert.certificate_number}_report.pdf")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse("/login?error=1", 303)
    r = RedirectResponse("/admin", 303)
    r.set_cookie(
        "theverum_session",
        create_token(user.email, user.role),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=43200,
    )
    return r


@app.get("/logout")
def logout():
    r = RedirectResponse("/", 303)
    r.delete_cookie("theverum_session")
    return r


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, db: Session = Depends(get_db)):
    user = admin_required(request, db)
    cases = db.scalars(select(AuthenticationCase).order_by(AuthenticationCase.id.desc())).all()
    certs = db.scalars(select(Certificate).order_by(Certificate.id.desc())).all()
    prices = db.scalars(select(PriceBlock).order_by(PriceBlock.sort_order, PriceBlock.id)).all()
    presets = db.scalars(select(TextPreset).order_by(TextPreset.kind, TextPreset.sort_order, TextPreset.id)).all()
    contacts = db.scalars(select(ContactRequest).order_by(ContactRequest.id.desc())).all()
    active_presets = [p for p in presets if p.active]
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "cases": cases,
            "certificates": certs,
            "prices": prices,
            "presets": presets,
            "contacts": contacts,
            "conclusion_presets": [p for p in active_presets if p.kind == "conclusion"],
            "feature_presets": [p for p in active_presets if p.kind == "notable_features"],
            "topic_labels": {
                "consultation": "Консультация",
                "check": "Заявка на проверку",
                "pricing": "Вопрос по ценам",
                "other": "Другое",
            },
        },
    )


@app.post("/admin/contacts/{contact_id}")
def update_contact(
    contact_id: int,
    request: Request,
    status: str = Form("NEW"),
    admin_note: str = Form(""),
    db: Session = Depends(get_db),
):
    user = admin_required(request, db)
    lead = db.get(ContactRequest, contact_id)
    if not lead:
        raise HTTPException(404)
    if status not in {"NEW", "IN_PROGRESS", "DONE", "SPAM"}:
        raise HTTPException(400, "Некорректный статус")
    lead.status = status
    lead.admin_note = admin_note.strip()
    db.add(
        AuditEvent(
            actor_email=user.email,
            action="CONTACT_REQUEST_UPDATED",
            entity_type="contact_request",
            entity_id=str(lead.id),
            payload={"status": status},
        )
    )
    db.commit()
    return RedirectResponse("/admin#contacts", 303)


@app.post("/admin/contacts/{contact_id}/delete")
def delete_contact(contact_id: int, request: Request, db: Session = Depends(get_db)):
    user = admin_required(request, db)
    lead = db.get(ContactRequest, contact_id)
    if not lead:
        raise HTTPException(404)
    db.delete(lead)
    db.add(
        AuditEvent(
            actor_email=user.email,
            action="CONTACT_REQUEST_DELETED",
            entity_type="contact_request",
            entity_id=str(contact_id),
        )
    )
    db.commit()
    return RedirectResponse("/admin#contacts", 303)


@app.post("/admin/cases")
async def create_case(
    request: Request,
    brand: str = Form(...),
    model: str = Form("Не указана"),
    category: str = Form("Сумка"),
    color: str = Form("Не указан"),
    material: str = Form("Не указан"),
    serial_display: str = Form("Не предусмотрен / не указан"),
    identifier_mode: str = Form("NONE"),
    identifier_notes: str = Form(""),
    verdict: str = Form("AUTHENTIC"),
    conclusion: str = Form(""),
    notable_features: str = Form(""),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    user = admin_required(request, db)
    number = f"TV-C-{db.query(AuthenticationCase).count() + 1:06d}"
    photo_path = await save_photo(photo)
    case = AuthenticationCase(
        case_number=number,
        brand=brand,
        model=model,
        category=category,
        color=color,
        material=material,
        serial_display=serial_display,
        identifier_mode=identifier_mode,
        identifier_notes=identifier_notes,
        status="COMPLETED",
        verdict=verdict,
        conclusion=conclusion,
        notable_features=notable_features,
        photo_path=photo_path,
        internal_evidence={"client_document": "minimal", "identifier_policy": "contextual"},
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    db.add(AuditEvent(actor_email=user.email, action="CASE_CREATED", entity_type="case", entity_id=str(case.id)))
    db.commit()
    return RedirectResponse("/admin", 303)


@app.post("/admin/cases/{case_id}/photo")
async def upload_case_photo(
    case_id: int,
    request: Request,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = admin_required(request, db)
    case = db.get(AuthenticationCase, case_id)
    if not case:
        raise HTTPException(404)
    case.photo_path = await save_photo(photo)
    cert = db.scalar(select(Certificate).where(Certificate.case_id == case.id))
    if cert:
        regenerate_docs(cert, case)
    db.add(AuditEvent(actor_email=user.email, action="CASE_PHOTO_UPDATED", entity_type="case", entity_id=str(case.id)))
    db.commit()
    return RedirectResponse("/admin", 303)


@app.get("/admin/certificates/{cert_id}/edit", response_class=HTMLResponse)
def edit_certificate_page(cert_id: int, request: Request, db: Session = Depends(get_db)):
    user = admin_required(request, db)
    cert = db.get(Certificate, cert_id)
    if not cert:
        raise HTTPException(404)
    presets = db.scalars(select(TextPreset).where(TextPreset.active == True).order_by(TextPreset.kind, TextPreset.sort_order, TextPreset.id)).all()
    return templates.TemplateResponse(
        "admin_edit_certificate.html",
        {
            "request": request,
            "user": user,
            "cert": cert,
            "case": cert.case,
            "conclusion_presets": [p for p in presets if p.kind == "conclusion"],
            "feature_presets": [p for p in presets if p.kind == "notable_features"],
            "issued_at_value": cert.issued_at.strftime("%Y-%m-%dT%H:%M"),
        },
    )


@app.post("/admin/certificates/{cert_id}/edit")
async def edit_certificate(
    cert_id: int,
    request: Request,
    certificate_number: str = Form(...),
    issued_at: str = Form(...),
    status: str = Form("ACTIVE"),
    revocation_reason: str = Form(""),
    brand: str = Form(...),
    model: str = Form("Не указана"),
    category: str = Form("Сумка"),
    color: str = Form("Не указан"),
    material: str = Form("Не указан"),
    serial_display: str = Form("Не предусмотрен / не указан"),
    identifier_mode: str = Form("NONE"),
    identifier_notes: str = Form(""),
    verdict: str = Form("AUTHENTIC"),
    conclusion: str = Form(""),
    notable_features: str = Form(""),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    user = admin_required(request, db)
    cert = db.get(Certificate, cert_id)
    if not cert:
        raise HTTPException(404)
    case = cert.case
    number = certificate_number.strip().upper()
    conflict = db.scalar(
        select(Certificate).where(Certificate.certificate_number == number, Certificate.id != cert.id)
    )
    if conflict:
        raise HTTPException(400, "Номер сертификата уже используется")
    if status not in {s.value for s in CertificateStatus}:
        raise HTTPException(400, "Некорректный статус")

    case.brand = brand.strip()
    case.model = model.strip() or "Не указана"
    case.category = category.strip() or "Сумка"
    case.color = color.strip() or "Не указан"
    case.material = material.strip() or "Не указан"
    case.serial_display = serial_display.strip() or "Не предусмотрен / не указан"
    case.identifier_mode = identifier_mode
    case.identifier_notes = identifier_notes.strip()
    case.verdict = verdict
    case.conclusion = conclusion.strip()
    case.notable_features = notable_features.strip()

    new_photo = await save_photo(photo)
    if new_photo:
        case.photo_path = new_photo

    cert.certificate_number = number
    cert.issued_at = parse_issued_at(issued_at, cert.issued_at)
    previous_status = cert.status
    cert.status = status
    if status == CertificateStatus.REVOKED.value:
        if previous_status != CertificateStatus.REVOKED.value or not cert.revoked_at:
            cert.revoked_at = datetime.utcnow()
        cert.revocation_reason = revocation_reason.strip() or cert.revocation_reason or "Пересмотр заключения"
    else:
        cert.revoked_at = None
        if status == CertificateStatus.ACTIVE.value:
            cert.revocation_reason = ""

    regenerate_docs(cert, case)
    db.add(
        AuditEvent(
            actor_email=user.email,
            action="CERTIFICATE_UPDATED",
            entity_type="certificate",
            entity_id=str(cert.id),
            payload={"certificate_number": cert.certificate_number, "status": cert.status},
        )
    )
    db.commit()
    return RedirectResponse(f"/admin/certificates/{cert.id}/edit?saved=1", 303)


@app.post("/admin/cases/{case_id}/issue")
def issue(case_id: int, request: Request, db: Session = Depends(get_db)):
    user = admin_required(request, db)
    case = db.get(AuthenticationCase, case_id)
    if not case:
        raise HTTPException(404)
    existing = db.scalar(select(Certificate).where(Certificate.case_id == case.id))
    if existing:
        return RedirectResponse(f"/admin/certificates/{existing.id}/edit", 303)
    cert = Certificate(
        case_id=case.id,
        certificate_number=f"TVR-{datetime.utcnow():%y}-{db.query(Certificate).count() + 185:07d}",
        public_token=secrets.token_urlsafe(18),
        status="ACTIVE",
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    p, h = make_certificate(cert, case)
    cert.pdf_path = p
    cert.report_path = make_report(cert, case)
    cert.sha256 = h
    db.add(AuditEvent(actor_email=user.email, action="CERTIFICATE_ISSUED", entity_type="certificate", entity_id=str(cert.id)))
    db.commit()
    return RedirectResponse(f"/admin/certificates/{cert.id}/edit", 303)


@app.post("/admin/certificates/{cert_id}/revoke")
def revoke(cert_id: int, request: Request, reason: str = Form("Пересмотр заключения"), db: Session = Depends(get_db)):
    user = admin_required(request, db)
    cert = db.get(Certificate, cert_id)
    if not cert:
        raise HTTPException(404)
    cert.status = "REVOKED"
    cert.revoked_at = datetime.utcnow()
    cert.revocation_reason = reason
    db.add(
        AuditEvent(
            actor_email=user.email,
            action="CERTIFICATE_REVOKED",
            entity_type="certificate",
            entity_id=str(cert.id),
            payload={"reason": reason},
        )
    )
    db.commit()
    return RedirectResponse("/admin", 303)


@app.post("/admin/prices")
def create_price(
    request: Request,
    title: str = Form(...),
    price_label: str = Form(...),
    description: str = Form(""),
    features: str = Form(""),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
):
    user = admin_required(request, db)
    block = PriceBlock(
        title=title.strip(),
        price_label=price_label.strip(),
        description=description.strip(),
        features=features.strip(),
        sort_order=sort_order,
        active=True,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    db.add(AuditEvent(actor_email=user.email, action="PRICE_CREATED", entity_type="price_block", entity_id=str(block.id)))
    db.commit()
    return RedirectResponse("/admin#prices", 303)


@app.post("/admin/prices/{price_id}")
def update_price(
    price_id: int,
    request: Request,
    title: str = Form(...),
    price_label: str = Form(...),
    description: str = Form(""),
    features: str = Form(""),
    sort_order: int = Form(0),
    active: str = Form("1"),
    db: Session = Depends(get_db),
):
    user = admin_required(request, db)
    block = db.get(PriceBlock, price_id)
    if not block:
        raise HTTPException(404)
    block.title = title.strip()
    block.price_label = price_label.strip()
    block.description = description.strip()
    block.features = features.strip()
    block.sort_order = sort_order
    block.active = active == "1"
    db.add(AuditEvent(actor_email=user.email, action="PRICE_UPDATED", entity_type="price_block", entity_id=str(block.id)))
    db.commit()
    return RedirectResponse("/admin#prices", 303)


@app.post("/admin/prices/{price_id}/delete")
def delete_price(price_id: int, request: Request, db: Session = Depends(get_db)):
    user = admin_required(request, db)
    block = db.get(PriceBlock, price_id)
    if not block:
        raise HTTPException(404)
    db.delete(block)
    db.add(AuditEvent(actor_email=user.email, action="PRICE_DELETED", entity_type="price_block", entity_id=str(price_id)))
    db.commit()
    return RedirectResponse("/admin#prices", 303)


@app.post("/admin/presets")
def create_preset(
    request: Request,
    kind: str = Form(...),
    title: str = Form(...),
    body: str = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
):
    user = admin_required(request, db)
    if kind not in {"conclusion", "notable_features"}:
        raise HTTPException(400, "Некорректный тип пресета")
    preset = TextPreset(kind=kind, title=title.strip(), body=body.strip(), sort_order=sort_order, active=True)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    db.add(AuditEvent(actor_email=user.email, action="PRESET_CREATED", entity_type="text_preset", entity_id=str(preset.id)))
    db.commit()
    return RedirectResponse("/admin#presets", 303)


@app.post("/admin/presets/{preset_id}")
def update_preset(
    preset_id: int,
    request: Request,
    kind: str = Form(...),
    title: str = Form(...),
    body: str = Form(...),
    sort_order: int = Form(0),
    active: str = Form("1"),
    db: Session = Depends(get_db),
):
    user = admin_required(request, db)
    preset = db.get(TextPreset, preset_id)
    if not preset:
        raise HTTPException(404)
    if kind not in {"conclusion", "notable_features"}:
        raise HTTPException(400, "Некорректный тип пресета")
    preset.kind = kind
    preset.title = title.strip()
    preset.body = body.strip()
    preset.sort_order = sort_order
    preset.active = active == "1"
    db.add(AuditEvent(actor_email=user.email, action="PRESET_UPDATED", entity_type="text_preset", entity_id=str(preset.id)))
    db.commit()
    return RedirectResponse("/admin#presets", 303)


@app.post("/admin/presets/{preset_id}/delete")
def delete_preset(preset_id: int, request: Request, db: Session = Depends(get_db)):
    user = admin_required(request, db)
    preset = db.get(TextPreset, preset_id)
    if not preset:
        raise HTTPException(404)
    db.delete(preset)
    db.add(AuditEvent(actor_email=user.email, action="PRESET_DELETED", entity_type="text_preset", entity_id=str(preset_id)))
    db.commit()
    return RedirectResponse("/admin#presets", 303)


@app.get("/api/certificates/{number}")
def api_certificate(number: str, db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.certificate_number == number.upper()))
    if not cert:
        raise HTTPException(404)
    return {
        "certificate_number": cert.certificate_number,
        "status": cert.status,
        "version": cert.version,
        "issued_at": cert.issued_at,
        "brand": cert.case.brand,
        "model": cert.case.model,
        "verdict": cert.case.verdict,
        "public_url": f"{settings.app_url}/v/{cert.public_token}",
        "has_photo": bool(cert.case.photo_path),
    }
