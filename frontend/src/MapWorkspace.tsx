import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { Project, Output, Asset } from "./types";
import { api, DEMO_LABEL } from "./types";
import { Crosshair, Plus, Minus, Check, X, MapPin } from "lucide-react";
import "maplibre-gl/dist/maplibre-gl.css";
interface Props {
  project: Project | null;
  selected: Asset | Output | null;
  jobId: string | null;
  visible: boolean;
  opacity: number;
  draw: boolean;
  onDraw: (g: GeoJSON.Polygon) => void;
  onStopDraw: () => void;
}
export default function MapWorkspace({
  project,
  selected,
  jobId,
  visible,
  opacity,
  draw,
  onDraw,
  onStopDraw,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [pixel, setPixel] = useState<string>(
    "Click a raster to inspect a pixel",
  );
  const [coords, setCoords] = useState("48.104° N  ·  11.566° E");
  const [mapError, setMapError] = useState("");
  const points = useRef<number[][]>([]);
  const state = useRef({ project, selected, jobId, draw });
  state.current = { project, selected, jobId, draw };
  const updateDraw = () => {
    const m = map.current;
    if (!m) return;
    const p = points.current;
    const g: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features:
        p.length > 1
          ? [
              {
                type: "Feature",
                properties: {},
                geometry:
                  p.length > 2
                    ? { type: "Polygon", coordinates: [[...p, p[0]]] }
                    : { type: "LineString", coordinates: p },
              },
            ]
          : [],
    };
    (m.getSource("drawing") as maplibregl.GeoJSONSource)?.setData(g);
  };
  useEffect(() => {
    if (!container.current) return;
    let m: maplibregl.Map;
    try {
      m = new maplibregl.Map({
        container: container.current,
        style: {
          version: 8,
          sources: {},
          layers: [
            {
              id: "background",
              type: "background",
              paint: { "background-color": "#e7ebe2" },
            },
          ],
        },
        center: [11.566, 48.104],
        zoom: 14,
        attributionControl: false,
      });
    } catch (e) {
      setMapError(String(e));
      return;
    }
    map.current = m;
    m.on("load", () => {
      m.addSource("boundary", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "boundary-fill",
        type: "fill",
        source: "boundary",
        paint: { "fill-color": "#355f50", "fill-opacity": 0.05 },
      });
      m.addLayer({
        id: "boundary-line",
        type: "line",
        source: "boundary",
        paint: {
          "line-color": "#355f50",
          "line-width": 2,
          "line-dasharray": [3, 2],
        },
      });
      m.addSource("drawing", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "drawing",
        type: "line",
        source: "drawing",
        paint: { "line-color": "#c67739", "line-width": 3 },
      });
      setReady(true);
    });
    m.on("mousemove", (e) =>
      setCoords(
        `${e.lngLat.lat.toFixed(5)}° N  ·  ${e.lngLat.lng.toFixed(5)}° E`,
      ),
    );
    m.on("click", async (e) => {
      const s = state.current;
      if (s.draw) {
        points.current.push([e.lngLat.lng, e.lngLat.lat]);
        updateDraw();
        return;
      }
      if (!s.project || !s.selected) return;
      const prefix = s.jobId
        ? `/projects/${s.project.id}/jobs/${s.jobId}/outputs/${s.selected.id}`
        : `/projects/${s.project.id}/assets/${s.selected.id}`;
      try {
        const p = await api<{ value: number | null; units?: string }>(
          `${prefix}/pixel?lon=${e.lngLat.lng}&lat=${e.lngLat.lat}`,
        );
        setPixel(
          p.value === null
            ? "No data at this location"
            : `${p.value.toFixed(2)} ${p.units || ("units" in s.selected ? s.selected.units : "")}`,
        );
      } catch (e) {
        setPixel(String(e));
      }
    });
    m.on("error", (e) => setMapError(e.error.message));
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    points.current = [];
    updateDraw();
    if (map.current)
      map.current.getCanvas().style.cursor = draw ? "crosshair" : "";
  }, [draw]);
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("boundary") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: project?.study_area
        ? [
            {
              type: "Feature",
              properties: {},
              geometry: project.study_area.processing,
            },
            {
              type: "Feature",
              properties: {},
              geometry: project.study_area.reporting,
            },
          ]
        : [],
    });
  }, [project?.study_area, ready]);
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    if (m.getLayer("raster")) m.removeLayer("raster");
    if (m.getSource("raster")) m.removeSource("raster");
    setPixel("Click a raster to inspect a pixel");
    const b = selected?.metadata.geographic_bounds;
    if (!selected || !project || !b) return;
    const prefix = jobId
      ? `/api/projects/${project.id}/jobs/${jobId}/outputs/${selected.id}`
      : `/api/projects/${project.id}/assets/${selected.id}`;
    m.addSource("raster", {
      type: "image",
      url: prefix + "/preview.png",
      coordinates: [
        [b[0], b[3]],
        [b[2], b[3]],
        [b[2], b[1]],
        [b[0], b[1]],
      ],
    });
    m.addLayer(
      {
        id: "raster",
        type: "raster",
        source: "raster",
        paint: { "raster-opacity": opacity, "raster-fade-duration": 0 },
      },
      "boundary-fill",
    );
    m.fitBounds(
      [
        [b[0], b[1]],
        [b[2], b[3]],
      ],
      { padding: 100, duration: 600 },
    );
  }, [selected?.id, project?.id, jobId, ready]);
  useEffect(() => {
    const m = map.current;
    if (m?.getLayer("raster")) {
      m.setLayoutProperty("raster", "visibility", visible ? "visible" : "none");
      m.setPaintProperty("raster", "raster-opacity", opacity);
    }
  }, [visible, opacity, ready, selected?.id]);
  return (
    <div className="map-workspace">
      <div ref={container} className="map-canvas" />
      <div className="map-grid" />
      <div className="map-top">
        <span className="map-tag">
          <span className="dot" />{" "}
          {selected
            ? "filename" in selected
              ? selected.filename
              : "Raster view"
            : "Study area workspace"}
        </span>
        <span className="map-tag subtle">Blank basemap · no API key</span>
      </div>
      {!selected && !draw && (
        <div className="map-empty">
          <div className="empty-symbol">
            <MapPin size={30} />
          </div>
          <h2>Your study starts here</h2>
          <p>
            Define an area, bring in your data,
            <br />
            and explore the urban climate.
          </p>
          <span>GeoTIFF · GeoJSON · Weather CSV</span>
        </div>
      )}
      {mapError && (
        <div className="map-error">
          Map: {mapError}. Metadata and downloads remain available.
        </div>
      )}
      {draw && (
        <div className="draw-tip">
          Click to add polygon vertices{" "}
          <button
            onClick={() => {
              if (points.current.length >= 3) {
                onDraw({
                  type: "Polygon",
                  coordinates: [[...points.current, points.current[0]]],
                });
                onStopDraw();
              }
            }}
          >
            <Check size={14} /> Finish polygon
          </button>
          <button onClick={onStopDraw}>
            <X size={14} />
          </button>
        </div>
      )}
      <div className="map-tools">
        <button title="Zoom in" onClick={() => map.current?.zoomIn()}>
          <Plus size={18} />
        </button>
        <button title="Zoom out" onClick={() => map.current?.zoomOut()}>
          <Minus size={18} />
        </button>
        <button
          title="Fit selected layer"
          onClick={() => {
            const b = selected?.metadata.geographic_bounds;
            if (b)
              map.current?.fitBounds(
                [
                  [b[0], b[1]],
                  [b[2], b[3]],
                ],
                { padding: 80 },
              );
          }}
        >
          <Crosshair size={18} />
        </button>
      </div>
      {selected && (
        <div className="legend">
          <b>
            {"role" in selected ? selected.role.replaceAll("_", " ") : "Raster"}
          </b>
          <div className="legend-gradient" />
          <div className="legend-labels">
            <span>Low</span>
            <span>{selected.units || "unknown units"}</span>
            <span>High</span>
          </div>
          <small>Preview: 2nd–98th percentile · transparent NoData</small>
          {("synthetic" in selected
            ? selected.synthetic === true
            : selected.nature === "synthetic") && <em>{DEMO_LABEL}</em>}
        </div>
      )}
      <div className="map-bottom">
        <span>{coords}</span>
        <span>{pixel}</span>
        <span>WGS 84 · display CRS</span>
      </div>
    </div>
  );
}
