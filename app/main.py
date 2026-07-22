from datetime import datetime
from pathlib import Path
import secrets
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from .config import settings
from .db import Base, engine, get_db, SessionLocal
from .models import User, AuthenticationCase, Certificate, AuditEvent, Role, Verdict, CertificateStatus
from .security import hash_password, verify_password, create_token, read_token
from .documents import make_certificate, make_report

app=FastAPI(title="TheVerum", version="1.0.0")
Base.metadata.create_all(bind=engine)
templates=Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def seed():
    db=SessionLocal()
    try:
        admin=db.scalar(select(User).where(User.email==settings.admin_email))
        if not admin:
            db.add(User(email=settings.admin_email,full_name="Администратор TheVerum",password_hash=hash_password(settings.admin_password),role=Role.ADMIN.value))
            db.commit()
        if not db.scalar(select(AuthenticationCase).where(AuthenticationCase.case_number=="TV-C-000001")):
            case=AuthenticationCase(case_number="TV-C-000001",brand="CHANEL",model="Classic Flap Bag",category="Сумка",color="Черный",material="Кожа",serial_display="31••••••",identifier_mode="SERIAL",status="COMPLETED",verdict=Verdict.AUTHENTIC.value,conclusion="Подлинность изделия подтверждена по совокупности применимых признаков.",notable_features="Конструкция, материалы, маркировка и исполнение согласуются с заявленной моделью. Существенных противоречий не выявлено.")
            db.add(case); db.commit(); db.refresh(case)
            cert=Certificate(case_id=case.id,certificate_number="TVR-26-0000184",public_token="demo-certificate",status=CertificateStatus.ACTIVE.value)
            db.add(cert); db.commit(); db.refresh(cert)
            p,h=make_certificate(cert,case); cert.pdf_path=p; cert.report_path=make_report(cert,case); cert.sha256=h; db.commit()
    finally: db.close()
seed()

def current_user(request: Request, db: Session):
    payload=read_token(request)
    if not payload: return None
    return db.scalar(select(User).where(User.email==payload.get("sub"),User.active==True))

def admin_required(request: Request, db: Session):
    user=current_user(request,db)
    if not user or user.role!=Role.ADMIN.value: raise HTTPException(403,"Требуются права администратора")
    return user

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/",response_class=HTMLResponse)
def home(request:Request): return templates.TemplateResponse("home.html",{"request":request})

@app.get("/verify",response_class=HTMLResponse)
def verify_form(request:Request): return templates.TemplateResponse("verify.html",{"request":request,"certificate":None})

@app.post("/verify",response_class=HTMLResponse)
def verify_post(request:Request,number:str=Form(...),db:Session=Depends(get_db)):
    cert=db.scalar(select(Certificate).where(Certificate.certificate_number==number.strip().upper()))
    return templates.TemplateResponse("verify.html",{"request":request,"certificate":cert,"not_found":not bool(cert)})

@app.get("/v/{token}",response_class=HTMLResponse)
def public_cert(token:str,request:Request,db:Session=Depends(get_db)):
    cert=db.scalar(select(Certificate).where(Certificate.public_token==token))
    if not cert: raise HTTPException(404,"Сертификат не найден")
    return templates.TemplateResponse("certificate.html",{"request":request,"certificate":cert,"case":cert.case})

@app.get("/v/{token}/certificate.pdf")
def certificate_pdf(token:str,db:Session=Depends(get_db)):
    cert=db.scalar(select(Certificate).where(Certificate.public_token==token));
    if not cert or not Path(cert.pdf_path).exists(): raise HTTPException(404)
    return FileResponse(cert.pdf_path,media_type="application/pdf",filename=f"{cert.certificate_number}.pdf")

@app.get("/v/{token}/report.pdf")
def report_pdf(token:str,db:Session=Depends(get_db)):
    cert=db.scalar(select(Certificate).where(Certificate.public_token==token));
    if not cert or not Path(cert.report_path).exists(): raise HTTPException(404)
    return FileResponse(cert.report_path,media_type="application/pdf",filename=f"{cert.certificate_number}_report.pdf")

@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request): return templates.TemplateResponse("login.html",{"request":request})

@app.post("/login")
def login(email:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==email.strip().lower()))
    if not user or not verify_password(password,user.password_hash):
        return RedirectResponse('/login?error=1',303)
    r=RedirectResponse('/admin',303); r.set_cookie('theverum_session',create_token(user.email,user.role),httponly=True,samesite='lax',secure=settings.cookie_secure,max_age=43200); return r

@app.get("/logout")
def logout():
    r=RedirectResponse('/',303); r.delete_cookie('theverum_session'); return r

@app.get("/admin",response_class=HTMLResponse)
def admin(request:Request,db:Session=Depends(get_db)):
    user=admin_required(request,db); cases=db.scalars(select(AuthenticationCase).order_by(AuthenticationCase.id.desc())).all(); certs=db.scalars(select(Certificate).order_by(Certificate.id.desc())).all()
    return templates.TemplateResponse("admin.html",{"request":request,"user":user,"cases":cases,"certificates":certs})

@app.post("/admin/cases")
def create_case(request:Request,brand:str=Form(...),model:str=Form("Не указана"),category:str=Form("Сумка"),color:str=Form("Не указан"),material:str=Form("Не указан"),serial_display:str=Form("Не предусмотрен / не указан"),identifier_mode:str=Form("NONE"),identifier_notes:str=Form(""),verdict:str=Form("AUTHENTIC"),conclusion:str=Form(""),notable_features:str=Form(""),db:Session=Depends(get_db)):
    user=admin_required(request,db); number=f"TV-C-{db.query(AuthenticationCase).count()+1:06d}"
    case=AuthenticationCase(case_number=number,brand=brand,model=model,category=category,color=color,material=material,serial_display=serial_display,identifier_mode=identifier_mode,identifier_notes=identifier_notes,status="COMPLETED",verdict=verdict,conclusion=conclusion,notable_features=notable_features,internal_evidence={"client_document":"minimal","identifier_policy":"contextual"})
    db.add(case); db.commit(); db.refresh(case); db.add(AuditEvent(actor_email=user.email,action="CASE_CREATED",entity_type="case",entity_id=str(case.id))); db.commit(); return RedirectResponse('/admin',303)

@app.post("/admin/cases/{case_id}/issue")
def issue(case_id:int,request:Request,db:Session=Depends(get_db)):
    user=admin_required(request,db); case=db.get(AuthenticationCase,case_id)
    if not case: raise HTTPException(404)
    existing=db.scalar(select(Certificate).where(Certificate.case_id==case.id))
    if existing: return RedirectResponse(f'/v/{existing.public_token}',303)
    cert=Certificate(case_id=case.id,certificate_number=f"TVR-{datetime.utcnow():%y}-{db.query(Certificate).count()+185:07d}",public_token=secrets.token_urlsafe(18),status="ACTIVE")
    db.add(cert); db.commit(); db.refresh(cert); p,h=make_certificate(cert,case); cert.pdf_path=p; cert.report_path=make_report(cert,case); cert.sha256=h; db.add(AuditEvent(actor_email=user.email,action="CERTIFICATE_ISSUED",entity_type="certificate",entity_id=str(cert.id))); db.commit(); return RedirectResponse(f'/v/{cert.public_token}',303)

@app.post("/admin/certificates/{cert_id}/revoke")
def revoke(cert_id:int,request:Request,reason:str=Form("Пересмотр заключения"),db:Session=Depends(get_db)):
    user=admin_required(request,db); cert=db.get(Certificate,cert_id)
    if not cert: raise HTTPException(404)
    cert.status="REVOKED"; cert.revoked_at=datetime.utcnow(); cert.revocation_reason=reason; db.add(AuditEvent(actor_email=user.email,action="CERTIFICATE_REVOKED",entity_type="certificate",entity_id=str(cert.id),payload={"reason":reason})); db.commit(); return RedirectResponse('/admin',303)

@app.get("/api/certificates/{number}")
def api_certificate(number:str,db:Session=Depends(get_db)):
    cert=db.scalar(select(Certificate).where(Certificate.certificate_number==number.upper()))
    if not cert: raise HTTPException(404)
    return {"certificate_number":cert.certificate_number,"status":cert.status,"version":cert.version,"issued_at":cert.issued_at,"brand":cert.case.brand,"model":cert.case.model,"verdict":cert.case.verdict,"public_url":f"{settings.app_url}/v/{cert.public_token}"}
