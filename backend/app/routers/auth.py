from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserProfile
from ..schemas import (
    CredentialLoginRequest,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    SignupRequest,
    SignupResponse,
    UserProfileResponse,
    UserResponse,
    UserWithProfileResponse,
)
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..services.audit import log_audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_user_with_profile(user: User, profile: UserProfile) -> UserWithProfileResponse:
    return UserWithProfileResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        profile=UserProfileResponse(
            user_id=user.id,
            department=profile.department,
            user_code=profile.institution_id,
            contact_number=profile.contact_number,
            approval_status=profile.approval_status,
            is_active=profile.is_active == 1,
            assigned_teacher_id=profile.assigned_teacher_id,
        ),
    )


@router.post("/signup", response_model=SignupResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    if db.query(UserProfile).filter(UserProfile.institution_id == payload.user_code).first():
        raise HTTPException(status_code=400, detail="User ID already exists")

    if payload.role == "student":
        if not payload.teacher_user_id:
            raise HTTPException(status_code=400, detail="Student signup requires teacher_user_id")
        teacher = db.query(User).filter(User.id == payload.teacher_user_id, User.role == "teacher").first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")

    user = User(name=payload.name, email=payload.email, role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)

    # Authority account can self-activate to bootstrap the system.
    is_authority = payload.role == "authority"
    profile = UserProfile(
        user_id=user.id,
        department=payload.department,
        institution_id=payload.user_code,
        contact_number=payload.contact_number,
        password_hash=hash_password(payload.password),
        approval_status="approved" if is_authority else "pending",
        is_active=1 if is_authority else 0,
        assigned_teacher_id=payload.teacher_user_id if payload.role == "student" else None,
    )
    db.add(profile)
    db.commit()

    log_audit(
        db,
        user_id=user.id,
        action="signup",
        entity_type="user",
        entity_id=user.id,
        metadata={"role": user.role, "approval_status": profile.approval_status},
    )

    message = "Signup submitted. Wait for approval."
    if is_authority:
        message = "Authority account created and activated."

    return SignupResponse(user_id=user.id, status=profile.approval_status, message=message)


@router.post("/login-id", response_model=LoginResponse)
def login_with_id(payload: CredentialLoginRequest, db: Session = Depends(get_db)):
    normalized_code = payload.user_code.strip().lower()
    profile = (
        db.query(UserProfile)
        .filter(func.lower(UserProfile.institution_id) == normalized_code)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="User ID not found")

    user = db.query(User).filter(User.id == profile.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(payload.password, profile.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if profile.approval_status != "approved":
        raise HTTPException(status_code=403, detail="Account not approved yet")
    if profile.is_active != 1:
        raise HTTPException(status_code=403, detail="Account access is disabled")

    token = create_access_token(user.id, user.role)
    log_audit(
        db,
        user_id=user.id,
        action="login",
        entity_type="user",
        entity_id=user.id,
        metadata={"role": user.role, "method": "id_password"},
    )
    return LoginResponse(access_token=token, user=_build_user_with_profile(user, profile))


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        if existing.role != payload.role:
            raise HTTPException(status_code=400, detail="Role mismatch for existing user")
        token = create_access_token(existing.id, existing.role)
        log_audit(
            db,
            user_id=existing.id,
            action="login",
            entity_type="user",
            entity_id=existing.id,
            metadata={"role": existing.role, "new_user": False},
        )
        profile = db.query(UserProfile).filter(UserProfile.user_id == existing.id).first()
        if not profile:
            profile = UserProfile(
                user_id=existing.id,
                department="General",
                institution_id=f"LEGACY-{existing.id}",
                contact_number="N/A",
                password_hash=hash_password("legacy-password"),
                approval_status="approved",
                is_active=1,
            )
            db.add(profile)
            db.commit()
        return LoginResponse(access_token=token, user=_build_user_with_profile(existing, profile))

    user = User(name=payload.name, email=payload.email, role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.role)
    log_audit(
        db,
        user_id=user.id,
        action="login",
        entity_type="user",
        entity_id=user.id,
        metadata={"role": user.role, "new_user": True},
    )
    profile = UserProfile(
        user_id=user.id,
        department="General",
        institution_id=f"LEGACY-{user.id}",
        contact_number="N/A",
        password_hash=hash_password("legacy-password"),
        approval_status="approved",
        is_active=1,
    )
    db.add(profile)
    db.commit()
    return LoginResponse(access_token=token, user=_build_user_with_profile(user, profile))


@router.get("/teachers")
def list_teacher_directory(db: Session = Depends(get_db)):
    rows = (
        db.query(User, UserProfile)
        .join(UserProfile, User.id == UserProfile.user_id)
        .filter(User.role == "teacher", UserProfile.approval_status == "approved", UserProfile.is_active == 1)
        .all()
    )
    return [
        {
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
            "department": profile.department,
            "user_code": profile.institution_id,
        }
        for user, profile in rows
    ]


@router.get("/me", response_model=UserWithProfileResponse)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _build_user_with_profile(current_user, profile)


@router.patch("/me", response_model=UserWithProfileResponse)
def update_me(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    current_user.name = payload.name
    profile.department = payload.department
    profile.contact_number = payload.contact_number
    db.commit()
    db.refresh(current_user)
    db.refresh(profile)

    log_audit(
        db,
        user_id=current_user.id,
        action="update_profile",
        entity_type="user",
        entity_id=current_user.id,
        metadata={"department": profile.department},
    )
    return _build_user_with_profile(current_user, profile)


@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if not verify_password(payload.current_password, profile.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    profile.password_hash = hash_password(payload.new_password)
    db.commit()
    log_audit(
        db,
        user_id=current_user.id,
        action="change_password",
        entity_type="user",
        entity_id=current_user.id,
        metadata={},
    )
    return {"status": "ok", "message": "Password changed successfully"}

