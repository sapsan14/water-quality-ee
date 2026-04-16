"use client";

type AnalyticsPayload = {
  event: string;
  ts: string;
  meta?: Record<string, string | number | boolean | null>;
};

const endpoint = process.env.NEXT_PUBLIC_ANALYTICS_ENDPOINT;

export function track(event: string, meta?: AnalyticsPayload["meta"]): void {
  if (!endpoint) return;
  const payload: AnalyticsPayload = {
    event,
    ts: new Date().toISOString(),
    meta
  };
  navigator.sendBeacon(endpoint, JSON.stringify(payload));
}
