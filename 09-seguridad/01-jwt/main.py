from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

# --- Config -----------------------------------------------------------
SECRET_KEY = "super-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- Hardcoded data ---------------------------------------------------


def _hash(plain: str) -> bytes:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt())


USERS = [
    {"id": 1, "username": "alice",   "email": "alice@example.com",
        "role": "admin",  "password": _hash("alice123")},
    {"id": 2, "username": "bob",     "email": "bob@example.com",
        "role": "editor", "password": _hash("bob456")},
    {"id": 3, "username": "charlie", "email": "charlie@example.com",
        "role": "viewer", "password": _hash("charlie789")},
]

BOOKS = [
    {"id": 1, "title": "Clean Code",
        "author": "Robert C. Martin", "owner_id": 1},
    {"id": 2, "title": "The Pragmatic Programmer",
        "author": "Andrew Hunt",       "owner_id": 1},
    {"id": 3, "title": "Design Patterns",
        "author": "Gang of Four",      "owner_id": 2},
    {"id": 4, "title": "Refactoring",
        "author": "Martin Fowler",     "owner_id": 2},
    {"id": 5, "title": "Domain-Driven Design",
        "author": "Eric Evans",        "owner_id": 3},
    {"id": 6, "title": "The Clean Coder",
        "author": "Robert C. Martin", "owner_id": 3},
]

# --- Schemas ----------------------------------------------------------


class LoginRequest(BaseModel):
    """ Esquema para la solicitud de login """
    username: str
    password: str


class Token(BaseModel):
    """ Esquema para el token de acceso """
    access_token: str
    token_type: str


class Book(BaseModel):
    """ Esquema para un libro """
    id: int
    title: str
    author: str
    owner_id: int


class User(BaseModel):
    """ Esquema para un usuario """
    id: int
    username: str
    email: str
    role: str


# --- Auth helpers -----------------------------------------------------
# Usamos HTTP Bearer para extraer el token JWT de la cabecera Authorization
# El token se enviará como: Authorization: Bearer <token>
# El esquema HTTPBearer se encarga de validar que el formato sea correcto y extraer el token
# Luego, en la función get_current_user, decodificamos el token y obtenemos la información del usuario
# Si el token es inválido o ha expirado, se lanza una excepción HTTP 401 Unauthorized
# El esquema HTTPBearer también añade el header "WWW-Authenticate: Bearer" en las respuestas 401, lo que es una buena práctica para indicar al cliente que se requiere autenticación Bearer.
bearer_scheme = HTTPBearer()


def get_user(username: str) -> dict | None:
    return next((u for u in USERS if u["username"] == username), None)


def verify_password(plain: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed)


def authenticate_user(username: str, password: str) -> dict | None:
    user = get_user(username)
    if not user or not verify_password(password, user["password"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Error en las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials,
                             SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user(username)
    if user is None:
        raise credentials_exception

    return User(id=user["id"], username=user["username"], email=user["email"], role=user["role"])


CurrentUser = Annotated[User, Depends(get_current_user)]

# --- App --------------------------------------------------------------
app = FastAPI(title="Books API with JWT")


# POST /login — returns a JWT
@app.post("/login", response_model=Token)
def login(body: LoginRequest):
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        data={"sub": user["username"],
              "email": user["email"], "role": user["role"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=token, token_type="bearer")


# GET /books — all books (public)
@app.get("/books", response_model=list[Book])
def list_books(current_user: CurrentUser):
    return BOOKS


# GET /books/{id} — single book (public)
@app.get("/books/{book_id}", response_model=Book)
def get_book(book_id: int):
    book = next((b for b in BOOKS if b["id"] == book_id), None)
    if not book:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    return book


# GET /my-books — only books owned by the logged-in user (protected)
@app.get("/my-books", response_model=list[Book])
def my_books(current_user: CurrentUser):
    return [b for b in BOOKS if b["owner_id"] == current_user.id]


# GET /me — current user info (protected)
@app.get("/me", response_model=User)
def me(current_user: CurrentUser):
    return current_user


# --- Run the app ------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
