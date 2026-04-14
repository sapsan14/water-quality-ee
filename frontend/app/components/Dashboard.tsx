"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { track } from "../lib/analytics";
import type { FrontendPlace, FrontendSnapshot } from "../lib/types";

const MapClient = dynamic(() => import("./MapClient"), { ssr: false });

type Props = { snapshot: FrontendSnapshot };
type IconName = "pin" | "unpin" | "close" | "alert" | "reset";
type CyrillicFont = "ibm" | "manrope";

const riskOrder: FrontendPlace["risk_level"][] = ["all", "low", "medium", "high", "unknown"] as never;
const officialOrder = ["all", "compliant", "violation", "unknown"] as const;
type Lang = "ru" | "et";
type TabKey = "alerts" | "domain" | "analytics" | "aboutModel" | "aboutService";
const countyKey = (value: string | null | undefined) => (value || "").trim().toLowerCase();
const countyPretty = (value: string | null | undefined) =>
  (value || "")
    .trim()
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(" ");

type DomainKey = "supluskoha" | "veevark" | "joogivesi" | "basseinid";
type NormRule = { min?: number; max?: number; exact?: number; unit: string };

const NORM_RULES: Record<string, Partial<Record<DomainKey, NormRule>> & { default?: NormRule }> = {
  e_coli: {
    supluskoha: { max: 500, unit: "КОЕ/100 мл" },
    basseinid: { exact: 0, unit: "КОЕ/100 мл" },
    default: { max: 500, unit: "КОЕ/100 мл" }
  },
  enterococci: {
    supluskoha: { max: 200, unit: "КОЕ/100 мл" },
    default: { max: 200, unit: "КОЕ/100 мл" }
  },
  coliforms: { basseinid: { exact: 0, unit: "КОЕ/100 мл" } },
  pseudomonas: { basseinid: { exact: 0, unit: "КОЕ/100 мл" } },
  staphylococci: { basseinid: { max: 20, unit: "КОЕ/100 мл" } },
  ph: {
    basseinid: { min: 6.5, max: 8.5, unit: "pH" },
    veevark: { min: 6.5, max: 9.5, unit: "pH" },
    joogivesi: { min: 6.5, max: 9.5, unit: "pH" },
    default: { min: 6.0, max: 9.0, unit: "pH" }
  },
  nitrates: { default: { max: 50, unit: "mg/L" } },
  nitrites: { default: { max: 0.5, unit: "mg/L" } },
  ammonium: { default: { max: 0.5, unit: "mg/L" } },
  fluoride: { default: { max: 1.5, unit: "mg/L" } },
  manganese: { default: { max: 0.05, unit: "mg/L" } },
  iron: { default: { max: 0.2, unit: "mg/L" } },
  turbidity: {
    basseinid: { max: 0.5, unit: "NTU" },
    default: { max: 4.0, unit: "NTU" }
  },
  color: { default: { max: 20, unit: "mg Pt/L" } },
  chlorides: { default: { max: 250, unit: "mg/L" } },
  sulfates: { default: { max: 250, unit: "mg/L" } },
  free_chlorine: { basseinid: { min: 0.2, max: 0.6, unit: "mg/L" } },
  combined_chlorine: { basseinid: { max: 0.4, unit: "mg/L" } }
};

function fmtDate(value: string | null): string {
  if (!value) return "n/a";
  const raw = String(value).trim();
  const isoPrefix = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  if (isoPrefix) return isoPrefix[1];
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const toRad = (v: number) => (v * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthRadiusKm * c;
}

const modelKeyNorm = (value: string) => String(value || "").trim().toLowerCase();

function modelLabelWithPrinciple(key: string, lang: Lang): string {
  const k = modelKeyNorm(key);
  if (k === "lr" || k === "logreg" || k === "logistic_regression") {
    return lang === "ru"
      ? "LR — Logistic Regression (линейная модель вероятности через логистическую функцию)"
      : "LR — Logistic Regression (lineaarne tõenäosusmudel logistilise funktsiooniga)";
  }
  if (k === "rf" || k === "random_forest") {
    return lang === "ru"
      ? "RF — Random Forest (ансамбль деревьев, усредняющий решения)"
      : "RF — Random Forest (puuansambel, mis keskmistab otsuseid)";
  }
  if (k === "gb" || k === "gradient_boosting") {
    return lang === "ru"
      ? "GB — Gradient Boosting (последовательные деревья, исправляющие ошибки предыдущих)"
      : "GB — Gradient Boosting (järjestikused puud, mis parandavad eelmiste vigu)";
  }
  if (k === "lgbm" || k === "lightgbm") {
    return lang === "ru"
      ? "LGBM — LightGBM (эффективный gradient boosting на деревьях)"
      : "LGBM — LightGBM (efektiivne gradient boosting puudel)";
  }
  return key.toUpperCase();
}

function lruet<T>(lang: Lang, ru: T, et: T, en: T): T {
  if (lang === "ru") return ru;
  if (lang === "et") return et;
  return en;
}

function Icon({ name }: { name: IconName }) {
  if (name === "pin") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 4.5h8l-1.4 4.2 2.7 2.8v1H13v6l-1 1-1-1v-6H6.7v-1l2.7-2.8L8 4.5Z" fill="currentColor" />
      </svg>
    );
  }
  if (name === "unpin") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M7 5h10l-1.6 4.3 2.6 2.7v1H13v5.7l-1 1-1-1V13H6v-1l2.6-2.7L7 5Zm-1.7 12.2 11.5-11.5 1.4 1.4L6.7 18.6l-1.4-1.4Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (name === "close") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6.7 5.3 12 10.6l5.3-5.3 1.4 1.4L13.4 12l5.3 5.3-1.4 1.4L12 13.4l-5.3 5.3-1.4-1.4L10.6 12 5.3 6.7l1.4-1.4Z" fill="currentColor" />
      </svg>
    );
  }
  if (name === "alert") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3 2.2 20h19.6L12 3Zm0 5.2c.6 0 1 .4 1 1v5.4a1 1 0 1 1-2 0V9.2c0-.6.4-1 1-1Zm0 10a1.2 1.2 0 1 1 0-2.4 1.2 1.2 0 0 1 0 2.4Z" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 4a8 8 0 1 1-5.7 2.3L4.9 7.7A10 10 0 1 0 12 2v2Zm-1 1 4 4-4 4V10H2V8h9V5Z" fill="currentColor" />
    </svg>
  );
}

export default function Dashboard({ snapshot }: Props) {
  const [lang, setLang] = useState<Lang>("ru");
  const [cyrillicFont, setCyrillicFont] = useState<CyrillicFont>("ibm");
  const [activeTab, setActiveTab] = useState<TabKey>("alerts");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [filtersPinned, setFiltersPinned] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [infoTitle, setInfoTitle] = useState("");
  const [infoText, setInfoText] = useState("");
  const [query, setQuery] = useState("");
  const [segment, setSegment] = useState("all");
  const [risk, setRisk] = useState("all");
  const [county, setCounty] = useState("all");
  const [official, setOfficial] = useState<(typeof officialOrder)[number]>("all");
  const [alertsOnly, setAlertsOnly] = useState(false);
  const [sampleDateFrom, setSampleDateFrom] = useState("");
  const [sampleDateTo, setSampleDateTo] = useState("");
  const [minProb, setMinProb] = useState(0);
  const [minProbInput, setMinProbInput] = useState(0);
  const [nearbyOnly, setNearbyOnly] = useState(false);
  const [nearbyRadiusKm, setNearbyRadiusKm] = useState(10);
  const [userCoords, setUserCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [simDelta, setSimDelta] = useState(0);
  const [simPressure, setSimPressure] = useState(0);
  const [simMicro, setSimMicro] = useState(0);
  const [watchlist, setWatchlist] = useState<string[]>([]);

  const tr = useMemo(
    () => ({
      ru: {
        filters: "Фильтры",
        pin: "Закрепить",
        unpin: "Открепить",
        openFilters: "Открыть фильтры",
        close: "Закрыть",
        search: "Поиск по месту/уезду",
        domain: "Домен",
        locationType: "Тип локации",
        county: "Уезд",
        risk: "Риск",
        official: "Официальный статус",
        minProb: "Мин. вероятность",
        alertsOnly: "Только алерты",
        nearMe: "Рядом со мной",
        nearRadius: "Радиус",
        clearNearMe: "Очистить геопозицию",
        geoDenied: "Геодоступ отклонён. Разрешите доступ к местоположению в браузере.",
        geoUnsupported: "Геолокация не поддерживается вашим браузером.",
        latestSampleDate: "Дата последней пробы",
        dateFrom: "С",
        dateTo: "По",
        resetDate: "Сбросить",
        latestSampleDateHint: "Если диапазон активен, точки без даты последней пробы скрываются.",
        clearFilters: "Сбросить фильтры",
        mapTitle: "Интерактивная карта качества воды",
        selectedPoint: "Выбранная точка",
        noSelectedPoint: "Кликните по маркеру или строке таблицы, чтобы увидеть детали точки.",
        measurements: "Показатели воды",
        history: "История",
        historyPlaceholder: "История по точке не найдена в текущем экспортированном наборе.",
        tabs: {
          alerts: "Алерты",
          domain: "Домены",
          analytics: "Модели и диагностика",
          aboutModel: "О модели",
          aboutService: "О сервисе"
        },
        aboutModel:
          "ML-модели (LR, RF, GB, LightGBM) оценивают вероятность нарушения по лабораторным показателям. Это инструмент поддержки решений, а не медицинская рекомендация.",
        aboutService:
          "Сервис объединяет открытые данные Terviseamet, карту, аналитику и объяснения параметров воды для жителей, туристов и семей.",
        metricGuideTitle: "Как читать метрики: точно + интуитивно",
        metricGuide: {
          roc: {
            title: "1) ROC-AUC — разделение классов",
            precise:
              "ROC-кривая строится по всем порогам и показывает TPR (Recall для нарушений) против FPR (ложные тревоги). AUC — площадь под кривой: вероятность, что случайное нарушение получит более высокий риск, чем случайная норма. AUC=0.5 — случайно, AUC=1.0 — идеальное ранжирование.",
            intuitive:
              "Если взять одну плохую и одну хорошую пробу, ROC-AUC показывает, как часто модель ставит более высокий риск плохой пробе. Это метрика качества ранжирования, а не выбранного порога.",
            reading:
              "Ориентир: 0.5 — случайно; 0.7-0.8 — приемлемо; 0.8-0.9 — хорошо; >0.9 — очень хорошо. Но высокий AUC сам по себе не задаёт хороший порог решения."
          },
          pr: {
            title: "2) Precision / Recall — цена ошибок",
            precise:
              "Recall = TP/(TP+FN): доля найденных реальных нарушений. Precision = TP/(TP+FP): доля подтвержденных нарушений среди тревог модели. FN — самые опасные ошибки (пропущенное нарушение), FP — лишние проверки.",
            intuitive:
              "Recall отвечает: 'сколько опасных случаев мы не пропустили?'. Precision отвечает: 'сколько наших тревог реально опасны?'. Обычно при росте Recall падает Precision, поэтому выбирается компромиссный порог.",
            reading:
              "Для water safety обычно важнее высокий Recall (не пропустить нарушение). Если Recall высокий, а Precision низкий — больше ложных тревог; обратная ситуация даёт меньше тревог, но больше пропусков."
          },
          calibration: {
            title: "3) Calibration — доверие к вероятности",
            precise:
              "Калибровка проверяет согласованность вероятностей с частотами. Если модель выдает группу точек с P(нарушения)=0.70, то примерно 70% таких точек должны реально быть нарушениями. Оценивается reliability-диаграммой и Brier score (ниже — лучше).",
            intuitive:
              "Это тест 'честности процентов'. Хорошо откалиброванная модель говорит 20% только там, где риск действительно около 20%, и 80% — где риск действительно около 80%.",
            reading:
              "Если калибровка плохая, проценты нельзя понимать как прямую вероятность. Тогда P(нарушения) полезнее для ранжирования приоритетов, чем для буквального 'шанса в процентах'."
          },
          shap: {
            title: "4) SHAP — объяснение причин риска",
            precise:
              "SHAP раскладывает прогноз точки на вклад признаков относительно базового уровня риска: положительный вклад увеличивает риск, отрицательный уменьшает. Сумма вкладов + baseline соответствует итоговому score модели.",
            intuitive:
              "SHAP — это 'чек', из чего собрался риск. Например, высокий iron и color могли поднять риск, а нормальный pH — снизить. Это объяснение модели, а не доказательство причинно-следственной связи в природе.",
            reading:
              "Большой положительный вклад SHAP двигает прогноз к нарушению, отрицательный — к норме. Это интерпретация поведения модели, а не доказательство физической причины загрязнения."
          }
        }
      },
      et: {
        filters: "Filtrid",
        pin: "Kinnita",
        unpin: "Vabasta",
        openFilters: "Ava filtrid",
        close: "Sulge",
        search: "Otsi koha/maakonna järgi",
        domain: "Domeen",
        locationType: "Asukoha tüüp",
        county: "Maakond",
        risk: "Risk",
        official: "Ametlik staatus",
        minProb: "Min tõenäosus",
        alertsOnly: "Ainult häired",
        nearMe: "Minu lähedal",
        nearRadius: "Raadius",
        clearNearMe: "Tühjenda geopositsioon",
        geoDenied: "Asukohaluba on keelatud. Luba brauseris asukohale ligipääs.",
        geoUnsupported: "Geolokatsioon ei ole selles brauseris toetatud.",
        latestSampleDate: "Viimane proov kuupäev",
        dateFrom: "Alates",
        dateTo: "Kuni",
        resetDate: "Lähtesta",
        latestSampleDateHint: "Kui kuupäevavahemik on aktiivne, peidetakse punktid ilma viimase proovi kuupäevata.",
        clearFilters: "Tühjenda filtrid",
        mapTitle: "Interaktiivne veekvaliteedi kaart",
        selectedPoint: "Valitud punkt",
        noSelectedPoint: "Klõpsa markeril või tabeli real, et näha detailset infot.",
        measurements: "Vee näitajad",
        history: "Ajalugu",
        historyPlaceholder: "Selle punkti ajalugu pole eksporditud andmestikus saadaval.",
        tabs: {
          alerts: "Häired",
          domain: "Domeenid",
          analytics: "Mudelid ja diagnostika",
          aboutModel: "Mudelist",
          aboutService: "Teenusest"
        },
        aboutModel:
          "ML-mudelid (LR, RF, GB, LightGBM) hindavad rikkumise tõenäosust laborinäitajate põhjal. See on otsusetugi, mitte meditsiiniline soovitus.",
        aboutService:
          "Teenuses on koos Terviseameti avaandmed, kaart, analüütika ja selgitused vee parameetrite kohta.",
        metricGuideTitle: "Mõõdikud: täpselt + intuitiivselt",
        metricGuide: {
          roc: {
            title: "1) ROC-AUC — klasside eristusvõime",
            precise:
              "ROC-kõver võrdleb TPR-i ja FPR-i kõigi lävede korral. AUC on pindala kõvera all: tõenäosus, et juhuslik rikkumine saab kõrgema riski kui juhuslik norm. 0.5 = juhuslik, 1.0 = ideaalne järjestus.",
            intuitive:
              "Kui võtta üks halb ja üks hea proov, ROC-AUC näitab, kui tihti mudel annab halvale proovile kõrgema riski.",
            reading:
              "0.5 = juhuslik; 0.7-0.8 = rahuldav; 0.8-0.9 = hea; >0.9 = väga hea. Kõrge AUC ei määra automaatselt head otsustusläve."
          },
          pr: {
            title: "2) Precision / Recall — vigade hind",
            precise:
              "Recall = TP/(TP+FN): kui palju päris rikkumistest leitakse. Precision = TP/(TP+FP): kui suur osa häiretest osutub päris rikkumiseks. FN on ohtlikud möödalaskmised, FP on lisakontroll.",
            intuitive:
              "Recall: 'mida me üles leidsime?'. Precision: 'kui usaldusväärsed on häired?'. Tavaliselt ühe kasv vähendab teist.",
            reading:
              "Veeohutuses eelistatakse tihti kõrgemat Recalli. Kõrge Recall + madal Precision = rohkem valehäireid; vastupidi = rohkem möödalaske."
          },
          calibration: {
            title: "3) Calibration — tõenäosuse usaldatavus",
            precise:
              "Kalibreeritus võrdleb mudeli tõenäosusi tegelike sagedustega. Kui mudel annab grupile P=0.70, peaks umbes 70% neist olema rikkumised. Hinnatakse reliability-kõvera ja Brier score'iga.",
            intuitive:
              "Kas mudeli protsendid on 'ausad': 20% tähendab päriselt umbes 20%, 80% tähendab umbes 80%.",
            reading:
              "Halva kalibreerituse korral ei maksa protsente võtta otsese tõenäosusena; neid tasub kasutada pigem järjestamiseks."
          },
          shap: {
            title: "4) SHAP — riski põhjendamine",
            precise:
              "SHAP jaotab üksikprognoosi tunnuste panusteks võrreldes baastasemega. Positiivne panus tõstab riski, negatiivne langetab. Panuste summa + baseline annab lõppscore'i.",
            intuitive:
              "SHAP on prognoosi 'lahtivõtt': mis näitajad riski tõstsid ja mis seda vähendasid. See pole põhjuslik tõestus.",
            reading:
              "Suur positiivne SHAP-panuse väärtus tõstab rikkumisriski, negatiivne vähendab. Tõlgenda mudeli selgitusena, mitte põhjusliku tõendusena."
          }
        }
      },
      en: {
        filters: "Filters",
        pin: "Pin",
        unpin: "Unpin",
        openFilters: "Open filters",
        close: "Close",
        search: "Search by place/county",
        domain: "Domain",
        locationType: "Location type",
        county: "County",
        risk: "Risk",
        official: "Official status",
        minProb: "Min probability",
        alertsOnly: "Alerts only",
        nearMe: "Near me",
        nearRadius: "Radius",
        clearNearMe: "Clear geolocation",
        geoDenied: "Geolocation access denied. Please allow location access in your browser.",
        geoUnsupported: "Geolocation is not supported in this browser.",
        latestSampleDate: "Latest sample date",
        dateFrom: "From",
        dateTo: "To",
        resetDate: "Reset",
        latestSampleDateHint: "If date range is active, points without latest sample date are hidden.",
        clearFilters: "Clear filters",
        mapTitle: "Interactive water quality map",
        selectedPoint: "Selected point",
        noSelectedPoint: "Click a marker or table row to see point details.",
        measurements: "Water measurements",
        history: "History",
        historyPlaceholder: "History for this point is not available in the current export.",
        tabs: {
          alerts: "Alerts",
          domain: "Domains",
          analytics: "Models and diagnostics",
          aboutModel: "About model",
          aboutService: "About service"
        },
        aboutModel:
          "ML models (LR, RF, GB, LightGBM) estimate violation probability from lab measurements. This is decision support, not medical advice.",
        aboutService:
          "The service combines Terviseamet open data, map, analytics, and explanations of water parameters for residents and visitors.",
        metricGuideTitle: "How to read metrics: precise + intuitive",
        metricGuide: {
          roc: {
            title: "1) ROC-AUC — class separability",
            precise:
              "ROC curve compares TPR and FPR across all thresholds. AUC is area under the curve: probability that a random violation gets a higher risk than a random compliant sample.",
            intuitive:
              "If you take one bad and one good sample, ROC-AUC shows how often the model ranks the bad one higher.",
            reading:
              "Rule of thumb: 0.5 random, 0.7-0.8 fair, 0.8-0.9 good, >0.9 very good. High AUC alone does not set a decision threshold."
          },
          pr: {
            title: "2) Precision / Recall — error trade-off",
            precise:
              "Recall = TP/(TP+FN), Precision = TP/(TP+FP). FN are missed violations, FP are false alarms.",
            intuitive:
              "Recall asks: how many dangerous cases were found? Precision asks: how many alerts were truly dangerous?",
            reading:
              "For water safety, high Recall is often preferred. High Recall + low Precision means more false alarms."
          },
          calibration: {
            title: "3) Calibration — probability reliability",
            precise:
              "Calibration checks whether predicted probabilities match observed frequencies (reliability curve, Brier score).",
            intuitive:
              "A well-calibrated model means 80% predictions are truly near 80% in reality.",
            reading:
              "If calibration is weak, use probabilities mainly for prioritization/ranking rather than literal percentages."
          },
          shap: {
            title: "4) SHAP — risk explanation",
            precise:
              "SHAP decomposes a single prediction into feature contributions around a baseline risk.",
            intuitive:
              "It shows which parameters pushed risk up or down for this sample.",
            reading:
              "Interpret as model behavior explanation, not as causal proof of contamination source."
          }
        }
      }
    }),
    []
  );
  const t = tr[lang];
  const pushHeaderLang = (nextLang: "ru" | "et" | "en") => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("water.ui.lang", nextLang);
    window.dispatchEvent(new CustomEvent("water-ui-lang-changed", { detail: { lang: nextLang } }));
  };
  const expertModeText =
    lang === "ru"
      ? [
          "Что такое P(violation)",
          "- Это оценка вероятности нарушения санитарных норм для конкретной пробы по её лабораторным признакам.",
          "- Это не прогноз будущего качества воды и не официальный вердикт регулятора.",
          "- При слабой калибровке используйте значение прежде всего для ранжирования приоритетов.",
          "",
          "Что означают модели",
          "- LR (Logistic Regression): линейная модель, переводит взвешенную сумму признаков в вероятность через сигмоиду.",
          "- RF (Random Forest): ансамбль многих деревьев решений; итоговая вероятность — усреднение по деревьям.",
          "- GB (Gradient Boosting): деревья строятся последовательно, каждое исправляет ошибки предыдущих.",
          "- LGBM (LightGBM): быстрый и оптимизированный вариант gradient boosting на деревьях для больших данных.",
          "",
          "Почему вероятности различаются",
          "- Модели имеют разную архитектуру и по-разному обобщают паттерны.",
          "- Разница с RF показывает, насколько модель строже или мягче относительно эталонной RF-оценки.",
          "",
          "О горизонте предсказания",
          "- Предсказание относится к текущей/исторической записи пробы в данных.",
          "- Это не ответ на вопрос 'что будет через неделю/месяц'."
        ].join("\n")
      : lang === "et"
        ? [
          "Mis on P(rikkumine)",
          "- See on konkreetse proovi rikkumise tõenäosuse hinnang laborinäitajate põhjal.",
          "- See ei ole tuleviku vee kvaliteedi prognoos ega ametlik regulatiivne otsus.",
          "",
          "Mida mudelid tähendavad",
          "- LR (Logistic Regression): lineaarne mudel, mis teisendab tunnuste summa tõenäosuseks logistilise funktsiooniga.",
          "- RF (Random Forest): paljude otsustuspuude ansambel; tõenäosus on puude hinnangute keskmine.",
          "- GB (Gradient Boosting): puud ehitatakse järjest, iga järgmine parandab eelmiste vigu.",
          "- LGBM (LightGBM): kiire ja optimeeritud gradient boosting puupõhiste mudelite jaoks.",
          "",
          "Miks tõenäosused erinevad",
          "- Mudelitel on erinev arhitektuur ja erinev üldistusviis.",
          "- RF-iga võrdlus näitab, kas mudel on RF suhtes rangem või leebem.",
          "",
          "Prognoosi ajahorisont",
          "- Hinnang käib praeguse/ajaloolise proovi kirje kohta andmestikus.",
          "- See ei vasta küsimusele, mis juhtub veekvaliteediga järgmisel nädalal või kuul."
        ].join("\n")
        : [
          "What P(violation) means",
          "- It is a model-estimated probability of sanitary norm violation for this specific sample.",
          "- It is not a future forecast and not an official regulatory verdict.",
          "- If calibration is weak, use it primarily for prioritization/ranking.",
          "",
          "What models mean",
          "- LR (Logistic Regression): linear model mapping weighted features into probability via logistic function.",
          "- RF (Random Forest): ensemble of decision trees; final probability is averaged across trees.",
          "- GB (Gradient Boosting): trees are built sequentially, each correcting previous errors.",
          "- LGBM (LightGBM): fast optimized gradient boosting on trees.",
          "",
          "Why probabilities differ",
          "- Models have different inductive biases and generalization behavior.",
          "- Difference vs RF shows whether a model is stricter or softer than RF on the same sample.",
          "",
          "Prediction horizon",
          "- Prediction refers to the current/historical sample record in data.",
          "- It does not answer what will happen to water quality next week or month."
        ].join("\n");
  const renderInfoContent = (text: string) => {
    const lines = String(text || "").split("\n");
    const isRu = text.includes("Что означают модели");
    const isEt = text.includes("Mida mudelid tähendavad");
    const isEn = text.includes("What models mean");
    const showMiniTable = isRu || isEt || isEn;
    const modelRows = showMiniTable
      ? [
          {
            short: "LR",
            full: "Logistic Regression",
            principle: isRu ? "Линейная модель + логистическая функция для вероятности" : isEt ? "Lineaarne mudel + logistiline funktsioon tõenäosuse leidmiseks" : "Linear model + logistic function for probability",
            errorSensitivity: isRu ? "Чувствительна к пропущенным и плохо масштабированным признакам; стабильна на линейных паттернах" : isEt ? "Tundlik puuduvale/skaleerimata sisendile; stabiilne lineaarsete mustrite korral" : "Sensitive to missing/poorly scaled features; stable for linear patterns"
          },
          {
            short: "RF",
            full: "Random Forest",
            principle: isRu ? "Ансамбль решающих деревьев, усредняет оценки" : isEt ? "Otsustuspuude ansambel, mis keskmistab hinnanguid" : "Decision-tree ensemble averaging outputs",
            errorSensitivity: isRu ? "Устойчива к шуму и выбросам, но может сглаживать редкие сигналы" : isEt ? "Vastupidav mürale ja outlier'itele, kuid võib haruldasi signaale siluda" : "Robust to noise/outliers, may smooth rare signals"
          },
          {
            short: "GB",
            full: "Gradient Boosting",
            principle: isRu ? "Последовательные деревья исправляют ошибки предыдущих" : isEt ? "Järjestikused puud parandavad eelmiste mudelite vigu" : "Sequential trees correct previous errors",
            errorSensitivity: isRu ? "Сильнее ловит сложные зависимости, но чувствителен к переобучению без регуляризации" : isEt ? "Tabab keerukaid seoseid, kuid võib ilma regulatsioonita üle õppida" : "Captures complex patterns, but can overfit without regularization"
          },
          {
            short: "LGBM",
            full: "LightGBM",
            principle: isRu ? "Оптимизированный быстрый gradient boosting на деревьях" : isEt ? "Optimeeritud ja kiire puupõhine gradient boosting" : "Fast optimized gradient boosting on trees",
            errorSensitivity: isRu ? "Очень чувствителен к гиперпараметрам; быстрый, но требует контроля overfitting" : isEt ? "Väga tundlik hüperparameetritele; kiire, kuid vajab overfitting'u kontrolli" : "Sensitive to hyperparameters; fast but needs overfitting control"
          }
        ]
      : [];
    return (
      <div className="infoRich">
        {lines.map((line, idx) => {
          const trimmed = line.trim();
          if (!trimmed) return <div key={`i-${idx}`} className="infoSpacer" />;
          if (trimmed.startsWith("- ")) return <div key={`i-${idx}`} className="infoBullet">{trimmed.slice(2)}</div>;
          return <div key={`i-${idx}`} className="infoHeading">{trimmed}</div>;
        })}
        {modelRows.length > 0 ? (
          <div className="infoTableWrap">
            <table className="table infoMiniTable">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Full Name</th>
                  <th>{isRu ? "Принцип" : isEt ? "Põhimõte" : "Principle"}</th>
                  <th>{isRu ? "Чувствительность к ошибкам" : isEt ? "Tundlikkus vigadele" : "Error sensitivity"}</th>
                </tr>
              </thead>
              <tbody>
                {modelRows.map((r) => (
                  <tr key={`mini-${r.short}`}>
                    <td>{r.short}</td>
                    <td>{r.full}</td>
                    <td>{r.principle}</td>
                    <td>{r.errorSensitivity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    );
  };

  const paramInfo: Record<
    string,
    { ruLabel: string; etLabel: string; ruDesc: string; etDesc: string }
  > = {
    e_coli: {
      ruLabel: "E. coli (КОЕ/100 мл)",
      etLabel: "E. coli (PMÜ/100 ml)",
      ruDesc:
        "Ключевой индикатор фекального загрязнения. Если значение повышено, растет риск кишечных инфекций и контактных заболеваний, особенно в открытой воде.",
      etDesc: "Fekaalreostuse indikaator. Kõrged väärtused suurendavad terviseriski."
    },
    enterococci: {
      ruLabel: "Энтерококки",
      etLabel: "Enterokokid",
      ruDesc:
        "Бактериальный индикатор для купальных зон и рекреационной воды. В сочетании с E. coli помогает оценить микробиологическую безопасность.",
      etDesc: "Bakteriaalne veekvaliteedi indikaator, eriti supluskohtades."
    },
    coliforms: {
      ruLabel: "Колиформы",
      etLabel: "Kolibakterid",
      ruDesc:
        "Общий микробиологический индикатор санитарного состояния. Рост колиформ может указывать на проблемы в источнике или системе водоподготовки.",
      etDesc: "Üldine mikrobioloogiline näitaja vee sanitaarseisundi kohta."
    },
    ph: {
      ruLabel: "pH",
      etLabel: "pH",
      ruDesc:
        "Кислотность/щелочность воды. Влияет на коррозию труб, эффективность дезинфекции и комфорт при контакте с водой.",
      etDesc: "Vee happelisus/leelisus. Äärmused viitavad kvaliteediprobleemidele."
    },
    nitrates: {
      ruLabel: "Нитраты",
      etLabel: "Nitraadid",
      ruDesc:
        "Особенно важны для питьевой воды. Повышенные нитраты часто связаны с сельхоз-стоками и требуют усиленного контроля источника.",
      etDesc: "Kõrged nitraaditasemed on eriti kriitilised joogivees."
    },
    nitrites: {
      ruLabel: "Нитриты",
      etLabel: "Nitritid",
      ruDesc:
        "Маркер свежей биозагрязненности и нестабильных процессов азотного цикла. В питьевой воде требует повышенного внимания.",
      etDesc: "Oluline joogivee näitaja, võib viidata värskele bioreostusele."
    },
    ammonium: {
      ruLabel: "Аммоний",
      etLabel: "Ammoonium",
      ruDesc:
        "Повышенный аммоний может указывать на органическое загрязнение или недостаточную очистку. Влияет на вкус/запах и технологичность воды.",
      etDesc: "Kõrgenenud ammoonium võib viidata orgaanilisele reostusele."
    },
    turbidity: {
      ruLabel: "Мутность",
      etLabel: "Hägusus",
      ruDesc:
        "Мутность отражает количество взвешенных частиц. Повышенные значения могут маскировать микробные риски и снижать эффективность обеззараживания.",
      etDesc: "Hägusus halvendab vee visuaalset ja sanitaarset kvaliteeti."
    },
    free_chlorine: {
      ruLabel: "Свободный хлор",
      etLabel: "Vaba kloor",
      ruDesc:
        "Ключевой параметр для бассейнов/SPA: недостаток снижает дезинфекцию, избыток может вызывать раздражение кожи, глаз и дыхательных путей.",
      etDesc: "Basseinides/SPA-des oluline desinfitseerimisnäitaja."
    }
  };

  const labelForParam = (key: string) => {
    const i = paramInfo[key];
    if (!i) return key;
    return lruet(lang, i.ruLabel, i.etLabel, i.ruLabel);
  };

  const descForParam = (key: string) => {
    const i = paramInfo[key];
    if (!i)
      return lruet(
        lang,
        "Лабораторный параметр качества воды. Важность зависит от типа точки (питьевая вода, бассейн, открытая вода) и нормативов.",
        "Laboratoorne veekvaliteedi näitaja. Tähendus sõltub domeenist ja normidest.",
        "Laboratory water quality parameter. Its meaning depends on domain and applicable norms."
      );
    return lruet(lang, i.ruDesc, i.etDesc, i.ruDesc);
  };

  const formatNum = (value: number) => Number(value.toFixed(3)).toString();

  const getNormRule = (param: string, domain: string): NormRule | null => {
    const def = NORM_RULES[param];
    if (!def) return null;
    return (def[domain as DomainKey] ?? def.default ?? null) as NormRule | null;
  };

  const normLabel = (rule: NormRule) => {
    if (typeof rule.exact === "number") return `${lruet(lang, "ровно", "täpselt", "exactly")} ${formatNum(rule.exact)} ${rule.unit}`;
    if (typeof rule.min === "number" && typeof rule.max === "number") {
      return `${formatNum(rule.min)}-${formatNum(rule.max)} ${rule.unit}`;
    }
    if (typeof rule.min === "number") return `>= ${formatNum(rule.min)} ${rule.unit}`;
    if (typeof rule.max === "number") return `<= ${formatNum(rule.max)} ${rule.unit}`;
    return rule.unit;
  };

  const assessNorm = (param: string, value: number, domain: string) => {
    const rule = getNormRule(param, domain);
    if (!rule) return { rule: null, violated: null as boolean | null };
    let violated = false;
    if (typeof rule.exact === "number") violated = value !== rule.exact;
    if (typeof rule.min === "number" && value < rule.min) violated = true;
    if (typeof rule.max === "number" && value > rule.max) violated = true;
    return { rule, violated };
  };

  const explainMeasurementNorm = (param: string, rawValue: number | string, place: FrontendPlace) => {
    const numericValue = typeof rawValue === "number" ? rawValue : Number(rawValue);
    const hasNumeric = Number.isFinite(numericValue);
    const base = descForParam(param);
    const rule = getNormRule(param, place.domain);
    if (!rule || !hasNumeric) {
      return `${base}\n\n${
        lruet(
          lang,
          "Для этого параметра в текущем домене в интерфейсе нет числового норматива.",
          "Selle näitaja jaoks pole antud domeenis liideses numbrilist normi.",
          "No numeric threshold is configured in the UI for this parameter in the current domain."
        )
      }`;
    }
    const verdict = assessNorm(param, numericValue, place.domain).violated;
    const verdictText =
      verdict === null
        ? lruet(lang, "Оценка по норме недоступна.", "Normi hinnang pole saadaval.", "Norm-based evaluation is unavailable.")
        : verdict
          ? lruet(lang, "Статус: ВЫХОД ЗА НОРМУ.", "Staatus: NORMIST VÄLJAS.", "Status: ABOVE THRESHOLD.")
          : lruet(lang, "Статус: в пределах нормы.", "Staatus: normi piires.", "Status: within threshold.");

    return `${base}\n\n${
      lruet(lang, "Норматив для этого домена", "Selle domeeni norm", "Norm for this domain")
    }: ${normLabel(rule)}\n${
      lruet(lang, "Фактическое значение", "Tegelik väärtus", "Actual value")
    }: ${formatNum(numericValue)} ${rule.unit}\n${verdictText}`;
  };

  const explainViolationFromMeasurements = (domain: string, measurements: Record<string, number>) => {
    const entries = Object.entries(measurements || {});
    const unknownNormParams: string[] = [];
    const violations = entries
      .map(([param, value]) => {
        const numericValue = typeof value === "number" ? value : Number(value);
        if (!Number.isFinite(numericValue)) return null;
        const assessed = assessNorm(param, numericValue, domain);
        if (!assessed.rule) {
          unknownNormParams.push(labelForParam(param));
          return null;
        }
        if (assessed.violated !== true) return null;
        return `- ${labelForParam(param)}: ${formatNum(numericValue)} ${assessed.rule.unit} (${lruet(lang, "норма", "norm", "norm")} ${normLabel(assessed.rule)})`;
      })
      .filter((x): x is string => Boolean(x));

    if (violations.length === 0) {
      const noMeasurements = entries.length === 0;
      const unknownPart =
        unknownNormParams.length > 0
          ? `\n${lruet(lang, "Параметры без встроенной нормы", "Parameetrid ilma sisseehitatud normita", "Parameters without built-in norm")}: ${unknownNormParams.slice(0, 6).join(", ")}${unknownNormParams.length > 6 ? "..." : ""}.`
          : "";
      return lruet(
        lang,
        `${noMeasurements ? "Для этой пробы в snapshot нет измерений, поэтому конкретный нарушенный параметр не определён." : "Официально отмечено нарушение, но среди доступных измерений нет явного выхода за встроенные пороги."}\nВозможны отсутствующие показатели, другие нормативы (по типу объекта) или ручная классификация инспектором.${unknownPart}`,
        `${noMeasurements ? "Selle proovi mõõtmised puuduvad snapshotis, seega rikkunud parameetrit ei saa määrata." : "Ametlik rikkumine on märgitud, kuid saadaolevates mõõtmistes ei leitud selget ületust sisseehitatud normide järgi."}${unknownPart}`,
        `${noMeasurements ? "No measurements are exported in snapshot for this sample, so a specific violated parameter cannot be determined." : "Official violation is marked, but available measurements show no explicit exceedance against built-in thresholds."} Missing indicators, other domain-specific norms, or manual inspector classification are possible.${unknownPart}`
      );
    }

    return `${lruet(lang, "Нарушены следующие параметры", "Rikutud parameetrid", "Violated parameters")}:\n${violations.join("\n")}`;
  };

  const explainViolation = (place: FrontendPlace) => explainViolationFromMeasurements(place.domain, place.measurements || {});

  const historyMeasurements = (place: FrontendPlace, idx: number): Record<string, number> => {
    const item = place.sample_history[idx];
    if (!item) return {};
    const direct = item.measurements || {};
    if (Object.keys(direct).length > 0) return direct;

    const itemDay = fmtDate(item.sample_date);
    const currentDay = fmtDate(place.sample_date);
    if (itemDay !== "n/a" && currentDay !== "n/a" && itemDay === currentDay) {
      const current = place.measurements || {};
      if (Object.keys(current).length > 0) return current;
    }

    const sibling = place.sample_history.find(
      (h) => fmtDate(h.sample_date) === itemDay && h.measurements && Object.keys(h.measurements).length > 0
    );
    return sibling?.measurements || {};
  };

  const explainHistoryMeasurements = (place: FrontendPlace, idx: number) => {
    const item = place.sample_history[idx];
    if (!item) return lruet(lang, "Запись истории не найдена.", "Ajaloo kirjet ei leitud.", "History record not found.");
    const rows = Object.entries(historyMeasurements(place, idx))
      .slice(0, 30)
      .map(([k, v]) => `- ${labelForParam(k)}: ${String(v)}`)
      .join("\n");
    if (!rows) return lruet(lang, "Для этой исторической пробы нет экспортированных измерений.", "Selle ajaloolise proovi mõõtmisi pole eksporditud.", "No exported measurements for this historical sample.");
    return `${lruet(lang, "Проба", "Proov", "Sample")}: ${fmtDate(item.sample_date)}\n${lruet(lang, "Показатели воды", "Vee näitajad", "Water measurements")}:\n${rows}`;
  };

  const severityLabel = (level: "good" | "warn" | "bad") => {
    if (lang === "ru") return level === "good" ? "ok" : level === "warn" ? "внимание" : "критично";
    return level === "good" ? "ok" : level === "warn" ? "hoiatus" : "kriitiline";
  };
  const placeKindLabel = (kind: string) => {
    const key = (kind || "other").toLowerCase();
    if (lang === "ru") {
      if (key === "swimming") return "Купальные воды";
      if (key === "pool_spa") return "Бассейн / SPA";
      if (key === "drinking_water") return "Питьевая вода (сеть)";
      if (key === "drinking_source") return "Источник питьевой воды";
      return "Другое";
    }
    if (key === "swimming") return "Suplusvesi";
    if (key === "pool_spa") return "Bassein / SPA";
    if (key === "drinking_water") return "Joogivesi (võrk)";
    if (key === "drinking_source") return "Joogivee allikas";
    return "Muu";
  };

  const openInfo = (title: string, text: string) => {
    setInfoTitle(title);
    setInfoText(text);
    setInfoOpen(true);
  };

  const counties = useMemo(() => {
    const map = new Map<string, string>();
    snapshot.places.forEach((p) => {
      const raw = p.county || "Unknown";
      const key = countyKey(raw) || "unknown";
      if (!map.has(key)) map.set(key, countyPretty(raw) || "Unknown");
    });
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [snapshot.places]);

  const placeKinds = useMemo(() => {
    const vals = new Set<string>();
    snapshot.places.forEach((p) => vals.add(p.place_kind || "other"));
    return Array.from(vals).sort((a, b) => a.localeCompare(b));
  }, [snapshot.places]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return snapshot.places.filter((p) => {
      if (segment !== "all") {
        if (p.place_kind !== segment) return false;
      }
      if (risk !== "all" && p.risk_level !== risk) return false;
      if (county !== "all" && countyKey(p.county || "Unknown") !== county) return false;
      if (official === "compliant" && p.official_compliant !== 1) return false;
      if (official === "violation" && p.official_compliant !== 0) return false;
      if (official === "unknown" && p.official_compliant !== null) return false;
      if (p.model_violation_prob !== null && p.model_violation_prob < minProb) return false;
      if (alertsOnly && !(p.risk_level === "high" || p.official_compliant === 0)) return false;
      if (nearbyOnly && userCoords) {
        if (distanceKm(userCoords.lat, userCoords.lon, p.lat, p.lon) > nearbyRadiusKm) return false;
      }
      if (sampleDateFrom || sampleDateTo) {
        const pointDate = fmtDate(p.sample_date);
        if (pointDate === "n/a") return false;
        if (sampleDateFrom && pointDate < sampleDateFrom) return false;
        if (sampleDateTo && pointDate > sampleDateTo) return false;
      }
      if (q && !p.search_text.includes(q)) return false;
      return true;
    });
  }, [snapshot.places, query, segment, risk, county, official, alertsOnly, nearbyOnly, userCoords, nearbyRadiusKm, minProb, sampleDateFrom, sampleDateTo]);

  useEffect(() => {
    track("dashboard_open", { places_count: snapshot.places_count, has_model: snapshot.has_model_predictions });
  }, [snapshot.places_count, snapshot.has_model_predictions]);

  useEffect(() => {
    pushHeaderLang(lang);
  }, [lang]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("water.ui.lang");
    if (saved === "ru" || saved === "et") {
      setLang(saved);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("water.watchlist.v1");
      if (!raw) return;
      const parsed = JSON.parse(raw) as string[];
      if (Array.isArray(parsed)) {
        setWatchlist(parsed.filter((x) => typeof x === "string"));
      }
    } catch {
      // ignore broken local storage payload
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("water.watchlist.v1", JSON.stringify(watchlist));
  }, [watchlist]);

  useEffect(() => {
    const t = setTimeout(() => setMinProb(minProbInput), 120);
    return () => clearTimeout(t);
  }, [minProbInput]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("water.ui.cyrillic-font.v1");
    if (saved === "ibm" || saved === "manrope") {
      setCyrillicFont(saved);
    }
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.classList.remove("cyr-ibm", "cyr-manrope");
    document.body.classList.add(cyrillicFont === "manrope" ? "cyr-manrope" : "cyr-ibm");
    if (typeof window !== "undefined") {
      window.localStorage.setItem("water.ui.cyrillic-font.v1", cyrillicFont);
    }
  }, [cyrillicFont]);

  useEffect(() => {
    track("filters_changed", {
      segment,
      risk,
      county,
      official,
      alerts_only: alertsOnly,
      nearby_only: nearbyOnly,
      nearby_radius_km: nearbyOnly ? nearbyRadiusKm : null,
      min_prob: Number(minProb.toFixed(2)),
      sample_date_from: sampleDateFrom || null,
      sample_date_to: sampleDateTo || null,
      query_length: query.length,
      visible_count: filtered.length
    });
  }, [segment, risk, county, official, alertsOnly, nearbyOnly, nearbyRadiusKm, minProb, sampleDateFrom, sampleDateTo, query, filtered.length]);

  const low = filtered.filter((x) => x.risk_level === "low").length;
  const high = filtered.filter((x) => x.risk_level === "high").length;
  const violations = filtered.filter((x) => x.official_compliant === 0).length;
  const withModel = filtered.filter((x) => x.model_violation_prob !== null).length;

  const avgProb = useMemo(() => {
    const vals = filtered.map((x) => x.model_violation_prob).filter((v): v is number => v !== null);
    if (!vals.length) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  }, [filtered]);

  const healthIndex = useMemo(() => {
    if (!filtered.length) return 0;
    const officialPassShare = filtered.filter((x) => x.official_compliant === 1).length / filtered.length;
    const modelSafety = avgProb === null ? 0.5 : 1 - avgProb;
    return Math.round((officialPassShare * 0.6 + modelSafety * 0.4) * 100);
  }, [filtered, avgProb]);

  const prognosis = healthIndex >= 80 ? "Excellent" : healthIndex >= 65 ? "Stable" : healthIndex >= 45 ? "Watch closely" : "Critical focus";

  const domainStats = useMemo(() => {
    const counts: Record<string, { total: number; violations: number; highRisk: number }> = {};
    filtered.forEach((p) => {
      const key = p.domain;
      if (!counts[key]) counts[key] = { total: 0, violations: 0, highRisk: 0 };
      counts[key].total += 1;
      if (p.official_compliant === 0) counts[key].violations += 1;
      if (p.risk_level === "high") counts[key].highRisk += 1;
    });
    return Object.entries(counts).sort((a, b) => b[1].total - a[1].total);
  }, [filtered]);

  const topAlerts = useMemo(() => {
    return filtered
      .filter((p) => p.official_compliant === 0 || p.risk_level === "high")
      .sort((a, b) => {
        const ap = a.model_violation_prob ?? (a.risk_level === "high" ? 1 : 0);
        const bp = b.model_violation_prob ?? (b.risk_level === "high" ? 1 : 0);
        return bp - ap;
      })
      .slice(0, 8);
  }, [filtered]);

  const selectedPlace = useMemo(() => {
    if (!selectedId) return null;
    return snapshot.places.find((p) => p.id === selectedId) || null;
  }, [selectedId, snapshot.places]);

  const watchlistPlaces = useMemo(() => {
    const byId = new Set(watchlist);
    return snapshot.places.filter((p) => byId.has(p.id));
  }, [watchlist, snapshot.places]);

  const simulatedProb = useMemo(() => {
    if (!selectedPlace || selectedPlace.model_violation_prob === null) return null;
    const combinedDelta = simDelta + simPressure * 0.08 + simMicro * 0.12;
    return Math.max(0, Math.min(1, selectedPlace.model_violation_prob + combinedDelta));
  }, [selectedPlace, simDelta, simPressure, simMicro]);

  const modelRows = useMemo(() => {
    if (!selectedPlace) return [];
    const rows = [
      { key: "lr", prob: selectedPlace.lr_violation_prob },
      { key: "rf", prob: selectedPlace.rf_violation_prob },
      { key: "gb", prob: selectedPlace.gb_violation_prob },
      { key: "lgbm", prob: selectedPlace.lgbm_violation_prob }
    ];
    return rows.filter((r) => typeof r.prob === "number");
  }, [selectedPlace]);

  const modelRowsFull = useMemo(() => {
    if (!selectedPlace) return [] as Array<{ key: string; prob: number | null }>;
    return [
      { key: "lr", prob: typeof selectedPlace.lr_violation_prob === "number" ? selectedPlace.lr_violation_prob : null },
      { key: "rf", prob: typeof selectedPlace.rf_violation_prob === "number" ? selectedPlace.rf_violation_prob : null },
      { key: "gb", prob: typeof selectedPlace.gb_violation_prob === "number" ? selectedPlace.gb_violation_prob : null },
      { key: "lgbm", prob: typeof selectedPlace.lgbm_violation_prob === "number" ? selectedPlace.lgbm_violation_prob : null }
    ];
  }, [selectedPlace]);

  const modelSpread = useMemo(() => {
    const vals = modelRowsFull.map((r) => r.prob).filter((v): v is number => typeof v === "number");
    if (vals.length < 2) return null;
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    return { min, max, delta: max - min };
  }, [modelRowsFull]);

  const quickInsights = useMemo(() => {
    const coverage = snapshot.diagnostics.model_coverage_share;
    const violation = snapshot.diagnostics.official_violation_share;
    const avg = avgProb;
    return [
      {
        key: "coverage",
        label: lruet(lang, "Покрытие модели", "Mudeli katvus", "Model coverage"),
        value: `${(coverage * 100).toFixed(1)}%`,
        level: coverage >= 0.9 ? "good" : coverage >= 0.6 ? "warn" : "bad",
        hint:
          lang === "ru"
            ? "Доля точек, где есть прогноз ML."
            : "Punktide osakaal, kus ML-prognoos on olemas."
      },
      {
        key: "official_violation",
        label: lruet(lang, "Офиц. нарушения", "Ametlikud rikkumised", "Official violations"),
        value: violation === null ? "n/a" : `${(violation * 100).toFixed(1)}%`,
        level: violation === null ? "warn" : violation <= 0.08 ? "good" : violation <= 0.15 ? "warn" : "bad",
        hint:
          lang === "ru"
            ? "Доля точек с официально зафиксированным нарушением."
            : "Ametliku rikkumisega punktide osakaal."
      },
      {
        key: "avg_model_risk",
        label: lruet(lang, "Средний риск модели", "Keskmine mudelirisk", "Average model risk"),
        value: avg === null ? "n/a" : avg.toFixed(2),
        level: avg === null ? "warn" : avg < 0.35 ? "good" : avg < 0.6 ? "warn" : "bad",
        hint:
          lang === "ru"
            ? "Средняя P(нарушения) по текущему фильтру."
            : "Keskmine P(rikkumine) aktiivse filtri all."
      }
    ] as const;
  }, [snapshot.diagnostics.model_coverage_share, snapshot.diagnostics.official_violation_share, avgProb, lang]);

  const parameterCards = useMemo(
    () => [
      {
        key: "e_coli",
        icon: "🧫",
        ruTitle: "E. coli",
        etTitle: "E. coli",
        ruImpact: "Очень высокий при росте",
        etImpact: "Tõustes väga kõrge",
        ruWhy:
          "Прямой маркер фекального загрязнения. Рост связан с риском кишечных инфекций, особенно в местах купания и рекреации.",
        etWhy:
          "Otsene fekaalreostuse marker. Tõus seostub soolenakkuste riskiga, eriti suplus- ja puhkealadel."
      },
      {
        key: "enterococci",
        icon: "🧪",
        ruTitle: "Enterococci",
        etTitle: "Enterokokid",
        ruImpact: "Высокий для рекреации",
        etImpact: "Kõrge rekreatsioonivees",
        ruWhy:
          "Ключевой микробиологический показатель для пляжей и открытой воды; помогает выявлять санитарные риски до массовых жалоб.",
        etWhy:
          "Oluline mikrobioloogiline näitaja randades ja avavees; aitab sanitaarseid riske varakult märgata."
      },
      {
        key: "ph",
        icon: "⚖️",
        ruTitle: "pH",
        etTitle: "pH",
        ruImpact: "Средний, но системный",
        etImpact: "Keskmine, kuid süsteemne",
        ruWhy:
          "Влияет на коррозию труб, вкус воды и эффективность дезинфекции. Отклонения pH часто указывают на технологические проблемы.",
        etWhy:
          "Mõjutab torude korrosiooni, vee maitset ja desinfitseerimise efektiivsust. pH hälbed viitavad sageli tehnoloogilistele probleemidele."
      },
      {
        key: "nitrates",
        icon: "🌾",
        ruTitle: "Nitrates",
        etTitle: "Nitraadid",
        ruImpact: "Высокий для питьевой воды",
        etImpact: "Kõrge joogivees",
        ruWhy:
          "Связаны с сельхоз-стоками и нагрузкой на водоисточник. Повышенные значения требуют приоритизации мониторинга и источникового контроля.",
        etWhy:
          "Seotud põllumajandusliku äravoolu ja veeallika koormusega. Kõrgenenud väärtused vajavad prioriteetset seiret."
      },
      {
        key: "free_chlorine",
        icon: "🏊",
        ruTitle: "Free chlorine",
        etTitle: "Vaba kloor",
        ruImpact: "Критичный в бассейнах",
        etImpact: "Basseinides kriitiline",
        ruWhy:
          "Недостаток снижает обеззараживание, избыток вызывает раздражение кожи и слизистых. Для бассейнов нужен рабочий диапазон 0.2–0.6 mg/L.",
        etWhy:
          "Liiga madal tase halvendab desinfitseerimist, liiga kõrge põhjustab ärritust. Basseinides on oluline töövahemik 0.2–0.6 mg/L."
      },
      {
        key: "turbidity",
        icon: "🌫️",
        ruTitle: "Turbidity",
        etTitle: "Hägusus",
        ruImpact: "Средний, усиливает другие риски",
        etImpact: "Keskmine, võimendab teisi riske",
        ruWhy:
          "Повышенная мутность может скрывать микробные проблемы и снижать эффективность дезинфекции, ухудшая реальную санитарную картину.",
        etWhy:
          "Kõrge hägusus võib varjata mikroobseid riske ja vähendada desinfitseerimise tõhusust."
      }
    ],
    []
  );

  const toggleWatch = (id: string) => {
    setWatchlist((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const clearFilters = () => {
    setQuery("");
    setSegment("all");
    setRisk("all");
    setCounty("all");
    setOfficial("all");
    setAlertsOnly(false);
    setSampleDateFrom("");
    setSampleDateTo("");
    setMinProb(0);
    setMinProbInput(0);
    setNearbyOnly(false);
    setNearbyRadiusKm(10);
    setGeoError(null);
  };

  const activateNearMe = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoError(t.geoUnsupported);
      return;
    }
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserCoords({ lat: position.coords.latitude, lon: position.coords.longitude });
        setNearbyOnly(true);
      },
      () => {
        setGeoError(t.geoDenied);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  };

  return (
    <div className={`dashboard ${filtersPinned ? "dashboardPinned" : ""}`}>
      <div className="topBar">
        <button className="btn" onClick={() => setDrawerOpen(true)}>
          {t.openFilters}
        </button>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className={`btn ${lang === "ru" ? "btnActive" : ""}`} onClick={() => setLang("ru")}>
            RU
          </button>
          <button className={`btn ${lang === "et" ? "btnActive" : ""}`} onClick={() => setLang("et")}>
            ET
          </button>
          <div className="fontToggle" role="group" aria-label="Cyrillic font switch">
            <button className={`btn btnSmall ${cyrillicFont === "ibm" ? "btnActive" : ""}`} onClick={() => setCyrillicFont("ibm")}>
              IBM
            </button>
            <button className={`btn btnSmall ${cyrillicFont === "manrope" ? "btnActive" : ""}`} onClick={() => setCyrillicFont("manrope")}>
              MAN
            </button>
          </div>
        </div>
      </div>

      {drawerOpen && !filtersPinned ? <div className="drawerBackdrop" onClick={() => setDrawerOpen(false)} /> : null}
      <aside className={`drawer panel ${drawerOpen || filtersPinned ? "open" : ""} ${filtersPinned ? "pinned" : ""}`}>
        <div className="drawerHeader">
          <h3 className="sectionTitle">{t.filters}</h3>
          <div className="drawerHeaderActions">
            <button
              className={`btn btnSmall iconBtn ${filtersPinned ? "btnActive" : ""}`}
              onClick={() => setFiltersPinned((v) => !v)}
              aria-label={filtersPinned ? t.unpin : t.pin}
              title={filtersPinned ? t.unpin : t.pin}
            >
              <span className="btnIcon" aria-hidden="true">
                <Icon name={filtersPinned ? "unpin" : "pin"} />
              </span>
            </button>
            {!filtersPinned ? (
              <button className="btn btnSmall iconBtn" onClick={() => setDrawerOpen(false)} aria-label={t.close} title={t.close}>
                <span className="btnIcon" aria-hidden="true">
                  <Icon name="close" />
                </span>
              </button>
            ) : null}
          </div>
        </div>
        <div className="field">
          <label htmlFor="search-input">{t.search}</label>
          <input
            id="search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={lruet(lang, "например: Tallinn, Harku, rand", "nt Tallinn, Harku, rand", "e.g. Tallinn, Harku, beach")}
            aria-label="Search places by location or county"
          />
        </div>
        <div className="field">
          <label htmlFor="segment-select">{lruet(lang, "Тип точки", "Punkti tüüp", "Point type")}</label>
          <select id="segment-select" value={segment} onChange={(e) => setSegment(e.target.value)} aria-label="Filter by source category">
            <option value="all">all</option>
            {placeKinds.map((k) => (
              <option key={`k-${k}`} value={k}>
                {placeKindLabel(k)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="county-select">{t.county}</label>
          <select id="county-select" value={county} onChange={(e) => setCounty(e.target.value)} aria-label="Filter by county">
            <option value="all">all</option>
            {counties.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="risk-select">{t.risk}</label>
          <select id="risk-select" value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Filter by risk level">
            {riskOrder.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="official-select">{t.official}</label>
          <select id="official-select" value={official} onChange={(e) => setOfficial(e.target.value as (typeof officialOrder)[number])}>
            {officialOrder.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="min-prob">
            {t.minProb}: <b>{minProb.toFixed(2)}</b>
          </label>
          <input
            id="min-prob"
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={minProbInput}
            onInput={(e) => setMinProbInput(Number((e.target as HTMLInputElement).value))}
          />
        </div>
        <div className="field">
          <label>{t.latestSampleDate}</label>
          <div style={{ display: "grid", gap: "0.35rem" }}>
            <input
              type="date"
              value={sampleDateFrom}
              onChange={(e) => setSampleDateFrom(e.target.value)}
              aria-label={t.dateFrom}
            />
            <input
              type="date"
              value={sampleDateTo}
              onChange={(e) => setSampleDateTo(e.target.value)}
              aria-label={t.dateTo}
            />
            <button
              className="btn btnSmall"
              type="button"
              onClick={() => {
                setSampleDateFrom("");
                setSampleDateTo("");
              }}
            >
              {t.resetDate}
            </button>
          </div>
          <p className="hint">{t.latestSampleDateHint}</p>
        </div>
        <div className="filterActionRow">
          <button
            type="button"
            className={`btn alertFocusBtn ${alertsOnly ? "btnActive alertFocusBtnActive" : ""}`}
            onClick={() => setAlertsOnly((v) => !v)}
            aria-pressed={alertsOnly}
          >
            <span className="btnIcon" aria-hidden="true">
              <Icon name="alert" />
            </span>
            {t.alertsOnly}
          </button>
          <button
            type="button"
            className={`btn nearMeBtn ${nearbyOnly ? "btnActive" : ""}`}
            onClick={() => {
              if (nearbyOnly) {
                setNearbyOnly(false);
                setGeoError(null);
                return;
              }
              if (userCoords) {
                setNearbyOnly(true);
                setGeoError(null);
                return;
              }
              activateNearMe();
            }}
            aria-pressed={nearbyOnly}
          >
            <span aria-hidden="true">📍</span>
            {t.nearMe}
          </button>
          {nearbyOnly && userCoords ? (
            <div className="nearbyPanel">
              <label htmlFor="nearby-radius">
                {t.nearRadius}: <b>{nearbyRadiusKm} km</b>
              </label>
              <input
                id="nearby-radius"
                type="range"
                min={1}
                max={50}
                step={1}
                value={nearbyRadiusKm}
                onChange={(e) => setNearbyRadiusKm(Number(e.target.value))}
              />
              <button
                type="button"
                className="btn btnSmall"
                onClick={() => {
                  setUserCoords(null);
                  setNearbyOnly(false);
                  setGeoError(null);
                }}
              >
                {t.clearNearMe}
              </button>
            </div>
          ) : null}
          {geoError ? <p className="hint">{geoError}</p> : null}
          <button type="button" className="btn clearFiltersBtn" onClick={clearFilters}>
            <span className="btnIcon" aria-hidden="true">
              <Icon name="reset" />
            </span>
            {t.clearFilters}
          </button>
        </div>

        <div className="stats">
          <div className="stat">
            <div className="k">{lruet(lang, "Видимых", "Nähtav", "Visible")}</div>
            <div className="v">{filtered.length}</div>
          </div>
          <div className="stat">
            <div className="k">{lruet(lang, "Высокий риск", "Kõrge risk", "High risk")}</div>
            <div className="v">{high}</div>
          </div>
          <div className="stat">
            <div className="k">{lruet(lang, "Низкий риск", "Madal risk", "Low risk")}</div>
            <div className="v">{low}</div>
          </div>
          <div className="stat">
            <div className="k">{lruet(lang, "Офиц. нарушения", "Ametlik rikkumine", "Official violations")}</div>
            <div className="v">{violations}</div>
          </div>
          <div className="stat">
            <div className="k">{lruet(lang, "С моделью", "Mudeli katvus", "With model")}</div>
            <div className="v">{withModel}</div>
          </div>
        </div>

        <div className="panel reportPanel">
          <div className="k">{lruet(lang, "Индекс здоровья", "Tervise indeks", "Health index")}</div>
          <div className={`healthIndex ${healthIndex >= 75 ? "good" : healthIndex >= 50 ? "warn" : "bad"}`}>{healthIndex}/100</div>
          <div className="hint">{lruet(lang, "Прогноз", "Prognoos", "Outlook")}: {prognosis}</div>
          <div className="hint">Avg P(violation): {avgProb === null ? "n/a" : avgProb.toFixed(2)}</div>
        </div>

        <div className="panel reportPanel">
          <h4>Your watchlist</h4>
          {watchlistPlaces.length === 0 ? (
            <p className="hint">
              {lang === "ru"
                ? "Сохраняйте ключевые пляжи, бассейны/SPA и питьевые точки для быстрого мониторинга."
                : "Salvesta olulised supluskohad, basseinid/SPA ja joogiveepunktid kiireks jälgimiseks."}
            </p>
          ) : (
            <ul className="alertList">
              {watchlistPlaces.slice(0, 8).map((p) => (
                <li key={`watch-${p.id}`}>
                  <button className="linkBtn" onClick={() => setSelectedId(p.id)}>
                    {p.location}
                  </button>
                  <span className={`badge ${p.risk_level === "high" ? "bad" : p.risk_level === "medium" ? "warn" : "good"}`}>
                    {p.model_violation_prob !== null ? p.model_violation_prob.toFixed(2) : p.risk_level}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

      </aside>

      <div className="mainContent">
      <section className="panel mapTopPanel">
        <h3 className="sectionTitle">{t.mapTitle}</h3>
        <MapClient
          places={filtered.slice(0, 3000)}
          onSelectPoint={setSelectedId}
          onSelectCounty={(c: string) => setCounty((prev) => (countyKey(prev) === countyKey(c) ? "all" : countyKey(c)))}
          selectedCounty={county !== "all" ? countyPretty(county) : undefined}
          locale={lang}
          selectedPoint={selectedPlace}
          userLocation={nearbyOnly ? userCoords : null}
        />
      </section>

      <section className="panel">
        <h3 className="sectionTitle">{t.selectedPoint}</h3>
        {!selectedPlace ? (
          <p className="hint">{t.noSelectedPoint}</p>
        ) : (
          <div className="pointGrid">
            <div className="panel reportPanel">
              <h4>{selectedPlace.location}</h4>
              <p className="hint">
                {selectedPlace.domain} / {selectedPlace.place_kind}
                <br />
                {t.county}: {countyPretty(selectedPlace.county || "Unknown")}
                <br />
                {lruet(lang, "Проба", "Proov", "Sample")}: {fmtDate(selectedPlace.sample_date)}
                <br />
                {lruet(lang, "Официальный статус", "Ametlik staatus", "Official status")}:{" "}
                {selectedPlace.official_compliant === 1 ? (
                  <span className="badge good">{lruet(lang, "соответствует", "vastab", "compliant")}</span>
                ) : selectedPlace.official_compliant === 0 ? (
                  <button
                    className="linkBtn badge bad"
                    onClick={() =>
                      openInfo(
                        lruet(lang, "Официальное нарушение", "Ametlik rikkumine", "Official violation"),
                        explainViolation(selectedPlace)
                      )
                    }
                  >
                    {lruet(lang, "нарушение", "rikkumine", "violation")}
                  </button>
                ) : (
                  <span className="badge warn">n/a</span>
                )}
                <br />
                ID: {selectedPlace.id}
                <br />
                Coord source: {selectedPlace.coord_source || "n/a"}
                <br />
                {lruet(lang, "Прогноз выбранной модели", "Valitud mudeli prognoos", "Selected model prediction")}:{" "}
                {selectedPlace.model_violation_prob !== null ? selectedPlace.model_violation_prob.toFixed(2) : "n/a"}
                <br />
                LR/RF/GB/LGBM:{" "}
                {[
                  selectedPlace.lr_violation_prob,
                  selectedPlace.rf_violation_prob,
                  selectedPlace.gb_violation_prob,
                  selectedPlace.lgbm_violation_prob
                ]
                  .map((v) => (typeof v === "number" ? v.toFixed(2) : "n/a"))
                  .join(" / ")}
                <br />
                <span className="hint">
                  {lang === "ru"
                    ? "LR = Logistic Regression (линейная вероятностная модель), RF = Random Forest (ансамбль деревьев), GB = Gradient Boosting (деревья последовательно исправляют ошибки), LGBM = LightGBM (быстрый boosting на деревьях)."
                    : "LR = Logistic Regression, RF = Random Forest, GB = Gradient Boosting, LGBM = LightGBM."}
                </span>
              </p>
            </div>
            <div className="panel reportPanel">
              <h4>{t.measurements}</h4>
              {Object.keys(selectedPlace.measurements || {}).length === 0 ? (
                <p className="hint">n/a</p>
              ) : (
                <div className="tableWrap compact">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{lruet(lang, "Показатель", "Näitaja", "Parameter")}</th>
                        <th>{lruet(lang, "Значение", "Väärtus", "Value")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(selectedPlace.measurements)
                        .slice(0, 25)
                        .map(([k, v]) => (
                          <tr key={`m-${k}`}>
                            <td>
                              <button
                                className="linkBtn"
                                onClick={() =>
                                  openInfo(
                                    labelForParam(k),
                                    descForParam(k)
                                  )
                                }
                              >
                                {labelForParam(k)}
                              </button>
                            </td>
                            <td>
                              <button
                                className="linkBtn"
                                onClick={() =>
                                  openInfo(
                                    `${labelForParam(k)}: ${lruet(lang, "норматив", "norm", "norm")}`,
                                    explainMeasurementNorm(k, v, selectedPlace)
                                  )
                                }
                              >
                                {String(v)}
                              </button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="panel reportPanel">
              <h4>{t.history}</h4>
              {selectedPlace.sample_history?.length ? (
                <div className="tableWrap compact">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{lruet(lang, "Дата", "Kuupäev", "Date")}</th>
                        <th>{lruet(lang, "Статус", "Staatus", "Status")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedPlace.sample_history.slice(0, 12).map((h, idx) => (
                        <tr
                          key={`hist-${idx}`}
                          onClick={() => {
                            openInfo(
                              lruet(lang, `История: ${fmtDate(h.sample_date)}`, `Ajalugu: ${fmtDate(h.sample_date)}`, `History: ${fmtDate(h.sample_date)}`),
                              explainHistoryMeasurements(selectedPlace, idx)
                            );
                          }}
                        >
                          <td>{fmtDate(h.sample_date)}</td>
                          <td>
                            {h.official_compliant === 1 ? (
                              <span className="badge good">{lruet(lang, "соответствует", "vastab", "compliant")}</span>
                            ) : h.official_compliant === 0 ? (
                              <button
                                className="linkBtn badge bad"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openInfo(
                                    lruet(lang, "Официальное нарушение (история)", "Ametlik rikkumine (ajalugu)", "Official violation (history)"),
                                    explainViolationFromMeasurements(selectedPlace.domain, historyMeasurements(selectedPlace, idx))
                                  );
                                }}
                              >
                                {lruet(lang, "нарушение", "rikkumine", "violation")}
                              </button>
                            ) : (
                              <span className="badge warn">n/a</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="hint">{t.historyPlaceholder}</p>
              )}
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="tabRow">
          <button className={`tabBtn ${activeTab === "alerts" ? "tabBtnActive" : ""}`} onClick={() => setActiveTab("alerts")}>
            {t.tabs.alerts}
          </button>
          <button className={`tabBtn ${activeTab === "domain" ? "tabBtnActive" : ""}`} onClick={() => setActiveTab("domain")}>
            {t.tabs.domain}
          </button>
          <button className={`tabBtn ${activeTab === "analytics" ? "tabBtnActive" : ""}`} onClick={() => setActiveTab("analytics")}>
            {t.tabs.analytics}
          </button>
          <button className={`tabBtn ${activeTab === "aboutModel" ? "tabBtnActive" : ""}`} onClick={() => setActiveTab("aboutModel")}>
            {t.tabs.aboutModel}
          </button>
          <button className={`tabBtn ${activeTab === "aboutService" ? "tabBtnActive" : ""}`} onClick={() => setActiveTab("aboutService")}>
            {t.tabs.aboutService}
          </button>
        </div>

        {activeTab === "alerts" ? (
          <div className="reportsGrid">
          <div className="panel reportPanel">
            <h4>{lruet(lang, "Центр алертов", "Häirekeskus", "Alert center")}</h4>
            <p className="hint">
              {lang === "ru"
                ? "Жёлтый статус означает недостаток модельных данных или промежуточный риск. Нажмите строку для деталей."
                : "Kollane tähendab kas puuduvaid mudeliandmeid või keskmist riski. Vajuta reale detailideks."}
            </p>
            {topAlerts.length === 0 ? (
              <p className="hint">No active alerts in current filter scope.</p>
            ) : (
              <ul className="alertList">
                {topAlerts.map((p) => (
                  <li key={`alert-${p.id}`}>
                    <button className="linkBtn" onClick={() => setSelectedId(p.id)}>
                      {p.location}
                    </button>
                    <span className={`badge ${p.risk_level === "high" ? "bad" : "warn"}`}>
                      {p.model_violation_prob !== null ? p.model_violation_prob.toFixed(2) : p.risk_level}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="panel reportPanel">
            <h4>Domain health report</h4>
            <div className="tableWrap compact">
              <table className="table">
                <thead>
                  <tr>
                    <th>{lruet(lang, "Домен", "Domeen", "Domain")}</th>
                    <th>Total</th>
                    <th>Viol.</th>
                    <th>High</th>
                  </tr>
                </thead>
                <tbody>
                  {domainStats.map(([d, s]) => (
                    <tr key={`domain-${d}`}>
                      <td>{d}</td>
                      <td>{s.total}</td>
                      <td>{s.violations}</td>
                      <td>{s.highRisk}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          </div>
        ) : null}

        {activeTab === "domain" ? (
          <div className="reportsGrid">
            <div className="panel reportPanel">
              <h4>{lruet(lang, "Отчёт по доменам", "Domeenide aruanne", "Domain report")}</h4>
              <div className="tableWrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{lruet(lang, "Домен", "Domeen", "Domain")}</th>
                      <th>{lruet(lang, "Всего", "Kokku", "Total")}</th>
                      <th>{lruet(lang, "Нарушений", "Rikkumised", "Violations")}</th>
                      <th>{lruet(lang, "Высокий риск", "Kõrge risk", "High risk")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {domainStats.map(([d, s]) => (
                      <tr key={`d2-${d}`}>
                        <td>{d}</td>
                        <td>{s.total}</td>
                        <td>{s.violations}</td>
                        <td>{s.highRisk}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : null}

        {activeTab === "analytics" ? (
          <div className="reportsGrid">
          <div className="panel reportPanel">
            <h4>{lruet(lang, "Сравнение моделей", "Mudelite võrdlus", "Model comparison")}</h4>
            <p className="hint">
              {lruet(
                lang,
                "1) Официальный статус — это поле vastavus из Terviseamet. 2) LR/RF/GB/LGBM — отдельные оценки моделей, они не заменяют официальный статус.",
                "1) Ametlik staatus tuleb Terviseameti vastavus väljast. 2) LR/RF/GB/LGBM on eraldi mudelihinnangud ega asenda ametlikku staatust.",
                "1) Official status comes from Terviseamet `vastavus`. 2) LR/RF/GB/LGBM are separate model estimates and do not replace official status."
              )}
            </p>
            <p className="hint">
              {lruet(
                lang,
                "Формат чтения: P(violation) от 0 до 1. Ближе к 1 — выше риск, ближе к 0 — ниже риск.",
                "Lugemine: P(violation) vahemikus 0 kuni 1. Mida lähemal 1-le, seda kõrgem risk.",
                "Reading: P(violation) ranges from 0 to 1. Closer to 1 means higher risk; closer to 0 means lower risk."
              )}
            </p>
            <div className="infoCardGrid">
              <article className="infoCard">
                <div className="infoCardHead">
                  <span className="infoCardIcon" aria-hidden>🎯</span>
                  <div>
                    <h5>{lruet(lang, "Что именно предсказывается", "Mida mudel ennustab", "What is predicted")}</h5>
                  </div>
                </div>
                <p className="hint">
                  {lruet(
                    lang,
                    "Модель оценивает вероятность нарушения для конкретной пробы по её лабораторным показателям. Это оценка текущей/исторической записи, а не прогноз будущего качества воды.",
                    "Mudel hindab rikkumise tõenäosust konkreetse proovi laborinäitajate põhjal. See on praeguse/ajaloolise kirje hinnang, mitte tuleviku prognoos.",
                    "The model estimates violation probability for a specific sample from its laboratory measurements. This is a current/historical record estimate, not a future water-quality forecast."
                  )}
                </p>
              </article>
              <article className="infoCard">
                <div className="infoCardHead">
                  <span className="infoCardIcon" aria-hidden>📈</span>
                  <div>
                    <h5>{lruet(lang, "Как читать P(violation)", "Kuidas lugeda P(violation)", "How to read P(violation)")}</h5>
                  </div>
                </div>
                <p className="hint">
                  {lruet(
                    lang,
                    "0.80 означает высокий риск по историческим паттернам, а не «80% гарантию» в физическом смысле. При плохой калибровке вероятность лучше использовать как ранжирование приоритетов.",
                    "0.80 tähendab kõrget riski ajalooliste mustrite järgi, mitte füüsikalist „80% garantiid“. Nõrga kalibreerituse korral kasuta väärtust pigem prioriteetide järjestamiseks.",
                    "0.80 means high risk by historical patterns, not a physical '80% guarantee'. With weak calibration, use probability mainly for ranking priorities."
                  )}
                </p>
              </article>
              <article className="infoCard">
                <div className="infoCardHead">
                  <span className="infoCardIcon" aria-hidden>🧪</span>
                  <div>
                    <h5>{lruet(lang, "Почему значения у моделей разные", "Miks mudelid annavad eri väärtusi", "Why model values differ")}</h5>
                  </div>
                </div>
                <p className="hint">
                  {lruet(
                    lang,
                    "LR, RF, GB и LightGBM обучены по-разному, поэтому дают немного разные вероятности. Разница с RF показывает, насколько конкретная модель строже или мягче в оценке риска.",
                    "LR, RF, GB ja LightGBM on erineva loogikaga, seetõttu erinevad ka tõenäosused. RF-iga võrdlus näitab, kas mudel on rangem või leebem riski hindamisel.",
                    "LR, RF, GB, and LightGBM learn differently, so probabilities can differ slightly. Difference vs RF shows whether a model is stricter or softer in risk assessment."
                  )}
                </p>
              </article>
              <article className="infoCard">
                <div className="infoCardHead">
                  <span className="infoCardIcon" aria-hidden>⚖️</span>
                  <div>
                    <h5>{lruet(lang, "Как использовать в решениях", "Kuidas otsustes kasutada", "How to use in decisions")}</h5>
                  </div>
                </div>
                <p className="hint">
                  {lruet(
                    lang,
                    "Официальный статус остаётся первичным. Модельный риск — это ранний индикатор для приоритизации проверок и коммуникации риска, особенно когда Recall важнее пропуска нарушений.",
                    "Ametlik staatus on esmane. Mudelirisk on varajane indikaator kontrollide prioritiseerimiseks ja riskikommunikatsiooniks, eriti kui Recall on olulisem kui möödalaskmised.",
                    "Official status remains primary. Model risk is an early indicator for inspection prioritization and risk communication, especially when high Recall is critical."
                  )}
                </p>
              </article>
            </div>
            <p className="hint">
              {lruet(
                lang,
                "Расшифровка моделей: LR — Logistic Regression (линейная модель), RF — Random Forest (ансамбль деревьев), GB — Gradient Boosting (последовательное усиление), LGBM — LightGBM (оптимизированный boosting на деревьях). Все они оценивают P(violation) по одной и той же пробе, но разными алгоритмами.",
                "Mudelite lühendid: LR, RF, GB, LGBM. Kõik hindavad sama proovi P(rikkumine), kuid erinevate algoritmidega.",
                "Model legend: LR = Logistic Regression, RF = Random Forest, GB = Gradient Boosting, LGBM = LightGBM. All estimate P(violation) for the same sample using different algorithms."
              )}
            </p>
            <div>
              <button
                className="btn btnSmall"
                onClick={() => openInfo(lruet(lang, "Режим эксперта", "Eksperdireziim", "Expert mode"), expertModeText)}
              >
                {lruet(lang, "Подробнее (режим эксперта)", "Rohkem (eksperdireziim)", "More (expert mode)")}
              </button>
            </div>
            {!selectedPlace ? (
              <p className="hint">
                {lruet(lang, "Выберите точку, чтобы сравнить вероятности LR / RF / GB / LightGBM.", "Vali punkt, et võrrelda LR / RF / GB / LightGBM tõenäosusi.", "Select a point to compare LR / RF / GB / LightGBM probabilities.")}
              </p>
            ) : modelRows.length === 0 ? (
              <p className="hint">
                {lruet(lang, "Для этой точки в текущем snapshot нет модельных значений (n/a). Это ожидаемо для сборки с --map-only.", "Selle punkti jaoks pole mudeliprognoose. Koosta snapshot ilma --map-only.", "No model values are available for this point in the current snapshot (n/a). This is expected for --map-only builds.")}
              </p>
            ) : (
              <>
                <div className="tableWrap compact">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{lruet(lang, "Модель", "Mudel", "Model")}</th>
                        <th>
                          <button
                            className="linkBtn"
                            onClick={() =>
                              openInfo(
                                "P(violation)",
                                lruet(
                                  lang,
                                  "P(violation) — оценка вероятности нарушения для конкретной пробы по её показателям. Это не прогноз будущего и не официальный вердикт, а вероятностный риск-скор для приоритизации.",
                                  "P(violation) on rikkumise tõenäosuse hinnang konkreetse proovi näitajate põhjal. See ei ole tuleviku prognoos ega ametlik otsus, vaid riskiskoor prioriteetide seadmiseks.",
                                  "P(violation) is the estimated probability of violation for this sample by model features. It is not a future forecast and not an official verdict; it is a probabilistic risk score for prioritization."
                                )
                              )
                            }
                          >
                            P(violation)
                          </button>
                        </th>
                        <th>{lruet(lang, "Интерпретация", "Tõlgendus", "Interpretation")}</th>
                        <th>{lruet(lang, "Разница с RF", "Erinevus RF-ist", "Difference vs RF")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {modelRowsFull.map((r) => {
                        const rf = modelRowsFull.find((x) => x.key === "rf")?.prob ?? null;
                        const deltaRf = typeof r.prob === "number" && typeof rf === "number" ? r.prob - rf : null;
                        return (
                          <tr key={`model-${r.key}`}>
                            <td>{modelLabelWithPrinciple(snapshot.model_labels?.[r.key] || r.key, lang)}</td>
                            <td>{typeof r.prob === "number" ? r.prob.toFixed(2) : "n/a"}</td>
                            <td>
                              {typeof r.prob === "number"
                                ? r.prob >= 0.7
                                  ? lruet(lang, "высокий риск", "kõrge risk", "high risk")
                                  : r.prob >= 0.4
                                    ? lruet(lang, "средний риск", "keskmine risk", "medium risk")
                                    : lruet(lang, "низкий риск", "madal risk", "low risk")
                                : "n/a"}
                            </td>
                            <td>{deltaRf === null ? "n/a" : `${deltaRf >= 0 ? "+" : ""}${deltaRf.toFixed(2)}`}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="hint">
                  {modelSpread
                    ? lruet(
                        lang,
                        `Разброс между моделями: min=${modelSpread.min.toFixed(2)}, max=${modelSpread.max.toFixed(2)}, delta=${modelSpread.delta.toFixed(2)}. Чем меньше delta, тем больше согласие моделей.`,
                        `Mudelite hajuvus: min=${modelSpread.min.toFixed(2)}, max=${modelSpread.max.toFixed(2)}, delta=${modelSpread.delta.toFixed(2)}. Mida väiksem delta, seda suurem mudelite üksmeel.`,
                        `Model spread: min=${modelSpread.min.toFixed(2)}, max=${modelSpread.max.toFixed(2)}, delta=${modelSpread.delta.toFixed(2)}. Smaller delta means stronger agreement between models.`
                      )
                    : lruet(
                        lang,
                        "Разброс между моделями не рассчитывается: в текущем snapshot недостаточно значений.",
                        "Mudelite hajuvust ei saa arvutada: snapshotis on liiga vähe väärtusi.",
                        "Model spread is unavailable: current snapshot has too few values."
                      )}
                </p>
              </>
            )}
          </div>
          <div className="panel reportPanel">
            <h4>{lruet(lang, "Диагностика + сценарный what-if", "Diagnostika + what-if stsenaarium", "Diagnostics + what-if scenario")}</h4>
            <div className="hint">
              {lruet(lang, "Доля официально соответствующих", "Ametlik vastavus", "Official compliant share")}:{" "}
              <b>{snapshot.diagnostics.official_compliant_share === null ? "n/a" : `${(snapshot.diagnostics.official_compliant_share * 100).toFixed(1)}%`}</b>
              <br />
              {lruet(lang, "Доля официальных нарушений", "Ametlik rikkumine", "Official violation share")}:{" "}
              <b>{snapshot.diagnostics.official_violation_share === null ? "n/a" : `${(snapshot.diagnostics.official_violation_share * 100).toFixed(1)}%`}</b>
              <br />
              {lruet(lang, "Покрытие моделью", "Mudeli katvus", "Model coverage")}: <b>{(snapshot.diagnostics.model_coverage_share * 100).toFixed(1)}%</b>
              <br />
              {snapshot.diagnostics.model_coverage_share === 0
                ? lruet(
                    lang,
                    "Покрытие 0% означает, что текущий экспорт сделан из snapshot без модельных вероятностей.",
                    "0% katvus tähendab, et praegune export on tehtud snapshotist ilma mudeli tõenäosusteta.",
                    "0% coverage means current export was built from a snapshot without model probabilities."
                  )
                : lruet(
                    lang,
                    "Средние значения по моделям ниже показывают общий риск-профиль в текущей выборке.",
                    "Allpool olevad mudelite keskmised näitavad valimi üldist riskiprofiili.",
                    "Average model values below summarize the overall risk profile in the current sample."
                  )}
            </div>
            <div className="tableWrap compact">
              <table className="table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>{lruet(lang, "Средняя P(нарушения)", "Keskmine P(rikkumine)", "Average P(violation)")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(snapshot.diagnostics.mean_model_probabilities || {}).map(([key, val]) => (
                    <tr key={`diag-${key}`}>
                      <td>{modelLabelWithPrinciple(snapshot.model_labels?.[key] || key, lang)}</td>
                      <td>{typeof val === "number" ? val.toFixed(2) : "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <hr />
            <h4>{lruet(lang, "Что можно делать в what-if", "Mida what-if võimaldab", "What you can do in what-if")}</h4>
            {!selectedPlace || selectedPlace.model_violation_prob === null ? (
              <p className="hint">
                {lruet(lang, "Сценарий включается после выбора точки с модельной вероятностью (клик по таблице/алерту/маркеру).", "Stsenaarium töötab pärast mudelitõenäosusega punkti valikut.", "Scenario becomes available after selecting a point with model probability (table/alert/marker click).")}
              </p>
            ) : (
              <>
                <p className="hint">
                  {lruet(lang, "Это не перерасчёт модели по новым анализам, а сценарная оценка чувствительности: как изменится риск при усилении загрязняющего давления или микробиологической нагрузки.", "See ei ole mudeli ümberõpe, vaid tundlikkuse stsenaarium: kuidas risk muutub koormuse kasvul.", "This is not model recalculation from new lab tests; it is a sensitivity scenario showing how risk changes under stronger pollution or microbiological load.")}
                </p>
                <p className="hint">
                  {lang === "ru"
                    ? "Просто: вы двигаете регуляторы и смотрите, как меняется риск. Это учебный сценарий (направление изменения риска), а не официальный новый лабораторный результат."
                    : "Lihtsalt: liigutad liugureid ja näed riski muutust. See on õppeline stsenaarium, mitte uus ametlik laboritulemus."}
                </p>
                <div className="field">
                  <label htmlFor="sim-delta">
                    {lruet(lang, "Базовый сдвиг риска", "Baasriski nihe", "Base risk shift")}: <b>{simDelta >= 0 ? `+${simDelta.toFixed(2)}` : simDelta.toFixed(2)}</b>
                  </label>
                  <input id="sim-delta" type="range" min={-0.5} max={0.5} step={0.01} value={simDelta} onInput={(e) => setSimDelta(Number((e.target as HTMLInputElement).value))} />
                  <p className="hint">
                    {lang === "ru"
                      ? "Ручной общий сдвиг риска: +0.10 добавляет 10 п.п., -0.10 вычитает 10 п.п."
                      : "Käsitsi üldnihe: +0.10 lisab 10 pp, -0.10 vähendab 10 pp."}
                  </p>
                </div>
                <div className="field">
                  <label htmlFor="sim-pressure">
                    {lruet(lang, "Фактор антропогенной нагрузки", "Antropogeense koormuse tegur", "Anthropogenic pressure factor")}: <b>{simPressure.toFixed(1)}</b>
                  </label>
                  <input id="sim-pressure" type="range" min={-2} max={2} step={0.1} value={simPressure} onInput={(e) => setSimPressure(Number((e.target as HTMLInputElement).value))} />
                  <p className="hint">
                    {lang === "ru"
                      ? "Условная внешняя нагрузка (стоки, нагрузка на инфраструктуру, сезон): вклад в риск = фактор × 0.08."
                      : "Tinglik väline koormus: panus riski = tegur × 0.08."}
                  </p>
                </div>
                <div className="field">
                  <label htmlFor="sim-micro">
                    {lruet(lang, "Фактор микробиологических рисков", "Mikrobioloogilise riski tegur", "Microbiological risk factor")}: <b>{simMicro.toFixed(1)}</b>
                  </label>
                  <input id="sim-micro" type="range" min={-2} max={2} step={0.1} value={simMicro} onInput={(e) => setSimMicro(Number((e.target as HTMLInputElement).value))} />
                  <p className="hint">
                    {lang === "ru"
                      ? "Условная микробиологическая нагрузка (например, после осадков): вклад в риск = фактор × 0.12."
                      : "Tinglik mikrobioloogiline koormus: panus riski = tegur × 0.12."}
                  </p>
                </div>
                <p className="hint">
                  {lruet(lang, "Базовая P(нарушения)", "Baas P(rikkumine)", "Base P(violation)")}: <b>{selectedPlace.model_violation_prob.toFixed(2)}</b>
                  <br />
                  {lang === "ru"
                    ? `Суммарный сдвиг сценария: ${((simDelta + simPressure * 0.08 + simMicro * 0.12) >= 0 ? "+" : "") + (simDelta + simPressure * 0.08 + simMicro * 0.12).toFixed(2)}`
                    : `Stsenaariumi kogunihe: ${((simDelta + simPressure * 0.08 + simMicro * 0.12) >= 0 ? "+" : "") + (simDelta + simPressure * 0.08 + simMicro * 0.12).toFixed(2)}`}
                  <br />
                  {lruet(lang, "Сценарная P(нарушения)", "Stsenaariumi P(rikkumine)", "Scenario P(violation)")}: <b>{simulatedProb?.toFixed(2)}</b>
                </p>
              </>
            )}
          </div>
          </div>
        ) : null}

        {activeTab === "aboutModel" ? (
          <div className="reportsGrid">
          <div className="panel reportPanel">
            <h4>{lruet(lang, "О модели", "Mudelist", "About model")}</h4>
            <div className="stats">
              {quickInsights.map((i) => (
                <div className="stat" key={`qi-model-${i.key}`}>
                  <div className="k">{i.label}</div>
                  <div className="v">
                    {i.value} <span className={`badge ${i.level}`}>{severityLabel(i.level)}</span>
                  </div>
                  <div className="hint">{i.hint}</div>
                </div>
              ))}
            </div>
            <p className="hint">
              {lang === "ru"
                ? "Сервис использует ансамбль моделей (LR, Random Forest, Gradient Boosting, LightGBM) для оценки вероятности нарушения санитарных норм по лабораторным параметрам."
                : "Teenus kasutab mudelikomplekti (LR, RF, GB, LightGBM), et hinnata normirikkumise tõenäosust."}
            </p>
            <p className="hint">
              {lang === "ru"
                ? "Важно: это инструмент поддержки решений. Официальным считается статус из данных Terviseamet; ML-прогноз нужен для раннего приоритезационного скрининга."
                : "Oluline: see on otsusetugi, ametlik staatus tuleb Terviseameti andmetest."}
            </p>
            <p className="hint">
              {lang === "ru"
                ? "4 уровня оценки качества: ROC-AUC (разделение классов), Precision/Recall (баланс ошибок), калибровка (доверие к вероятности) и SHAP (пояснение причин прогноза)."
                : "4 hindamistaset: ROC-AUC, Precision/Recall, kalibreeritus ja SHAP selgitused."}
            </p>
            <p className="hint">
              {lruet(lang, "Метрики для чтения качества модели:", "Mõõdikud mudeli hindamiseks:", "Metrics to assess model quality:")}{" "}
              <a href="https://scikit-learn.org/stable/modules/model_evaluation.html" target="_blank" rel="noreferrer" className="linkBtn">
                scikit-learn model evaluation
              </a>
              ,{" "}
              <a href="https://en.wikipedia.org/wiki/Receiver_operating_characteristic" target="_blank" rel="noreferrer" className="linkBtn">
                ROC-AUC
              </a>
              ,{" "}
              <a href="https://en.wikipedia.org/wiki/Precision_and_recall" target="_blank" rel="noreferrer" className="linkBtn">
                Precision/Recall
              </a>
            </p>
            <div className="tableWrap compact">
              <table className="table">
                <thead>
                  <tr>
                    <th>{lruet(lang, "Уровень", "Tase", "Level")}</th>
                    <th>{lruet(lang, "Вопрос", "Küsimus", "Question")}</th>
                    <th>{lruet(lang, "Метрика", "Mõõdik", "Metric")}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>1</td>
                    <td>{lruet(lang, "Разделяет ли модель чистые и рискованные пробы?", "Kas mudel eristab puhtaid ja riskseid proove?", "Does the model separate clean and risky samples?")}</td>
                    <td>ROC-AUC</td>
                  </tr>
                  <tr>
                    <td>2</td>
                    <td>{lruet(lang, "Какие ошибки допускаются?", "Milliseid vigu tehakse?", "What errors are made?")}</td>
                    <td>Precision / Recall</td>
                  </tr>
                  <tr>
                    <td>3</td>
                    <td>{lruet(lang, "Насколько вероятности калиброваны?", "Kui hästi on tõenäosused kalibreeritud?", "How well are probabilities calibrated?")}</td>
                    <td>Calibration</td>
                  </tr>
                  <tr>
                    <td>4</td>
                    <td>{lruet(lang, "Почему получен этот риск?", "Miks just selline risk?", "Why this risk score?")}</td>
                    <td>SHAP</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <h4>{t.metricGuideTitle}</h4>
            <div className="tableWrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>{lruet(lang, "Метрика", "Mõõdik", "Metric")}</th>
                    <th>{lruet(lang, "Точное определение", "Täpne definitsioon", "Precise definition")}</th>
                    <th>{lruet(lang, "Интуитивно", "Intuitsioon", "Intuition")}</th>
                    <th>{lruet(lang, "Как читать значение", "Kuidas väärtust lugeda", "How to read value")}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><b>{t.metricGuide.roc.title}</b></td>
                    <td>{t.metricGuide.roc.precise}</td>
                    <td>{t.metricGuide.roc.intuitive}</td>
                    <td>{t.metricGuide.roc.reading}</td>
                  </tr>
                  <tr>
                    <td><b>{t.metricGuide.pr.title}</b></td>
                    <td>{t.metricGuide.pr.precise}</td>
                    <td>{t.metricGuide.pr.intuitive}</td>
                    <td>{t.metricGuide.pr.reading}</td>
                  </tr>
                  <tr>
                    <td><b>{t.metricGuide.calibration.title}</b></td>
                    <td>{t.metricGuide.calibration.precise}</td>
                    <td>{t.metricGuide.calibration.intuitive}</td>
                    <td>{t.metricGuide.calibration.reading}</td>
                  </tr>
                  <tr>
                    <td><b>{t.metricGuide.shap.title}</b></td>
                    <td>{t.metricGuide.shap.precise}</td>
                    <td>{t.metricGuide.shap.intuitive}</td>
                    <td>{t.metricGuide.shap.reading}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div className="panel reportPanel">
            <p className="hint">
              {lang === "ru"
                ? "Базовые формулы (для понимания):"
                : "Põhivalemid (intuitsiooni jaoks):"}
            </p>
            <div className="tableWrap compact">
              <table className="table">
                <thead>
                  <tr>
                    <th>{lruet(lang, "Метрика", "Mõõdik", "Metric")}</th>
                    <th>{lruet(lang, "Формула", "Valem", "Formula")}</th>
                    <th>{lruet(lang, "Смысл", "Tähendus", "Meaning")}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Precision</td>
                    <td>TP / (TP + FP)</td>
                    <td>{lruet(lang, "Из предсказанных нарушений — сколько реальных", "Prognoositud rikkumistest kui palju on päris", "Of predicted violations, how many are real")}</td>
                  </tr>
                  <tr>
                    <td>Recall</td>
                    <td>TP / (TP + FN)</td>
                    <td>{lruet(lang, "Из всех реальных нарушений — сколько найдено", "Kõigist päris rikkumistest kui palju leiti", "Of all real violations, how many were found")}</td>
                  </tr>
                  <tr>
                    <td>F1</td>
                    <td>2PR / (P + R)</td>
                    <td>{lruet(lang, "Компромисс Precision и Recall", "Tasakaal Precisioni ja Recalli vahel", "Precision/Recall trade-off")}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="tableWrap compact">
              <table className="table">
                <thead>
                  <tr>
                    <th>{lruet(lang, "Формула", "Valem", "Formula")}</th>
                    <th>{lruet(lang, "Интуиция", "Intuitsioon", "Intuition")}</th>
                    <th>{lruet(lang, "Пример из данных", "Näide andmetest", "Example from data")}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Recall = TP / (TP + FN)</td>
                    <td>
                      {lang === "ru"
                        ? "Из всех реальных нарушений сколько модель действительно нашла."
                        : "Kõigist päris rikkumistest kui palju mudel üles leidis."}
                    </td>
                    <td>
                      {lang === "ru"
                        ? "Если Recall=0.95, модель находит ~95 из 100 нарушений."
                        : "Kui Recall=0.95, leitakse ~95 rikkumist 100-st."}
                    </td>
                  </tr>
                  <tr>
                    <td>Precision = TP / (TP + FP)</td>
                    <td>
                      {lang === "ru"
                        ? "Сколько тревог модели оказались реальными нарушениями."
                        : "Kui suur osa mudeli häiretest on päris rikkumised."}
                    </td>
                    <td>
                      {lang === "ru"
                        ? "При Precision=0.80 примерно 8 из 10 алертов подтверждаются."
                        : "Precision=0.80 tähendab, et ~8/10 häirest kinnitub."}
                    </td>
                  </tr>
                  <tr>
                    <td>P(violation)</td>
                    <td>
                      {lang === "ru"
                        ? "Вероятность нарушения для конкретной точки."
                        : "Rikkumise tõenäosus konkreetses punktis."}
                    </td>
                    <td>
                      {avgProb === null
                        ? "n/a"
                        : lang === "ru"
                          ? `Сейчас средняя P(нарушения) по фильтру: ${avgProb.toFixed(2)}.`
                          : `Praegune keskmine P(rikkumine): ${avgProb.toFixed(2)}.`}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="hint">
              {lang === "ru"
                ? "Для water safety важнее высокий Recall (лучше ложная тревога, чем пропущенное нарушение)."
                : "Veeohutuses on Recall prioriteetne (parem valehäire kui märkamata rikkumine)."}
            </p>
          </div>
          </div>
        ) : null}

        {activeTab === "aboutService" ? (
          <div className="reportsGrid">
          <div className="panel reportPanel">
            <h4>{lruet(lang, "О сервисе", "Teenusest", "About service")}</h4>
            <div className="stats">
              {quickInsights.map((i) => (
                <div className="stat" key={`qi-service-${i.key}`}>
                  <div className="k">{i.label}</div>
                  <div className="v">
                    {i.value} <span className={`badge ${i.level}`}>{severityLabel(i.level)}</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="hint">
              {lang === "ru"
                ? "Этот сервис — публичный инструмент экологической прозрачности для жителей, муниципалитетов и госструктур. Он объединяет официальные открытые данные Terviseamet и аналитический ML-слой, чтобы вода оценивалась не только постфактум, но и через ранние риск-сигналы."
                : "See teenus on avalik keskkonnaläbipaistvuse tööriist elanikele, omavalitsustele ja riigiasutustele. See ühendab Terviseameti ametlikud avaandmed ning ML-analüüsi kihi, et veekvaliteeti hinnata nii faktiliselt kui ka varaste riskisignaalide kaudu."}
            </p>
            <p className="hint">
              {lang === "ru"
                ? "По каждой точке доступны: дата и контекст последней пробы, официальный статус соответствия, вероятности нарушения от нескольких моделей, история наблюдений и пояснения ключевых параметров. Такая структура помогает принимать решения на уровне гражданской осведомлённости, муниципального планирования и экологического мониторинга."
                : "Iga punkti kohta kuvatakse: viimase proovi kuupäev ja kontekst, ametlik vastavusstaatus, rikkumise tõenäosused mitmest mudelist, vaatlusajalugu ning võtmeparameetrite selgitused. Selline struktuur toetab nii kodanike teadlikkust, kohaliku tasandi planeerimist kui ka keskkonnaseiret."}
            </p>
            <p className="hint">
              {lang === "ru"
                ? "Важно: модельные оценки не заменяют официальный санитарный вердикт. Они предназначены для приоритезации проверок, более раннего обнаружения потенциально проблемных зон и повышения качества коммуникации между населением и органами контроля."
                : "Oluline: mudelihinnangud ei asenda ametlikku sanitaarset otsust. Need on mõeldud kontrollide prioriseerimiseks, võimalike probleemialade varasemaks avastamiseks ning elanike ja järelevalveasutuste vahelise kommunikatsiooni parandamiseks."}
            </p>
            <p className="hint">
              {lang === "ru"
                ? "Технический слой: официальный статус — поле vastavus в данных Terviseamet. Координаты: сначала справочные точки Terviseamet (coord_source=terviseamet_*, преобразование EPSG:3301 -> WGS84), затем каскад геокодирования Google -> Geoapify -> OpenCage (coord_source=opencage/geocode_cache; в старых снимках возможны google). county_centroid — центроид уезда; approximate_ee — визуальная приблизительная точка в границах Эстонии. Параметры lr/rf/gb/lgbm_violation_prob — прогнозы отдельных ML-моделей, не замена официальной оценке."
                : "Tehniline kiht: ametlik staatus tuleb väljast vastavus. Koordinaadid: esmalt Terviseameti viitepunktid (coord_source=terviseamet_*, teisendus EPSG:3301 -> WGS84), seejärel geokodeerimise kaskaad Google -> Geoapify -> OpenCage (coord_source=opencage/geocode_cache; vanemates snapshotides võimalik google). county_centroid on maakonna tsentroid; approximate_ee on visuaalne ligikaudne punkt Eesti piires. lr/rf/gb/lgbm_violation_prob on eraldi ML-mudelite prognoosid ega asenda ametlikku hinnangut."}
            </p>
            <p className="hint">{snapshot.disclaimer || t.aboutService}</p>
            {snapshot.data_catalog_url ? (
              <p className="hint">
                {lruet(lang, "Источник открытых данных:", "Avaandmete allikas:", "Open data source:")}{" "}
                <a href={snapshot.data_catalog_url} target="_blank" rel="noreferrer" className="linkBtn">
                  {snapshot.data_catalog_url}
                </a>
              </p>
            ) : null}
          </div>
          <div className="panel reportPanel">
            <h4>{lruet(lang, "Слои и интерпретация карты", "Kaardikihid ja tõlgendus", "Map layers and interpretation")}</h4>
            <div className="tableWrap compact">
              <table className="table">
                <thead>
                  <tr>
                    <th>{lruet(lang, "Элемент", "Element", "Element")}</th>
                    <th>{lruet(lang, "Что показывает", "Mida näitab", "What it shows")}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{lruet(lang, "Цвет маркера", "Markeri värv", "Marker color")}</td>
                    <td>{lruet(lang, "Зелёный/жёлтый/красный = низкий/средний/высокий риск", "Roheline/kollane/punane = madal/keskmine/kõrge risk", "Green/yellow/red = low/medium/high risk")}</td>
                  </tr>
                  <tr>
                    <td>{lruet(lang, "Иконка маркера", "Markeri ikoon", "Marker icon")}</td>
                    <td>{lruet(lang, "Тип локации: пляж, бассейн, сеть, источник", "Asukoha tüüp: rand, bassein, võrk, allikas", "Location type: beach, pool, network, source")}</td>
                  </tr>
                  <tr>
                    <td>{lruet(lang, "Кластер", "Klaster", "Cluster")}</td>
                    <td>{lruet(lang, "Количество точек в группе на текущем масштабе", "Punktide arv grupis antud suumitasemel", "Number of points in the group at current zoom")}</td>
                  </tr>
                  <tr>
                    <td>{lruet(lang, "Границы уездов", "Maakonna piirid", "County borders")}</td>
                    <td>{lruet(lang, "Контекст территории и фильтрация по выбранному уезду", "Territooriumi kontekst ja filtreerimine valitud maakonna järgi", "Territory context and filtering by selected county")}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <h4>{lruet(lang, "Нормы по ключевым параметрам (мини-справочник)", "Oluliste näitajate normid (mini-viit)", "Norms for key parameters (mini reference)")}</h4>
            <div className="tableWrap compact">
              <table className="table">
                <thead>
                  <tr>
                    <th>{lruet(lang, "Параметр", "Näitaja", "Parameter")}</th>
                    <th>{lruet(lang, "Купальные воды", "Suplusvesi", "Bathing water")}</th>
                    <th>{lruet(lang, "Питьевая вода", "Joogivesi", "Drinking water")}</th>
                    <th>{lruet(lang, "Бассейн / SPA", "Bassein / SPA", "Pool / SPA")}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>E. coli</td>
                    <td>{lruet(lang, "низко = лучше", "madalam = parem", "lower = better")}</td>
                    <td>{lruet(lang, "почти 0", "peaaegu 0", "near zero")}</td>
                    <td>n/a</td>
                  </tr>
                  <tr>
                    <td>Enterococci</td>
                    <td>{lruet(lang, "контроль микробиологии", "mikrobioloogia kontroll", "microbiology control")}</td>
                    <td>n/a</td>
                    <td>n/a</td>
                  </tr>
                  <tr>
                    <td>pH</td>
                    <td>{lruet(lang, "~нейтральный диапазон", "~neutraalne vahemik", "~neutral range")}</td>
                    <td>6.5-9.5</td>
                    <td>{lruet(lang, "обычно ~7.0-7.8", "tavaliselt ~7.0-7.8", "typically ~7.0-7.8")}</td>
                  </tr>
                  <tr>
                    <td>Nitrates</td>
                    <td>n/a</td>
                    <td>{lruet(lang, "≤ 50 mg/L", "≤ 50 mg/L", "≤ 50 mg/L")}</td>
                    <td>n/a</td>
                  </tr>
                  <tr>
                    <td>Free chlorine</td>
                    <td>n/a</td>
                    <td>n/a</td>
                    <td>0.2-0.6 mg/L</td>
                  </tr>
                  <tr>
                    <td>Turbidity</td>
                    <td>{lruet(lang, "чем ниже, тем лучше", "mida madalam, seda parem", "lower is better")}</td>
                    <td>{lruet(lang, "низкая мутность", "madal hägusus", "low turbidity")}</td>
                    <td>{lruet(lang, "строже в pool-нормах", "pool-normides rangem", "stricter in pool norms")}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="hint">
              {lang === "ru"
                ? "Быстрый вывод: если по точке одновременно высокий риск, красный официальный статус и повышенные микробиологические параметры — это приоритет №1 для контроля."
                : "Kiirjäreldus: kui punktis on koos kõrge risk, punane ametlik staatus ja kõrged mikrobioloogilised näitajad, on see prioriteet nr 1."}
            </p>
            <h4>{lruet(lang, "Карточки параметров: интуиция для исследователя", "Parameetrikaardid: uurija intuitsioon", "Parameter cards: practical intuition")}</h4>
            <div className="infoCardGrid">
              {parameterCards.map((card) => (
                <article key={`pc-${card.key}`} className="infoCard">
                  <div className="infoCardHead">
                    <span className="infoCardIcon" aria-hidden>
                      {card.icon}
                    </span>
                    <div>
                      <h5>{lruet(lang, card.ruTitle, card.etTitle, card.ruTitle)}</h5>
                      <span className="badge warn">
                        {lruet(lang, card.ruImpact, card.etImpact, card.ruImpact)}
                      </span>
                    </div>
                  </div>
                  <p className="hint">{lruet(lang, card.ruWhy, card.etWhy, card.ruWhy)}</p>
                </article>
              ))}
            </div>
          </div>
          </div>
        ) : null}

        <div className="tableWrap">
          <table className="table">
            <thead>
              <tr>
                <th>{lruet(lang, "Локация", "Asukoht", "Location")}</th>
                <th>{lruet(lang, "Уезд", "Maakond", "County")}</th>
                <th>{lruet(lang, "Домен", "Domeen", "Domain")}</th>
                <th>
                  <button
                    className="linkBtn"
                    onClick={() =>
                      openInfo(
                        lruet(lang, "Официальный статус", "Ametlik staatus", "Official status"),
                        lruet(
                          lang,
                          "Зелёный — соответствует нормам, красный — есть официальное нарушение.",
                          "Roheline — vastab normile, punane — ametlik rikkumine.",
                          "Green = compliant, red = official violation."
                        )
                      )
                    }
                  >
                    {lruet(lang, "Официально", "Ametlik", "Official")}
                  </button>
                </th>
                <th>
                  <button
                    className="linkBtn"
                    onClick={() =>
                      openInfo(
                        lruet(lang, "Риск модели", "Mudeli risk", "Model risk"),
                        lruet(
                          lang,
                          "Low/Medium/High — интерпретация вероятности нарушения по ML-модели.",
                          "Low/Medium/High — rikkumise tõenäosuse ML-tõlgendus.",
                          "Low/Medium/High — interpretation of model-estimated violation probability."
                        )
                      )
                    }
                  >
                    {lruet(lang, "Риск", "Risk", "Risk")}
                  </button>
                </th>
                <th>{lruet(lang, "Вероятность", "Tõenäosus", "Probability")}</th>
                <th>{lruet(lang, "Дата", "Kuupäev", "Date")}</th>
                <th>{lruet(lang, "Избранное", "Jälgimine", "Watchlist")}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 250).map((p) => (
                <tr key={p.id} onClick={() => setSelectedId(p.id)} className={selectedId === p.id ? "rowSelected" : ""}>
                  <td>{p.location}</td>
                  <td>{countyPretty(p.county || "Unknown")}</td>
                  <td>{p.domain}</td>
                  <td>
                    {p.official_compliant === 0 ? (
                      <button
                        className="linkBtn badge bad"
                        onClick={(e) => {
                          e.stopPropagation();
                          openInfo(
                            lruet(lang, "Официальное нарушение", "Ametlik rikkumine", "Official violation"),
                            explainViolation(p)
                          );
                        }}
                      >
                        violation
                      </button>
                    ) : (
                      <span className={`badge ${p.official_compliant === 1 ? "good" : "warn"}`}>
                        {p.official_compliant === 1 ? "compliant" : "unknown"}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`badge ${p.risk_level === "high" ? "bad" : p.risk_level === "medium" ? "warn" : "good"}`}>
                      {p.risk_level}
                    </span>
                  </td>
                  <td>{p.model_violation_prob !== null ? p.model_violation_prob.toFixed(2) : "n/a"}</td>
                  <td>{fmtDate(p.sample_date)}</td>
                  <td>
                    <button
                      className="btn btnSmall"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleWatch(p.id);
                      }}
                    >
                      {watchlist.includes(p.id) ? "Unwatch" : "Watch"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      </div>

      {infoOpen ? (
        <div className="modalBackdrop" onClick={() => setInfoOpen(false)}>
          <div className="modalCard panel" onClick={(e) => e.stopPropagation()}>
            <h3 className="sectionTitle">{infoTitle}</h3>
            {renderInfoContent(infoText)}
            <button className="btn btnSmall" onClick={() => setInfoOpen(false)}>
              {t.close}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
