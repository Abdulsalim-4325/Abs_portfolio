from datetime import datetime
from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=4)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class AdminProfileResponse(BaseModel):
    id: str
    username: str
    created_at: datetime


class AdminPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)
