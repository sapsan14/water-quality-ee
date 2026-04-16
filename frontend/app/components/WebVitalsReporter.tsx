"use client";

import { useEffect } from "react";
import { onCLS, onINP, onLCP, onTTFB, type Metric } from "web-vitals";
import { track } from "../lib/analytics";

function send(metric: Metric) {
  track("web_vital", {
    name: metric.name,
    value: Number(metric.value.toFixed(2)),
    rating: metric.rating
  });
}

export default function WebVitalsReporter() {
  useEffect(() => {
    onCLS(send);
    onINP(send);
    onLCP(send);
    onTTFB(send);
  }, []);
  return null;
}
