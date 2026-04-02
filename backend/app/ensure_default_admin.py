from .database import Base, SessionLocal, engine
from .models import User, UserProfile
from .security import hash_password


DEFAULT_ADMIN_NAME = "Admin"
DEFAULT_ADMIN_EMAIL = "admin@local"
DEFAULT_ADMIN_CODE = "ADMIN"
DEFAULT_ADMIN_PASSWORD = "123456"


def ensure_default_admin() -> dict:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.institution_id == DEFAULT_ADMIN_CODE).first()
        user = None

        if profile:
            user = db.query(User).filter(User.id == profile.user_id).first()

        if not user:
            user = db.query(User).filter(User.email == DEFAULT_ADMIN_EMAIL).first()

        if not user:
            user = User(name=DEFAULT_ADMIN_NAME, email=DEFAULT_ADMIN_EMAIL, role="authority")
            db.add(user)
            db.commit()
            db.refresh(user)

        user.name = DEFAULT_ADMIN_NAME
        user.role = "authority"

        if not profile:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()

        if not profile:
            profile = UserProfile(
                user_id=user.id,
                department="Admin",
                institution_id=DEFAULT_ADMIN_CODE,
                contact_number="0000000000",
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                approval_status="approved",
                is_active=1,
            )
            db.add(profile)
        else:
            profile.department = "Admin"
            profile.institution_id = DEFAULT_ADMIN_CODE
            profile.contact_number = profile.contact_number or "0000000000"
            profile.password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
            profile.approval_status = "approved"
            profile.is_active = 1

        db.commit()

        return {
            "user_code": DEFAULT_ADMIN_CODE,
            "password": DEFAULT_ADMIN_PASSWORD,
            "name": DEFAULT_ADMIN_NAME,
            "user_id": user.id,
        }
    finally:
        db.close()


if __name__ == "__main__":
    result = ensure_default_admin()
    print("Default admin ensured")
    print(f"Authority login: {result['user_code']} / {result['password']}")
