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
export type GiftResponse = {
  summary: string;
  recommendations: Gift[];
  remaining_today: number;
  provider: string;
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
