from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.database import Base, engine, get_db, SessionLocal
import app.models as models
import app.schemas as schemas
import app.nlu as nlu
import app.security as security

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Directory Admin Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def seed_if_empty(db: Session):
    if not db.query(models.User).filter_by(email="samantha@company.com").first():
        db.add(models.User(name="Samantha Reyes", email="samantha@company.com", phone="+923001234567", city="Lahore"))
    if not db.query(models.User).filter_by(email="ahsan.malik@company.com").first():
        db.add(models.User(name="Ahsan Malik", email="ahsan.malik@company.com", phone="+923214567890", city="Karachi"))
    if not db.query(models.User).filter_by(email="bushra@company.com").first():
        db.add(models.User(name="Bushra Aziz", email="bushra@company.com", phone="+923339876543", city="Islamabad"))
    db.commit()

@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()

# ---------- Auth dependency ---------- #

def get_current_admin(authorization: str = Header(None), db: Session = Depends(get_db)) -> models.User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token header")
    token = authorization.split(" ")[1]
    payload = security.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    admin = db.query(models.User).filter_by(email=payload.get("sub")).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Admin user not found")
    return admin

# ---------- Auth endpoints ---------- #

@app.post("/api/login")
def login(payload: dict, db: Session = Depends(get_db)):
    email = payload.get("email", "").strip()
    if not email:
        return {"success": False, "message": "Email is required"}
    user = db.query(models.User).filter_by(email=email).first()
    if not user:
        return {"success": False, "message": f"No account found for '{email}'. Check spelling or use a seeded email."}
    token = security.create_token(email)
    return {
        "success": True,
        "access_token": token,
        "admin_email": user.email,
        "admin_name": user.name
    }

# ---------- Data endpoints ---------- #

@app.get("/api/users")
def list_users(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [schemas.UserOut.from_orm(u) for u in users]

@app.get("/api/audit-log")
def list_audit_logs(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    logs = db.query(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(50).all()
    return [schemas.AuditLogOut.from_orm(l) for l in logs]

# ---------- Chat / NLU endpoint ---------- #

@app.post("/api/chat")
def chat(payload: dict, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    msg = payload.get("message", "")
    success, reply = nlu.handle_command(db, msg)
    
    log = models.AuditLog(actor_email=admin.email, message=msg, success=success, result=reply)
    db.add(log)
    db.commit()

    return {"reply": reply, "success": success}

# ---------- Static Frontend ---------- #

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("app/static/index.html")
