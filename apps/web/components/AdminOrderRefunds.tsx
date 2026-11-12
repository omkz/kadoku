"use client";

import {useCallback, useEffect, useRef, useState, type FormEvent} from "react";
import {api, dollars} from "@/lib/api";

type Order = {
  id: string;
  price_minor: number;
  currency: string;
  status: string;
  refundable: boolean;
};

type Refund = {
  request_key: string;
  amount_minor: number;
  currency: string;
  status: string;
  paypal_refund_id: string | null;
};

type Attempt = {requestKey: string; amountMinor: number};

const storageKey = (orderId: string) => "kadoku-refund-attempt:" + orderId;

function readAttempt(orderId: string): Attempt | null {
  try {
    const raw = sessionStorage.getItem(storageKey(orderId));
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return null;
    const attempt = value as Record<string,unknown>;
    if (typeof attempt.requestKey !== "string" ||
        !/^[0-9a-f-]{36}$/i.test(attempt.requestKey) ||
        typeof attempt.amountMinor !== "number" ||
        !Number.isSafeInteger(attempt.amountMinor) || attempt.amountMinor <= 0) return null;
    return {requestKey: attempt.requestKey, amountMinor: attempt.amountMinor};
  } catch {
    return null;
  }
}

function saveAttempt(orderId: string, attempt: Attempt) {
  try { sessionStorage.setItem(storageKey(orderId), JSON.stringify(attempt)); }
  catch { /* The API still persists idempotency keys if storage is disabled. */ }
}

function clearAttempt(orderId: string) {
  try { sessionStorage.removeItem(storageKey(orderId)); } catch { /* no-op */ }
}

function parseUsd(value: string): number | null {
  const match = /^(0|[1-9]\d*)(?:\.(\d{1,2}))?$/.exec(value.trim());
  if (!match) return null;
  const cents = Number(match[1]) * 100 + Number((match[2] || "").padEnd(2, "0"));
  return Number.isSafeInteger(cents) && cents > 0 ? cents : null;
}

export default function AdminOrderRefunds({
  order, isSuperAdmin, onUpdated,
}: {
  order: Order;
  isSuperAdmin: boolean;
  onUpdated: () => void;
}) {
  const [refunds, setRefunds] = useState<Refund[] | null>(null);
  const [amount, setAmount] = useState("1.00");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [actionError, setActionError] = useState("");
  const [resultMessage, setResultMessage] = useState("");
  const inFlight = useRef(false);

  const loadRefunds = useCallback(async () => {
    setLoading(true);
    setHistoryError("");
    try {
      const rows = await api<Refund[]>("/admin/orders/" + encodeURIComponent(order.id) + "/refunds");
      setRefunds(rows);
      const pending = rows.find(row => row.status === "pending");
      const saved = readAttempt(order.id);
      if (pending) {
        const current = {requestKey: pending.request_key, amountMinor: pending.amount_minor};
        setAttempt(current);
        saveAttempt(order.id, current);
      } else if (saved && rows.some(row => row.request_key === saved.requestKey)) {
        clearAttempt(order.id);
        setAttempt(null);
      } else {
        // Preserve a request that may have reached PayPal but lost its response.
        setAttempt(saved);
      }
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not load refunds.");
      setAttempt(readAttempt(order.id));
    } finally {
      setLoading(false);
    }
  }, [order.id]);

  useEffect(() => { void loadRefunds(); }, [loadRefunds]);

  const refundedMinor = (refunds || [])
    .filter(row => row.status === "completed")
    .reduce((total, row) => total + row.amount_minor, 0);
  const remainingMinor = Math.max(0, order.price_minor - refundedMinor);
  const pending = refunds?.find(row => row.status === "pending");
  const activeAttempt = pending
    ? {requestKey: pending.request_key, amountMinor: pending.amount_minor}
    : attempt;
  const canRefund = isSuperAdmin && order.refundable && remainingMinor > 0;

  async function submitRefund(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canRefund || loading || inFlight.current) return;
    const amountMinor = activeAttempt?.amountMinor ?? parseUsd(amount);
    if (amountMinor === null || amountMinor <= 0 || amountMinor > remainingMinor) {
      setActionError("Enter an amount between $0.01 and " + dollars(remainingMinor) + ".");
      return;
    }
    if (!activeAttempt && !window.confirm(
      "Refund " + dollars(amountMinor) + " for order " + order.id.slice(0,8) +
      "? This sends a PayPal Sandbox refund request."
    )) return;

    const current = activeAttempt ?? {requestKey: crypto.randomUUID(), amountMinor};
    inFlight.current = true;
    setBusy(true);
    setActionError("");
    setResultMessage("");
    saveAttempt(order.id, current);
    setAttempt(current);
    try {
      const result = await api<Refund>(
        "/admin/orders/" + encodeURIComponent(order.id) + "/refund",
        "POST", {request_key: current.requestKey, amount_minor: current.amountMinor},
      );
      if (result.request_key !== current.requestKey || result.amount_minor !== current.amountMinor) {
        throw new Error("Unexpected PayPal refund response. Check its status before retrying.");
      }
      setResultMessage(
        result.status === "completed"
          ? "Sandbox refund completed: " + dollars(result.amount_minor) + "."
          : result.status === "pending"
            ? "Refund pending. Use Check / retry with the same request ID."
            : "Refund status: " + result.status + "."
      );
      if (result.status === "completed" || result.status === "failed") {
        clearAttempt(order.id);
        setAttempt(null);
        onUpdated();
      }
    } catch (error) {
      setActionError(
        (error instanceof Error ? error.message : "Refund status unknown.") +
        " Do not start a new refund; check or retry this request."
      );
    } finally {
      await loadRefunds();
      setBusy(false);
      inFlight.current = false;
    }
  }

  return <div className="admin-history">
    <h3>PayPal Sandbox refunds</h3>
    <p className="admin-muted">Completed: {dollars(refundedMinor)} · Remaining: {dollars(remainingMinor)}</p>
    {loading && <p className="admin-muted" role="status">Checking refund history…</p>}
    {historyError && <p className="admin-error" role="alert">{historyError}</p>}
    {!loading && refunds?.length === 0 && <p className="admin-muted">No refunds yet.</p>}
    {refunds && refunds.length > 0 && <ol>
      {refunds.map(refund => <li key={refund.request_key}>
        <strong>{dollars(refund.amount_minor)} · {refund.status}</strong>
        {refund.paypal_refund_id && <p className="admin-muted">PayPal refund: <code>{refund.paypal_refund_id}</code></p>}
      </li>)}
    </ol>}
    {isSuperAdmin && <>
      {canRefund ? <form onSubmit={event => void submitRefund(event)}>
        {activeAttempt
          ? <p className="admin-muted">Unresolved refund: {dollars(activeAttempt.amountMinor)}. Retry uses the original request ID.</p>
          : <div className="admin-form-grid">
            <label className="admin-field">Refund amount (USD)
              <input type="text" inputMode="decimal" maxLength={15}
                value={amount} onChange={event => setAmount(event.target.value)}
                placeholder="1.00" aria-label="Refund amount in USD" disabled={busy || loading}/>
            </label>
            <div className="admin-editor-actions">
              <button type="button" className="admin-outline" disabled={busy || loading}
                onClick={() => setAmount((remainingMinor / 100).toFixed(2))}>Full remaining</button>
            </div>
          </div>}
        {actionError && <p className="admin-error" role="alert">{actionError}</p>}
        {resultMessage && <p role="status" className="admin-muted">{resultMessage}</p>}
        <div className="admin-editor-actions">
          <button type="button" className="admin-outline" onClick={() => void loadRefunds()}
            disabled={busy || loading}>Refresh status</button>
          <button type="submit" className="admin-primary" disabled={busy || loading}>
            {busy ? "Checking PayPal…" : activeAttempt ? "Check / retry refund" : "Confirm Sandbox refund"}
          </button>
        </div>
      </form>
      : <p className="admin-muted">Refund unavailable: requires an unfulfilled, captured USD order with a refundable balance.</p>}
    </>}
    {!isSuperAdmin && <p className="admin-muted">Only a super administrator can issue refunds.</p>}
  </div>;
}
