#!/usr/bin/env node
/**
 * Render a human-readable post body for FB / LinkedIn from a candidate
 * record produced by select-top.mjs. Two functions exported as ESM:
 *
 *   - renderPostBody(candidate, lang = "en") -> string
 *   - buildPlaceUrl(id) -> string
 *
 * Run as a CLI to preview:
 *   echo '<one candidate JSON>' | node scripts/social/render-text.mjs
 */

const SITE = "https://h2oatlas.ee";

const STATUS = {
  en: { violation: "violation in the latest sample", compliant: "compliant in the latest sample", unknown: "no recent verdict" },
  ru: { violation: "нарушение в последней пробе", compliant: "норма в последней пробе", unknown: "статус неизвестен" },
};

const RISK = {
  en: { high: "high model risk", medium: "medium model risk", low: "low model risk", unknown: "model risk unknown" },
  ru: { high: "высокий риск модели", medium: "средний риск модели", low: "низкий риск модели", unknown: "риск модели неизвестен" },
};

const DOMAIN = {
  en: { supluskoha: "swimming spot", veevark: "drinking-water network", basseinid: "pool/SPA", joogivesi: "drinking-water source" },
  ru: { supluskoha: "место для купания", veevark: "питьевой водопровод", basseinid: "бассейн/SPA", joogivesi: "источник питьевой воды" },
};

export function buildPlaceUrl(id) {
  return `${SITE}/?place=${encodeURIComponent(id)}`;
}

function statusKey(c) {
  if (c === 0) return "violation";
  if (c === 1) return "compliant";
  return "unknown";
}

export function renderPostBody(c, lang = "en") {
  const where = c.county ? `${c.location} (${c.county})` : c.location;
  const domain = DOMAIN[lang]?.[c.domain] ?? c.domain;
  const status = STATUS[lang][statusKey(c.official_compliant)];
  const risk = RISK[lang][c.risk_level] ?? RISK[lang].unknown;
  const url = buildPlaceUrl(c.id);

  if (lang === "ru") {
    return [
      `${where} — ${domain}`,
      ``,
      `Свежий статус: ${status}.`,
      `Оценка риска нарушения: ${risk}${typeof c.model_violation_prob === "number" ? ` (P=${c.model_violation_prob.toFixed(2)})` : ""}.`,
      ``,
      `Подробности и интерактивная карта: ${url}`,
      ``,
      `#вода #Эстония #открытыеданные #Terviseamet #машинноеобучение`,
    ].join("\n");
  }

  return [
    `${where} — ${domain}`,
    ``,
    `Latest status: ${status}.`,
    `Model risk assessment: ${risk}${typeof c.model_violation_prob === "number" ? ` (P=${c.model_violation_prob.toFixed(2)})` : ""}.`,
    ``,
    `Explore the interactive map: ${url}`,
    ``,
    `#waterquality #Estonia #opendata #Terviseamet #machinelearning`,
  ].join("\n");
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
  let raw = "";
  process.stdin.on("data", (chunk) => (raw += chunk));
  process.stdin.on("end", () => {
    const c = JSON.parse(raw);
    process.stdout.write(renderPostBody(c, process.argv[2] || "en") + "\n");
  });
}
