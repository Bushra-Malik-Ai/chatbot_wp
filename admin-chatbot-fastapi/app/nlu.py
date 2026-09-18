"""
Rule-based command parser.

Deliberately NOT an LLM call: for a data-mutation tool you want deterministic,
testable behaviour — same input always produces the same action. This is also
a cheap, dependency-free layer you'd keep as a validator/fallback even after
adding an LLM-based parser for more flexible phrasing (see README).

Each function returns (success: bool, message: str). All DB writes happen here.
"""
import re
from sqlalchemy.orm import Session
from app.models import User

ALLOWED_FIELDS = {"city", "phone", "name", "email"}


def name_from_email(email: str) -> str:
    local = email.split("@")[0]
    parts = re.split(r"[._-]+", local)
    return " ".join(p.capitalize() for p in parts if p)


def find_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email.ilike(email)).first()


def find_by_first_name(db: Session, name: str):
    return (
        db.query(models.User)
        .filter(models.User.name.ilike(f"{name}%"))
        .first()
    )


def handle_command(db: Session, text: str) -> tuple[bool, str]:
    t = text.strip()

    # ADD with phone: add the user "email" ... phone number "value"
    m = re.search(
        r'add\s+(?:the\s+)?user\s+"?([^\s",]+@[^\s",]+)"?.*?phone\s*(?:number)?\s*"?([+\d][\d\s-]*)"?',
        t, re.IGNORECASE,
    )
    if m:
        email, phone = m.group(1).strip(), m.group(2).strip()
        if find_by_email(db, email):
            return False, f'A user with email "{email}" already exists.'
        user = models.User(name=name_from_email(email), email=email, phone=phone, city="")
        db.add(user)
        db.commit()
        return True, f'Added "{email}" with phone "{phone}".'

    # ADD, email only
    m = re.search(r'add\s+(?:the\s+)?user\s+"?([^\s",]+@[^\s",]+)"?', t, re.IGNORECASE)
    if m:
        email = m.group(1).strip()
        if find_by_email(db, email):
            return False, f'A user with email "{email}" already exists.'
        user = models.User(name=name_from_email(email), email=email, phone="", city="")
        db.add(user)
        db.commit()
        return True, f'Added "{email}".'

    # REMOVE / DELETE
    m = re.search(
        r'(?:remove|delete)\s+(?:the\s+)?user\s+"?([^\s",]+@[^\s",]+)"?',
        t, re.IGNORECASE,
    )
    if m:
        email = m.group(1).strip()
        user = find_by_email(db, email)
        if not user:
            return False, f'No user found with email "{email}".'
        db.delete(user)
        db.commit()
        return True, f'Removed "{email}" from the directory.'

    # UPDATE by first name: update NAMEs FIELD to VALUE
    m = re.search(r"update\s+([a-zA-Z]+)'?s\s+(\w+)\s+to\s+(.+?)[.\s]*$", t, re.IGNORECASE)
    if m:
        name, field, value = m.group(1).strip(), m.group(2).strip().lower(), m.group(3).strip()
        user = find_by_first_name(db, name)
        if not user:
            return False, f'No user found matching the name "{name}".'
        if field not in ALLOWED_FIELDS:
            return False, f'I can update name, email, phone, or city — not "{field}".'
        setattr(user, field, value)
        db.commit()
        return True, f"Updated {user.name}'s {field} to \"{value}\"."

    # UPDATE by email: update the user "email" FIELD to VALUE
    m = re.search(
        r'update\s+(?:the\s+user\s+)?"?([^\s",]+@[^\s",]+)"?\'?s?\s+(\w+)\s+to\s+(.+?)[.\s]*$',
        t, re.IGNORECASE,
    )
    if m:
        email, field, value = m.group(1).strip(), m.group(2).strip().lower(), m.group(3).strip()
        user = find_by_email(db, email)
        if not user:
            return False, f'No user found with email "{email}".'
        if field not in ALLOWED_FIELDS:
            return False, f'I can update name, email, phone, or city — not "{field}".'
        setattr(user, field, value)
        db.commit()
        return True, f'Updated "{email}"\'s {field} to "{value}".'

    return False, (
        'I didn\'t catch that. Try: add the user "jane@xyz.com" with phone number "+123", '
        'remove the user "jane@xyz.com", or update janes city to Lahore.'
    )
