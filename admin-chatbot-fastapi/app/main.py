from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from app.database import Base, engine, get_db
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
    if db.query(models.User).count() == 0:
        db.add_all([
            models.User(name="Samantha Reyes", email="samantha@company.com",
                        phone="+923001234567", city="Lahore"),
            models.User(name="Ahsan Malik", email="ahsan.malik@company.com",
                        phone="+923214567890", city="Karachi"),
            models.User(name="Bushra Aziz", email="bushra@company.com",
                        phone="+923339876543", city="Islamabad"),
        ])
        db.commit()

    if db.query(models.AdminUser).count() == 0:
        # Default admin account for local/demo use only.
        # CHANGE THIS PASSWORD before using this anywhere but your own machine.
        db.add(models.AdminUser(
            email="admin@company.com",
            hashed_password=security.hash_password("ChangeMe123!"),
        ))
        db.commit()


@app.on_event("startup")
def on_startup():
    db = next(get_db())
    seed_if_empty(db)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))
# ---------- Auth dependency ----------


def get_current_admin(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> models.AdminUser:
    """Protects a route: requires 'Authorization: Bearer <token>'."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    token = authorization.removeprefix("Bearer ").strip()
    email = security.decode_access_token(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    admin = db.query(models.AdminUser).filter(models.AdminUser.email == email).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Admin account no longer exists.")
    return admin


# ---------- Public routes ----------

@app.post("/api/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    admin = db.query(models.AdminUser).filter(models.AdminUser.email == payload.email).first()
    if not admin or not security.verify_password(payload.password, admin.hashed_password):
        return schemas.LoginResponse(success=False, message="Invalid email or password.")
    token = security.create_access_token(admin.email)
    return schemas.LoginResponse(
        success=True, message="Signed in.", access_token=token, admin_email=admin.email
    )


# ---------- Protected routes (require a valid admin token) ----------

@app.get("/api/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), admin: models.AdminUser = Depends(get_current_admin)):
    return db.query(models.User).order_by(models.User.id).all()


@app.post("/api/chat", response_model=schemas.ChatResponse)
def chat(
    payload: schemas.ChatRequest,
    db: Session = Depends(get_db),
    admin: models.AdminUser = Depends(get_current_admin),
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
def audit_log(db: Session = Depends(get_db), admin: models.AdminUser = Depends(get_current_admin)):
    entries = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.id.desc())
        .limit(100)
        .all()
    )
    return [
        schemas.AuditEntryOut(
            id=e.id, actor_email=e.actor_email, message=e.message,
            success=bool(e.success), result=e.result, created_at=e.created_at,
        )
        for e in entries
    ]


