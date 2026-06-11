from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import Token, UserCreate, UserResponse
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Registers a new user inside the system.
    Hashes the user password and inserts the user record into the database.
    """
    # Query database to check if email is already taken
    statement = select(User).where(User.email == user_in.email)
    existing_user = db.execute(statement).scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )

    # Instantiate the User model with hashed password
    new_user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Authenticates a user via OAuth2 Form (form_data.username maps to email).
    Validates credentials and returns a Bearer JWT Token.
    """
    # Fetch the user from the database
    statement = select(User).where(User.email == form_data.username)
    db_user = db.execute(statement).scalar_one_or_none()

    # Verify user exists and check password hash
    if not db_user or not verify_password(form_data.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create the access token
    access_token = create_access_token(subject=db_user.email)

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }
