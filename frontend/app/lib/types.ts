export type FrontendPlace = {
  id: string;
  location: string;
  domain: string;
  place_kind: string;
  county: string | null;
  sample_date: string | null;
  official_compliant: number | null;
  coord_source: string | null;
  lat: number;
  lon: number;
  model_violation_prob: number | null;
  lr_violation_prob: number | null;
  rf_violation_prob: number | null;
  gb_violation_prob: number | null;
  lgbm_violation_prob: number | null;
  risk_level: "low" | "medium" | "high" | "unknown";
  has_model_prob: boolean;
  search_text: string;
  measurements_count: number;
  measurements: Record<string, number>;
  sample_history?: Array<{
    sample_date: string;
    official_compliant: number | null;
    measurements?: Record<string, number>;
  }>;
  // AI Act Art 12 provenance (optional — older snapshots may not carry these).
  prediction_id?: string;
  feature_hash?: string;
  model_version?: string;
  created_at?: string;
};

export type FrontendSnapshot = {
  generated_at: string;
  data_fetched_at?: string | null;
  model_trained_at?: string | null;
  has_model_predictions: boolean;
  available_models: string[];
  model_labels: Record<string, string>;
  /** Human-readable name of the model whose probability drives
   *  `risk_level` / marker color on the map (e.g. "LightGBM").
   *  Null on very old snapshots with no per-model columns. */
  canonical_model?: string | null;
  data_catalog_url: string | null;
  disclaimer: string | null;
  places_count: number;
  place_kinds: Record<string, string>;
  domains: string[];
  diagnostics: {
    official_compliant_share: number | null;
    official_violation_share: number | null;
    model_coverage_share: number;
    mean_model_probabilities: Record<string, number | null>;
  };
  places: FrontendPlace[];
  // AI Act Art 12 snapshot-level provenance (optional).
  model_version?: string;
  git_sha?: string | null;
  feature_hash_columns?: string[];
};
