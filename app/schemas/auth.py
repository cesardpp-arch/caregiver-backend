from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    user_id: int
    email: EmailStr
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
