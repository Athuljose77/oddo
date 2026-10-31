from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import validate_password_strength


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    role: str
    is_active: bool = True


class RegisterIn(BaseModel):
    """No role field exists here on purpose — registration always creates a customer."""

    email: EmailStr
    password: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        error = validate_password_strength(v)
        if error:
            raise ValueError(error)
        return v

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be empty")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        error = validate_password_strength(v)
        if error:
            raise ValueError(error)
        return v


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        error = validate_password_strength(v)
        if error:
            raise ValueError(error)
        return v


class StaffCreateIn(BaseModel):
    """Admin-only. role is fixed to 'staff' — admin accounts are never API-created."""

    email: EmailStr
    password: str
    name: str = Field(min_length=1, max_length=120)
    role: str = "staff"

    @field_validator("password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        error = validate_password_strength(v)
        if error:
            raise ValueError(error)
        return v

    @field_validator("role")
    @classmethod
    def _staff_only(cls, v: str) -> str:
        if v != "staff":
            raise ValueError("Only 'staff' accounts can be created here")
        return v


class UserPatchIn(BaseModel):
    name: str | None = None
    is_active: bool | None = None
