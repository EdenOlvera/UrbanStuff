export const DEMO_LABEL = "Demonstration data — not a scientific simulation.";
export const roles = [
  "unassigned",
  "terrain",
  "building_dsm",
  "surface_dsm",
  "canopy_height",
  "trunk_height",
  "ground_cover",
  "building_footprints",
  "study_boundary",
  "weather",
  "quality_mask",
];
export const roleName = (s: string) =>
  ({
    surface_dsm: "Combined surface DSM",
    building_dsm: "Building & ground DSM",
    terrain: "Bare-earth terrain",
    canopy_height: "Canopy height",
    trunk_height: "Trunk-zone height",
    ground_cover: "Ground cover",
    unassigned: "Assign a role…",
  })[s] || s.replaceAll("_", " ");
export interface Metadata {
  kind: string;
  crs?: string;
  width?: number;
  height?: number;
  resolution?: number[];
  geographic_bounds?: number[];
  bounds?: number[];
  nodata_fraction?: number;
  [key: string]: unknown;
}
export interface Asset {
  id: string;
  filename: string;
  role: string;
  units: string;
  height_reference: string;
  vertical_reference: string;
  source: string;
  nature: string;
  metadata: Metadata;
  checksum: string;
  [key: string]: unknown;
}
export interface Output {
  id: string;
  role: string;
  units: string;
  metadata: Metadata;
  filename: string;
  synthetic: boolean;
}
export interface Job {
  id: string;
  state: string;
  progress: number;
  logs: string[];
  config: Config;
  created_at: string;
  manifest?: { outputs: Output[]; label: string; [key: string]: unknown };
}
export interface Project {
  id: string;
  name: string;
  created_at: string;
  assets: Asset[];
  jobs: Job[];
  study_area?: { reporting: GeoJSON.Geometry; processing: GeoJSON.Geometry };
  grid?: unknown;
}
export interface Config {
  engine: "demo" | "umep";
  air_temperature: number;
  solar_altitude: number;
  vegetation: string;
  timezone: string;
  weather_asset_id: string | null;
  baseline_configuration_id?: string | null;
  input_overrides?: Record<string, string>;
}
export interface Finding {
  severity: string;
  code: string;
  message: string;
  remedy: string;
  asset_id?: string;
}
export interface Report {
  valid: boolean;
  findings: Finding[];
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch("/api" + path, init);
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  }
  return res.json();
}
export const json = (data: unknown, method = "POST") => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});
