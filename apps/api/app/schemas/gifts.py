from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


BoundedTag = Annotated[str, Field(min_length=1, max_length=60)]


class GiftContext(BaseModel):
    """Short-lived client-held conversation state, revalidated on every request."""
    model_config = ConfigDict(extra="forbid")

    interests: list[BoundedTag] = Field(default_factory=list, max_length=10)
    occasion: Literal["birthday", "anniversary", "thank_you"] | None = None
    budget_minor: int | None = Field(default=None, gt=0, le=10_000_000)
    avoid: list[BoundedTag] = Field(default_factory=list, max_length=12)
    relationship: str | None = Field(default=None, max_length=80)
    prefer_personal: bool = False
    top_pick_price_minor: int | None = Field(default=None, ge=0, le=10_000_000)


class GiftRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=1200)
    recipient_id: str | None = None
    context: GiftContext | None = None


class GiftCard(BaseModel):
    id: str
    name: str
    description: str
    category: str
    price_minor: int
    currency: str
    emoji: str
    image_url: str | None = None
    demo_only: bool
    label: str
    reason: str


class GiftResponse(BaseModel):
    summary: str
    recommendations: list[GiftCard]
    remaining_today: int
    provider: str
    context: GiftContext | None = None
    notice: str = "Sample catalog; items are not available for real-world fulfillment."


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    category: str
    price_minor: int
    currency: str
    stock: int
    emoji: str
    image_url: str | None = None
    demo_only: bool


class RecipientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relationship: str | None = Field(default=None, max_length=80)
    interests: list[str] = Field(default_factory=list, max_length=20)
    avoids: list[str] = Field(default_factory=list, max_length=20)
    usual_budget_minor: int | None = Field(default=None, ge=0, le=10_000_000)


class RecipientOut(RecipientIn):
    model_config = ConfigDict(from_attributes=True)
    id: str


class OccasionIn(BaseModel):
    recipient_id: str
    kind: str = Field(default="birthday", max_length=40)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    year: int | None = Field(default=None, ge=1900, le=2200)
    reminder_enabled: bool = False


class OccasionOut(OccasionIn):
    model_config = ConfigDict(from_attributes=True)
    id: str


class ShippingAddress(BaseModel):
    """Universal demo shipping address. Saved as an immutable order snapshot."""
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=120)
    address_line_1: str = Field(min_length=5, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str = Field(min_length=2, max_length=80)
    phone_country_code: str | None = Field(default=None, pattern=r"^\+[1-9]\d{0,3}$")
    phone_number: str | None = Field(default=None, max_length=30)

    @field_validator("full_name", "address_line_1", "address_line_2", "city",
                     "region", "postal_code", "country", "phone_number")
    @classmethod
    def trim_and_reject_blank(cls, value: str | None):
        if value is None:
            return value
        text = value.strip()
        if not text:
            return None if value == "" else value  # required fields fail their length checks
        return text

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str | None):
        if value is not None:
            if not all(char.isdigit() or char in " -()." for char in value):
                raise ValueError("Phone number contains invalid characters")
            digits = "".join(char for char in value if char.isdigit())
            if not (5 <= len(digits) <= 15):
                raise ValueError("Phone number must have 5 to 15 digits")
        return value

    @field_validator("phone_country_code", mode="before")
    @classmethod
    def normalize_phone_code(cls, value):
        return value.strip() if isinstance(value, str) else value

class CheckoutStart(BaseModel):
    product_id: str
    shipping_address: ShippingAddress


class CheckoutCreated(BaseModel):
    order_id: str
    approval_url: str
    status: str


class CheckoutCapture(BaseModel):
    order_id: str
    paypal_order_id: str

class OrderSummary(BaseModel):
    id: str
    product_id: str
    product_name: str
    product_emoji: str
    price_minor: int
    currency: str
    status: str
    created_at: datetime


class OrderDetail(OrderSummary):
    shipping_address: ShippingAddress | None = None
    paypal_order_id: str | None = None
    paypal_capture_id: str | None = None
