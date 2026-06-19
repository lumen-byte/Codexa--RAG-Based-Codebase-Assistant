from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport import requests
import secrets
import string

from app.config import GOOGLE_CLIENT_ID
from app.auth.schemas import Token, UserCreate, UserResponse, GoogleAuthRequest
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


def generate_random_password(length=32):
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Registers a new user inside the system.
    Hashes the user password and inserts the user record into the database.
    """
    if len(user_in.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )

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

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found. Please register first.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create the access token
    access_token = create_access_token(subject=db_user.email)

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/google", response_model=Token)
def google_auth(request: GoogleAuthRequest, db: Session = Depends(get_db)):
    """
    Authenticates a user using a Google OAuth JWT token.
    If the user doesn't exist, automatically creates a new account.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google Login is not configured on the server."
        )

    try:
        # Verify the token with Google
        id_info = id_token.verify_oauth2_token(
            request.credential, requests.Request(), GOOGLE_CLIENT_ID
        )

        email = id_info.get("email")
        if not email:
            raise ValueError("Token didn't contain an email.")

        # Check if user exists
        statement = select(User).where(User.email == email)
        db_user = db.execute(statement).scalar_one_or_none()

        if not db_user:
            # Create user with strong random password
            random_pw = generate_random_password()
            db_user = User(
                email=email,
                hashed_password=hash_password(random_pw)
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        # Create our own app access token
        access_token = create_access_token(subject=db_user.email)
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {str(e)}"
        )
