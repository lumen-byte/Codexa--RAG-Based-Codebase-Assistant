from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import TokenData
from app.auth.security import ALGORITHM, SECRET_KEY
from app.db.database import get_db
from app.db.models import User

# Configuration pointing to the token-issuing login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI dependency to secure endpoints.
    Decodes the Bearer JWT token, validates its signature and expiration,
    and returns the corresponding database User object.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode the JWT token using security configurations
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not isinstance(payload, dict):
            raise credentials_exception
            
        email = payload.get("sub")
        if email is None:
            raise credentials_exception

        token_data = TokenData(email=email)

    except JWTError:
        raise credentials_exception

    # Query the user from the database using modern SQLAlchemy 2.0 select statement
    statement = select(User).where(User.email == token_data.email)
    user = db.execute(statement).scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user
