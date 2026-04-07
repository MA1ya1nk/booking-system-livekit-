from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.user import User, UserRole


def create_admin(name: str, email: str, password: str) -> None:
    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            print("Admin already exists for this email.")
            return
        user = User(
            name=name,
            email=email,
            hashed_password=get_password_hash(password),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        print("Admin created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    create_admin(name="Admin", email="admin@example.com", password="admin123")
