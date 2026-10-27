import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings

router = APIRouter()


class ContactInquiry(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=1, max_length=40)
    message: str = Field(min_length=1, max_length=5000)


@router.post("/contact/inquiry")
def submit_contact_inquiry(inquiry: ContactInquiry):
    recipient = quote(settings.CONTACT_INQUIRY_EMAIL, safe="")
    request = Request(
        f"https://formsubmit.co/ajax/{recipient}",
        data=json.dumps({
            "name": inquiry.name,
            "email": str(inquiry.email),
            "phone": inquiry.phone,
            "message": inquiry.message,
            "_subject": f"Home care inquiry from {inquiry.name}",
            "_captcha": "true",
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        raise HTTPException(status_code=502, detail="Unable to send your message right now.") from None

    if not isinstance(result, dict) or result.get("success") not in (True, "true"):
        raise HTTPException(status_code=502, detail="Unable to send your message right now.")

    return {"success": True, "message": "Message sent."}
