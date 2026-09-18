from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.database import Base, engine, get_db
import app.models as models
import app.schemas as schemas
import app.nlu as nlu
import app.security as security

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Directory Admin Chatbot")
from app.database import SessionLocal
db = SessionLocal()
if not db.query(models.User).filter_by(email="samantha@company.com").first():
    db.add(models.User(name="Samantha Reyes", email="samantha@company.com", phone="+923001234567", city="Lahore"))
    db.commit()
db.close()

models.Base.metadata.create_all(bind=engine)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def seed_if_empty(db: Session):
    if db.query(models.User).count() == 0:
        db.add_all([
            models.User(name="Samantha Reyes", email="samantha@company.com", phone="+923001234567", city="Lahore"),
            models.User(name="Ahsan Malik", email="ahsan.malik@company.com", phone="+923214567890", city="Karachi"),
            models.User(name="Bushra Aziz", email="bushra@company.com", phone="+923339876543", city="Islamabad"),
        ])
        db.commit()

@app.on_event("startup")
def on_startup():
    db = next(get_db())
    seed_if_empty(db)

# ---------- Auth dependency ---------- #
def get_current_admin(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    token = authorization.removeprefix("Bearer ").strip()
    email = security.decode_access_token(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists in the directory.")
    return user

# ---------- Public routes ----------
@app.post("/api/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Auto login: succeeds only if the email already exists in the directory."""
    user = db.query(models.User).filter(models.User.email.ilike(payload.email)).first()
    if not user:
        return schemas.LoginResponse(
            success=False,
            message=f'No user found with "{payload.email}". Ask an admin to add you first.',
        )
    token = security.create_access_token(user.email)
    return schemas.LoginResponse(
        success=True,
        message="Signed in.",
        access_token=token,
        admin_email=user.email
    )

# ---------- Protected routes ----------
@app.get("/api/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), admin: models.User = Depends(get_current_admin)):
    return db.query(models.User).order_by(models.User.id).all()

@app.post("/api/chat", response_model=schemas.ChatResponse)
def chat(
    payload: schemas.ChatRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    
    success, reply = nlu.handle_command(db, payload.message)
    
    db.add(models.AuditLog(
        actor_email=admin.email,
        message=payload.message,
        success=1 if success else 0,
        result=reply,
    ))
    db.commit()
    return schemas.ChatResponse(success=success, reply=reply)

@app.get("/api/audit-log", response_model=list[schemas.AuditEntryOut])
def audit_log(db: Session = Depends(get_db), admin: models.User = Depends(get_current_admin)):
    entries = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.id.desc())
        .limit(100)
        .all()
    )
    return [
        schemas.AuditEntryOut(
            id=e.id,
            actor_email=e.actor_email,
            message=e.message,
            success=bool(e.success),
            result=e.result,
            created_at=e.created_at,
        )
        for e in entries
    ]

# ---------- Frontend ----------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("app/static/index.html")
