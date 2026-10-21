export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type CallMode = "inbound" | "outbound";
export type OutboundReason =
  | "auto"
  | "emi_reminder"
  | "overdue_followup"
  | "kyc_update"
  | "product_update";

export interface Customer {
  customer_id: string;
  name: string;
}

export async function fetchCustomers(): Promise<Customer[]> {
  const res = await fetch(`${API_BASE}/api/customer/list`);
  if (!res.ok) {
    throw new Error(`Failed to load customers (${res.status})`);
  }
  return res.json();
}

export interface TokenResponse {
  token: string;
  room_name: string;
  url: string;
}

export async function fetchRealtimeToken(
  sessionId: string,
  callMode: CallMode,
  language: string,
  customerId: string,
  outboundReason?: OutboundReason,
): Promise<TokenResponse> {
  const params = new URLSearchParams({
    session_id: sessionId,
    customer_id: customerId,
    call_mode: callMode,
    language,
  });
  if (callMode === "outbound" && outboundReason) {
    params.set("outbound_reason", outboundReason);
  }
  const res = await fetch(`${API_BASE}/api/realtime/token?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to get call token (${res.status})`);
  }
  return res.json();
}

export function newSessionId(): string {
  return crypto.randomUUID();
}
