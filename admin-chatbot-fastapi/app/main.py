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
    if db.query(models.User).count() == 0:
        db.add_all([
            models.User(name="Samantha Reyes", email="samantha@company.com", phone="+923001234567", city="Lahore"),
            models.User(name="Ahsan Malik", email="ahsan.malik@company.com", phone="+923214567890", city="Karachi"),
            models.User(name="Bushra Aziz", email="bushra@company.com", phone="+923339876543", city="Islamabad"),
        ])
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
    intent, entities = nlu.parse_command(msg)
    
    if intent == "UNKNOWN":
        log = models.AuditLog(actor_email=admin.email, message=msg, success=False, result="Could not parse command intent")
        db.add(log)
        db.commit()
        return {"reply": "I couldn't understand that command. Try asking to add, update, or remove a user.", "success": False}

    success = False
    reply = ""

    if intent == "ADD_USER":
        email = entities.get("email")
        if not email:
            reply = "Please specify an email address for the user."
        elif db.query(models.User).filter_by(email=email).first():
            reply = f"User with email '{email}' already exists."
        else:
            name = entities.get("name") or email.split("@")[0].replace(".", " ").title()
            new_user = models.User(name=name, email=email, phone=entities.get("phone"), city=entities.get("city"))
            db.add(new_user)
            db.commit()
            success = True
            reply = f"Added user {name} ({email})."

    elif intent == "REMOVE_USER":
        email = entities.get("email")
        if not email:
            reply = "Please specify the email address of the user to remove."
        else:
            target = db.query(models.User).filter_by(email=email).first()
            if not target:
                reply = f"User with email '{email}' not found."
            else:
                db.delete(target)
                db.commit()
                success = True
                reply = f"Removed user {email}."

    elif intent == "UPDATE_USER":
        email = entities.get("email")
        if not email:
            reply = "Please specify the email of the user to update."
        else:
            target = db.query(models.User).filter_by(email=email).first()
            if not target:
                reply = f"User with email '{email}' not found."
            else:
                updated_fields = []
                if "city" in entities:
                    target.city = entities["city"]
                    updated_fields.append(f"city to {entities['city']}")
                if "phone" in entities:
                    target.phone = entities["phone"]
                    updated_fields.append(f"phone to {entities['phone']}")
                if "name" in entities:
                    target.name = entities["name"]
                    updated_fields.append(f"name to {entities['name']}")
                
                if updated_fields:
                    db.commit()
                    success = True
                    reply = f"Updated {target.email}: {', '.join(updated_fields)}."
                else:
                    reply = "No valid fields provided to update."

    log = models.AuditLog(actor_email=admin.email, message=msg, success=success, result=reply)
    db.add(log)
    db.commit()

    return {"reply": reply, "success": success}

# ---------- Static Frontend ---------- #

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("app/static/index.html")
