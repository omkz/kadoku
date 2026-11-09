from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field


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


class CheckoutStart(BaseModel):
    product_id: str


class CheckoutCreated(BaseModel):
    order_id: str
    approval_url: str
    status: str


class CheckoutCapture(BaseModel):
    order_id: str
    paypal_order_id: str
