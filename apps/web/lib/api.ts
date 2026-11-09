import {authHeaders} from "./auth-client";

export type Gift = {
  id: string;
  name: string;
  description: string;
  category: string;
  price_minor: number;
  currency: string;
  emoji: string;
  image_url: string | null;
  demo_only: boolean;
  label: string;
  reason: string;
};
/** Catalog item returned by the public products endpoint (not an AI recommendation). */
export type CatalogProduct = {
  id: string;
  name: string;
  description: string;
  category: string;
  price_minor: number;
  currency: string;
  stock: number;
  emoji: string;
  image_url: string | null;
  demo_only: boolean;
};
export type GiftContext = {
  interests: string[];
  occasion: "birthday" | "anniversary" | "thank_you" | null;
  budget_minor: number | null;
  avoid: string[];
  relationship: string | null;
  prefer_personal: boolean;
  top_pick_price_minor: number | null;
};
export type GiftResponse = {
  summary: string;
  recommendations: Gift[];
  remaining_today: number;
  provider: string;
  context: GiftContext | null;
  notice: string;
};
/** Recipient address saved per Sandbox order, never shared with the recommendation model. */
export type ShippingAddress = {
  full_name: string;
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  region: string | null;
  postal_code: string | null;
  country: string;
  phone_country_code: string | null;
  phone_number: string | null;
};
export type OrderSummary = {
  id: string;
  product_id: string;
  product_name: string;
  product_emoji: string;
  price_minor: number;
  currency: string;
  status: string;
  created_at: string;
};
export type OrderDetail = OrderSummary & {
  shipping_address: ShippingAddress | null;
  paypal_order_id: string | null;
  paypal_capture_id: string | null;
};
export type Recipient = {
  id: string;
  name: string;
  relationship: string | null;
  interests: string[];
  avoids: string[];
  usual_budget_minor: number | null;
};
export type Occasion = {
  id: string;
  recipient_id: string;
  kind: string;
  month: number;
  day: number;
  year: number | null;
  reminder_enabled: boolean;
};

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const headers: Record<string,string> = {"Content-Type":"application/json", ...await authHeaders(/^\/(recipients|occasions|orders|checkout\/paypal|auth\/me)(\/|$)/.test(path))};
  const response = await fetch(`/backend/api/v1${path}`, {method, headers, ...(body === undefined ? {} : {body: JSON.stringify(body)}), cache: "no-store"});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 429) throw new Error("Daily recommendation limit reached. Please try again tomorrow.");
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  }
  return data as T;
}
export function dollars(minor: number) { return new Intl.NumberFormat("en-US", {style:"currency",currency:"USD"}).format(minor/100); }
