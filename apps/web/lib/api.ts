import {authHeaders} from "./auth-client";

export type Gift = {
  id: string;
  name: string;
  description: string;
  category: string;
  price_minor: number;
  currency: string;
  emoji: string;
  demo_only: boolean;
  label: string;
  reason: string;
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
  const headers: Record<string,string> = {"Content-Type":"application/json", ...await authHeaders()};
  const response = await fetch(`/backend/api/v1${path}`, {method, headers, ...(body === undefined ? {} : {body: JSON.stringify(body)}), cache: "no-store"});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  }
  return data as T;
}
export function dollars(minor: number) { return new Intl.NumberFormat("en-US", {style:"currency",currency:"USD"}).format(minor/100); }
