import re
from datetime import datetime
from typing import Optional, Tuple
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

COMPANY_KEYWORDS = re.compile(
    r"\b(pvt|ltd|inc|llc|llp|corp|corporation|company|technologies|tech|labs|solutions|"
    r"systems|group|enterprise|enterprises|studio|studios|agency|consulting|global|india|gmbh|plc|co)\b",
    re.IGNORECASE,
)


def split_person_and_company(raw_input: str) -> Tuple[Optional[str], Optional[str]]:
    cleaned = raw_input.strip()

    paren_match = re.match(r"^([A-Za-z\s\.]+)\s*\((.+)\)$", cleaned)
    if paren_match:
        return paren_match.group(1).strip(), paren_match.group(2).strip()

    for sep in [" - ", " | ", " @ ", " / ", ","]:
        if sep in cleaned:
            parts = [p.strip() for p in cleaned.split(sep, 1)]
            return parts[0], parts[1]

    if COMPANY_KEYWORDS.search(cleaned) or not re.fullmatch(r"[A-Za-z\s\.]+", cleaned):
        return None, cleaned

    return cleaned, None


class OTPRequestSchema(BaseModel):
    email: EmailStr


class OTPVerifySchema(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=6)
    provider: Optional[str] = "EMAIL-OTP"
    identifier: Optional[str] = None


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    raw_name_or_company: str = Field(..., min_length=2, max_length=160)
    verified_identifier: str = Field(..., min_length=2, max_length=180)
    verification_token: str = Field(..., min_length=16)

    email: Optional[str] = None
    insta_id: Optional[str] = None
    google_account: Optional[str] = None
    github_account: Optional[str] = None

    rating: int = Field(..., ge=1, le=5, description="Minimum 1 star, maximum 5 stars")
    message: str = Field(..., min_length=10, max_length=15000, description="Minimum 10 characters, max 1000 words")

    @model_validator(mode="after")
    def validate_message_constraints(self) -> "FeedbackCreate":
        if len(self.message.strip()) < 10:
            raise ValueError("Feedback message must be at least 10 characters long.")
        words = [w for w in self.message.strip().split() if w]
        if len(words) > 1000:
            raise ValueError(f"Feedback message cannot exceed 1,000 words (got {len(words)}).")
        return self


class FeedbackUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    person_name: Optional[str] = Field(default=None, max_length=160)
    company_name: Optional[str] = Field(default=None, max_length=160)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    message: Optional[str] = Field(default=None, min_length=10, max_length=15000)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    person_name: Optional[str]
    company_name: Optional[str]
    email: Optional[str]
    insta_id: Optional[str]
    google_account: Optional[str]
    github_account: Optional[str]
    verification_provider: str
    rating: int
    rating_stars: str
    word_count: int
    message: str
    synced_to_drive: bool
    created_at: datetime


class PortfolioStatsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hackathons_count: int = Field(..., ge=0)
    projects_count: int = Field(..., ge=0)
    research_papers_count: int = Field(..., ge=0)
