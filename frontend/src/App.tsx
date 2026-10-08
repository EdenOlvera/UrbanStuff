import { useState, useEffect, useCallback } from "react";
import {
  Layers,
  Leaf,
  ChevronDown,
  ChevronRight,
  Plus,
  FolderOpen,
  MapPin,
  Upload,
  ShieldCheck,
  Sun,
  ChartNoAxesCombined,
  ArrowUpRight,
  Play,
  Download,
  Eye,
  EyeOff,
  Check,
  Info,
  Activity,
  FileText,
  Settings2,
  X,
  LoaderCircle,
  Copy,
} from "lucide-react";
import MapWorkspace from "./MapWorkspace";
import { api, json, DEMO_LABEL, roles, roleName } from "./types";
import type { Project, Asset, Output, Job, Config, Report } from "./types";
const stages = [
  { name: "Study area", icon: MapPin },
  { name: "Data", icon: Layers },
  { name: "Validation", icon: ShieldCheck },
  { name: "Simulation", icon: Sun },
  { name: "Results", icon: ChartNoAxesCombined },
];
const initial: Config = {
  engine: "demo",
  air_temperature: 25,
  solar_altitude: 45,
  vegetation: "unknown",
  timezone: "UTC",
  weather_asset_id: null,
};
export default function App() {
  const [projects, setProjects] = useState<Project[]>([]),
    [project, setProject] = useState<Project | null>(null),
    [stage, setStage] = useState(0),
    [selected, setSelected] = useState<Asset | Output | null>(null),
    [jobId, setJobId] = useState<string | null>(null),
    [visible, setVisible] = useState(true),
    [opacity, setOpacity] = useState(0.85),
    [draw, setDraw] = useState(false),
    [config, setConfig] = useState<Config>(initial),
    [report, setReport] = useState<Report | null>(null),
    [cap, setCap] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(""),
    [modal, setModal] = useState(false),
    [name, setName] = useState(""),
    [summary, setSummary] = useState<any>(null),
    [showLogs, setShowLogs] = useState(true),
    [processLog, setProcessLog] = useState(""),
    [weatherKind, setWeatherKind] = useState("observed");
  const base = project ? `/projects/${project.id}` : "";
  const currentJob =
    project?.jobs.find((j) => j.id === jobId) || project?.jobs[0];
  const refresh = useCallback(async (id: string) => {
    const p = await api<Project>(`/projects/${id}`);
    setProject(p);
    return p;
  }, []);
  useEffect(() => {
    api<Project[]>("/projects")
      .then(async (p) => {
        setProjects(p);
        if (p.length) await refresh(p[0].id);
      })
      .catch((e) => setError(e.message));
    api("/capabilities")
      .then(setCap)
      .catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    if (!project?.jobs.some((j) => ["queued", "running"].includes(j.state)))
      return;
    const timer = setInterval(
      () => refresh(project.id).catch((e) => setError(e.message)),
      800,
    );
    return () => clearInterval(timer);
  }, [project?.id, project?.jobs, refresh]);
  useEffect(() => {
    if (!project || !selected || !jobId) return;
    api(`${base}/jobs/${jobId}/outputs/${selected.id}/summary`)
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [selected?.id, jobId, base]);
  async function task(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }
  async function create() {
    await task("Creating project", async () => {
      const p = await api<Project>("/projects", json({ name }));
      await refresh(p.id);
      setProjects(await api("/projects"));
      setSelected(null);
      setJobId(null);
      setStage(0);
      setModal(false);
      setName("");
      setReport(null);
    });
  }
  async function upload(file: File) {
    await task("Inspecting upload", async () => {
      const form = new FormData();
      form.append("file", file);
      form.append("timezone", config.timezone);
      form.append("weather_kind", weatherKind);
      const a = await api<Asset>(base + "/assets", {
        method: "POST",
        body: form,
      });
      await refresh(project!.id);
      setSelected(a);
      setJobId(null);
      setReport(null);
    });
  }
  async function fixture() {
    await task("Generating fixture", async () => {
      const a = await api<Asset>(base + "/demo-fixture", { method: "POST" });
      await refresh(project!.id);
      setSelected(a);
      setJobId(null);
      setStage(1);
      setReport(null);
    });
  }
  async function declaration(a: Asset, changes: Partial<Asset>) {
    await task("Saving declaration", async () => {
      const updated = await api<Asset>(
        base + "/assets/" + a.id,
        json({ ...a, ...changes }, "PUT"),
      );
      await refresh(project!.id);
      setSelected(updated);
      setReport(null);
    });
  }
  async function saveBoundary(
    geometry: GeoJSON.Geometry,
    processing?: GeoJSON.Geometry,
  ) {
    await task("Saving boundary", async () => {
      await api(
        base + "/study-area",
        json(
          { reporting: geometry, processing: processing || geometry },
          "PUT",
        ),
      );
      await refresh(project!.id);
      setReport(null);
    });
  }
  async function boundaryFile(file: File) {
    await task("Reading boundary", async () => {
      const value = JSON.parse(await file.text());
      const g = value.type === "Feature" ? value.geometry : value;
      const processing = value.processing;
      await api(
        base + "/study-area",
        json({ reporting: g, processing: processing || g }, "PUT"),
      );
      await refresh(project!.id);
    });
  }
  async function validate() {
    await task("Validating inputs", async () => {
      setReport(await api<Report>(base + "/validate", json(config)));
      setStage(2);
    });
  }
  async function submit() {
    await task("Submitting job", async () => {
      const j = await api<Job>(base + "/jobs", json(config));
      setJobId(j.id);
      setSelected(null);
      await refresh(project!.id);
      setStage(3);
    });
  }
  function selectAsset(a: Asset) {
    setSelected(a);
    setJobId(null);
    setSummary(null);
    setVisible(true);
  }
  function selectOutput(o: Output, j: Job) {
    setSelected(o);
    setJobId(j.id);
    setVisible(true);
    setStage(4);
  }
  const inputSelected = selected && !jobId ? (selected as Asset) : null;
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Layers size={24} />
          </div>
          <div>
            UMEP <b>Studio</b>
            <small>URBAN CLIMATE WORKSPACE</small>
          </div>
        </div>
        <div className="workspace-label">
          WORKSPACE <span>LOCAL</span>
        </div>
        <button className="project-switch" onClick={() => setModal(true)}>
          <FolderOpen size={18} />
          <span>
            {project?.name || "Create your first project"}
            <small>
              {project ? "Geospatial project" : "Get started with UMEP Studio"}
            </small>
          </span>
          <ChevronDown size={16} />
        </button>
        {projects.length > 1 && (
          <select
            className="project-select"
            value={project?.id || ""}
            onChange={(e) =>
              task("Loading project", async () => {
                await refresh(e.target.value);
                setSelected(null);
                setJobId(null);
                setReport(null);
                setStage(0);
              })
            }
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        <div className="nav-label">PROJECT WORKFLOW</div>
        <nav>
          {stages.map((s, i) => (
            <button
              key={s.name}
              className={stage === i ? "active" : ""}
              onClick={() => setStage(i)}
            >
              <s.icon size={18} />
              <span>{s.name}</span>
              <span className="nav-number">0{i + 1}</span>
            </button>
          ))}
        </nav>
        <div className="layer-heading">
          LAYERS <span>{project?.assets.length || 0}</span>
          <button title="Upload layer" onClick={() => setStage(1)}>
            <Plus size={16} />
          </button>
        </div>
        <div className="layer-list">
          {project?.assets.length ? (
            project.assets.map((a) => (
              <button
                key={a.id}
                className={
                  selected?.id === a.id && !jobId ? "layer selected" : "layer"
                }
                onClick={() => selectAsset(a)}
              >
                <span
                  className={
                    "layer-swatch " +
                    (a.nature === "synthetic" ? "synthetic" : "")
                  }
                />
                <span>
                  {a.filename}
                  <small>{roleName(a.role)}</small>
                </span>
                <Layers size={13} />
              </button>
            ))
          ) : (
            <div className="layer-empty">
              <Layers size={23} />
              <p>No layers yet</p>
              <small>Upload data or load the demo fixture.</small>
            </div>
          )}
        </div>
        {selected && (
          <div className="layer-controls">
            <button onClick={() => setVisible(!visible)}>
              {visible ? <Eye size={15} /> : <EyeOff size={15} />}{" "}
              {visible ? "Visible" : "Hidden"}
            </button>
            <label>
              Opacity <b>{Math.round(opacity * 100)}%</b>
              <input
                aria-label="Layer opacity"
                type="range"
                min="0"
                max="1"
                step=".05"
                value={opacity}
                onChange={(e) => setOpacity(+e.target.value)}
              />
            </label>
          </div>
        )}
        <button className="new-project" onClick={() => setModal(true)}>
          <Plus size={16} /> New project
        </button>
        <div className="sidebar-bottom">
          <div className="avatar">US</div>
          <div>
            Local environment
            <small>
              <span className="dot" /> {cap ? "API connected" : "Connecting…"}
            </small>
          </div>
          <Settings2 size={17} />
        </div>
      </aside>
      <div className="main">
        <header>
          <div className="breadcrumb">
            Projects <ChevronRight size={13} />{" "}
            <b>{project?.name || "New workspace"}</b>
          </div>
          <div className="header-right">
            <span className="local-badge">
              <span className="dot" /> Local development
            </span>
            <button title="Create project" onClick={() => setModal(true)}>
              <Plus size={17} />
            </button>
          </div>
        </header>
        <div className="page-heading">
          <div>
            <div className="eyebrow">
              PROJECT / {String(stage + 1).padStart(2, "0")}
            </div>
            <h1>{stages[stage].name}</h1>
            <p>
              {
                [
                  "Set the spatial context for your simulation.",
                  "Bring your geospatial inputs into one workspace.",
                  "Understand your data before you run.",
                  "Configure and run your urban climate analysis.",
                  "Explore the outputs, trace the provenance.",
                ][stage]
              }
            </p>
          </div>
          <span className="model-tag">
            <Sun size={17} /> SOLWEIG <span>shade & radiant temperature</span>
          </span>
        </div>
        <div className="stepbar">
          {stages.map((s, i) => (
            <button
              key={s.name}
              className={stage === i ? "current" : ""}
              onClick={() => setStage(i)}
            >
              <span className="step-circle">
                {(i === 0 && project?.study_area) ||
                (i === 1 && project?.assets.length) ||
                (i === 2 && report?.valid) ? (
                  <Check size={13} />
                ) : (
                  i + 1
                )}
              </span>
              {s.name}
              {i < 4 && <ChevronRight size={14} />}
            </button>
          ))}
        </div>
        {error && (
          <div role="alert" className="error-banner">
            <Info size={16} />
            <span>{error}</span>
            <button onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        <div className="workbench">
          <MapWorkspace
            project={project}
            selected={selected}
            jobId={jobId}
            visible={visible}
            opacity={opacity}
            draw={draw}
            onDraw={(g) => saveBoundary(g)}
            onStopDraw={() => setDraw(false)}
          />
          <section className="panel">
            <div className="panel-title">
              <span>
                {stages[stage].name === "Study area"
                  ? "Define your study area"
                  : stages[stage].name}
              </span>
              <span className="panel-icon">
                <Settings2 size={16} />
              </span>
            </div>
            {!project ? (
              <div className="panel-content">
                <div className="panel-illustration">
                  <FolderOpen size={32} />
                </div>
                <h2>A place for your analysis</h2>
                <p>
                  Create a project to organize your boundary, datasets, and
                  simulation runs.
                </p>
                <button className="primary wide" onClick={() => setModal(true)}>
                  <Plus size={16} /> Create project
                </button>
                <div className="note">
                  <Info size={16} />
                  <span>
                    Everything is stored locally. No cloud account or map API
                    key is required.
                  </span>
                </div>
              </div>
            ) : (
              <div className="panel-content">
                {stage === 0 && (
                  <>
                    <div className="section-index">01 / SPATIAL EXTENT</div>
                    <h2>Start with a boundary</h2>
                    <p>
                      Choose the area you want to report on. Include surrounding
                      context in your processing boundary.
                    </p>
                    <button
                      className="primary wide"
                      onClick={() => setDraw(!draw)}
                    >
                      <MapPin size={16} />
                      {draw ? "Cancel drawing" : "Draw on map"}
                    </button>
                    <label className="secondary wide file-button">
                      <Upload size={16} /> Upload GeoJSON
                      <input
                        type="file"
                        accept=".json,.geojson"
                        onChange={(e) => {
                          if (e.target.files?.[0])
                            boundaryFile(e.target.files[0]);
                          e.target.value = "";
                        }}
                      />
                    </label>
                    <div className="divider">
                      <span>BOUNDARY STATUS</span>
                    </div>
                    <div className="detail-row">
                      <span>Reporting boundary</span>
                      <b>{project.study_area ? "Defined" : "Not defined"}</b>
                    </div>
                    <div className="detail-row">
                      <span>Processing boundary</span>
                      <b>{project.study_area ? "Defined" : "Not defined"}</b>
                    </div>
                    <div className="note">
                      <Info size={16} />
                      <span>
                        Drawing sets both boundaries to the same polygon. Upload
                        a GeoJSON geometry with a <code>processing</code>{" "}
                        polygon to include a larger buffer.
                      </span>
                    </div>
                    <div className="divider">
                      <span>QUICK START</span>
                    </div>
                    <div className="demo-card">
                      <span className="mini-label">DEMONSTRATION</span>
                      <h3>Explore a sample district</h3>
                      <p>
                        A small synthetic surface raster to try the full
                        workflow.
                      </p>
                      <button onClick={fixture} disabled={!!busy}>
                        Load demo dataset <ArrowUpRight size={15} />
                      </button>
                    </div>
                    <button className="text-action" onClick={() => setStage(1)}>
                      Continue to data <ChevronRight size={16} />
                    </button>
                  </>
                )}
                {stage === 1 && (
                  <>
                    <div className="section-index">02 / INPUT DATA</div>
                    <h2>Bring in your layers</h2>
                    <p>
                      Upload a GeoTIFF, weather CSV, or register a LAS/LAZ file.
                      Declare what the data represents.
                    </p>
                    <div className="field-grid">
                      <label className="field">
                        Weather classification
                        <select
                          value={weatherKind}
                          onChange={(e) => setWeatherKind(e.target.value)}
                        >
                          <option value="observed">Observed</option>
                          <option value="typical-year">Typical year</option>
                          <option value="hypothetical">Hypothetical</option>
                        </select>
                      </label>
                      <label className="field">
                        CSV timezone
                        <input
                          value={config.timezone}
                          onChange={(e) =>
                            setConfig({ ...config, timezone: e.target.value })
                          }
                        />
                      </label>
                    </div>
                    <label className="upload-zone">
                      <Upload size={24} />
                      <b>Choose a file to upload</b>
                      <span>GeoTIFF · CSV · LAS / LAZ · 100 MB default</span>
                      <input
                        type="file"
                        accept=".tif,.tiff,.csv,.las,.laz"
                        onChange={(e) => {
                          if (e.target.files?.[0]) upload(e.target.files[0]);
                          e.target.value = "";
                        }}
                      />
                    </label>
                    {inputSelected ? (
                      <>
                        <div className="divider">
                          <span>SELECTED ASSET</span>
                        </div>
                        <h3 className="filename">{inputSelected.filename}</h3>
                        {inputSelected.nature === "synthetic" && (
                          <div className="synthetic-note">{DEMO_LABEL}</div>
                        )}
                        <label className="field">
                          Semantic role
                          <select
                            value={inputSelected.role}
                            onChange={(e) =>
                              declaration(inputSelected, {
                                role: e.target.value,
                              })
                            }
                          >
                            {roles.map((r) => (
                              <option key={r} value={r}>
                                {roleName(r)}
                              </option>
                            ))}
                          </select>
                        </label>
                        {inputSelected.metadata.kind === "raster" && (
                          <>
                            <div className="field-grid">
                              <label className="field">
                                Units
                                <select
                                  value={inputSelected.units}
                                  onChange={(e) =>
                                    declaration(inputSelected, {
                                      units: e.target.value,
                                    })
                                  }
                                >
                                  {["unknown", "m", "ft", "category"].map(
                                    (u) => (
                                      <option key={u}>{u}</option>
                                    ),
                                  )}
                                </select>
                              </label>
                              <label className="field">
                                Height reference
                                <select
                                  value={inputSelected.height_reference}
                                  onChange={(e) =>
                                    declaration(inputSelected, {
                                      height_reference: e.target.value,
                                    })
                                  }
                                >
                                  {[
                                    "unknown",
                                    "absolute",
                                    "above_ground",
                                    "not_applicable",
                                  ].map((u) => (
                                    <option key={u}>{u}</option>
                                  ))}
                                </select>
                              </label>
                            </div>
                            <label className="field">
                              Vertical datum
                              <input
                                key={
                                  inputSelected.id +
                                  inputSelected.vertical_reference
                                }
                                defaultValue={inputSelected.vertical_reference}
                                onBlur={(e) => {
                                  if (
                                    e.target.value !==
                                    inputSelected.vertical_reference
                                  )
                                    declaration(inputSelected, {
                                      vertical_reference: e.target.value,
                                    });
                                }}
                              />
                            </label>
                            <div className="metadata">
                              <div>
                                <span>CRS</span>
                                <b>{inputSelected.metadata.crs || "Missing"}</b>
                              </div>
                              <div>
                                <span>Dimensions</span>
                                <b>
                                  {inputSelected.metadata.width} ×{" "}
                                  {inputSelected.metadata.height}
                                </b>
                              </div>
                              <div>
                                <span>Resolution</span>
                                <b>
                                  {inputSelected.metadata.resolution?.join(
                                    " × ",
                                  )}
                                </b>
                              </div>
                              <div>
                                <span>NoData</span>
                                <b>
                                  {(
                                    (inputSelected.metadata.nodata_fraction ||
                                      0) * 100
                                  ).toFixed(1)}
                                  %
                                </b>
                              </div>
                            </div>
                          </>
                        )}
                        <label className="field">
                          Source
                          <input
                            key={inputSelected.id + inputSelected.source}
                            defaultValue={inputSelected.source}
                            onBlur={(e) => {
                              if (e.target.value !== inputSelected.source)
                                declaration(inputSelected, {
                                  source: e.target.value,
                                });
                            }}
                          />
                        </label>
                        <details>
                          <summary>Full metadata & provenance</summary>
                          <pre>{JSON.stringify(inputSelected, null, 2)}</pre>
                        </details>
                      </>
                    ) : (
                      <div className="note">
                        <Info size={16} />
                        <span>
                          Select a layer to inspect metadata and declare its
                          role. Filenames never determine the role
                          automatically.
                        </span>
                      </div>
                    )}
                    <button
                      className="secondary wide"
                      onClick={fixture}
                      disabled={!!busy}
                    >
                      Load demo fixture
                    </button>
                    <button
                      className="primary wide"
                      onClick={validate}
                      disabled={!!busy}
                    >
                      <ShieldCheck size={16} /> Validate inputs
                    </button>
                  </>
                )}
                {stage === 2 && (
                  <>
                    <div className="section-index">03 / QUALITY CHECKS</div>
                    <h2>Confidence before computation</h2>
                    <p>
                      Check coverage, CRS, shared grid, missing pixels, and
                      declared height units.
                    </p>
                    <button
                      className="primary wide"
                      onClick={validate}
                      disabled={!!busy}
                    >
                      <ShieldCheck size={16} /> Run validation
                    </button>
                    {report ? (
                      <>
                        <div
                          className={
                            "validation-status " +
                            (report.valid ? "pass" : "fail")
                          }
                        >
                          {report.valid ? (
                            <Check size={18} />
                          ) : (
                            <Info size={18} />
                          )}{" "}
                          {report.valid
                            ? "Ready for explicit demo processing"
                            : "Resolve blocking findings"}
                          <small>
                            {
                              report.findings.filter(
                                (f) => f.severity === "error",
                              ).length
                            }{" "}
                            errors ·{" "}
                            {
                              report.findings.filter(
                                (f) => f.severity === "warning",
                              ).length
                            }{" "}
                            warnings
                          </small>
                        </div>
                        {report.findings.map((f, i) => (
                          <div key={i} className={"finding " + f.severity}>
                            <span>
                              {f.severity === "error"
                                ? "BLOCKING ERROR"
                                : f.severity.toUpperCase()}
                            </span>
                            <b>{f.message}</b>
                            <p>{f.remedy}</p>
                          </div>
                        ))}
                        {!report.findings.length && (
                          <p>All selected checks passed.</p>
                        )}
                        <button
                          className="text-action"
                          onClick={() => setStage(3)}
                        >
                          Configure simulation <ChevronRight size={16} />
                        </button>
                      </>
                    ) : (
                      <div className="note">
                        <Info size={16} />
                        <span>
                          Validation checks the selected engine and
                          configuration. Warnings stay in the run manifest.
                        </span>
                      </div>
                    )}
                  </>
                )}
                {stage === 3 && (
                  <>
                    <div className="section-index">
                      04 / MODEL CONFIGURATION
                    </div>
                    <h2>Run a climate workflow</h2>
                    <label className="field">
                      Processing engine
                      <select
                        value={config.engine}
                        onChange={(e) => {
                          setConfig({
                            ...config,
                            engine: e.target.value as Config["engine"],
                          });
                          setReport(null);
                        }}
                      >
                        <option value="demo">Demonstration engine</option>
                        <option value="umep">QGIS / UMEP · unsupported</option>
                      </select>
                    </label>
                    <div className="synthetic-note">
                      {config.engine === "demo"
                        ? DEMO_LABEL
                        : cap?.umep.reason ||
                          "Scientific engine unavailable. No demo fallback."}
                    </div>
                    <div className="field-grid">
                      <label className="field">
                        Air temperature (°C)
                        <input
                          type="number"
                          min="-80"
                          max="65"
                          value={config.air_temperature}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              air_temperature: +e.target.value,
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        Solar altitude (°)
                        <input
                          type="number"
                          min="1"
                          max="90"
                          value={config.solar_altitude}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              solar_altitude: +e.target.value,
                            })
                          }
                        />
                      </label>
                    </div>
                    <label className="field">
                      Vegetation state
                      <select
                        value={config.vegetation}
                        onChange={(e) =>
                          setConfig({ ...config, vegetation: e.target.value })
                        }
                      >
                        <option value="unknown">Unknown</option>
                        <option value="absent">Confirmed absent</option>
                        <option value="provided">
                          Canopy & trunk layers provided
                        </option>
                      </select>
                    </label>
                    <label className="field">
                      Weather CSV
                      <select
                        value={config.weather_asset_id || ""}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            weather_asset_id: e.target.value || null,
                          })
                        }
                      >
                        <option value="">Hypothetical demo parameters</option>
                        {project.assets
                          .filter((a) => a.role === "weather")
                          .map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.filename}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label className="field">
                      Weather timezone (IANA)
                      <input
                        value={config.timezone}
                        onChange={(e) =>
                          setConfig({ ...config, timezone: e.target.value })
                        }
                      />
                    </label>
                    <small className="help">
                      Uploaded weather is recorded in demo provenance. It does
                      not drive the illustrative demo formula.
                    </small>
                    <button
                      className="primary wide"
                      onClick={submit}
                      disabled={!!busy}
                    >
                      <Play size={15} />{" "}
                      {config.engine === "demo"
                        ? "Run demonstration"
                        : "Submit scientific request"}
                    </button>
                    <div className="divider">
                      <span>ENGINE AVAILABILITY</span>
                    </div>
                    <div className="detail-row">
                      <span>Demo engine</span>
                      <b className="green">Available</b>
                    </div>
                    <div className="detail-row">
                      <span>QGIS / UMEP</span>
                      <b>
                        {cap?.umep.version
                          ? cap.umep.version.split("-")[0] + " / no engine"
                          : "Unsupported"}
                      </b>
                    </div>
                    <div className="detail-row">
                      <span>PDAL processing</span>
                      <b>Unsupported</b>
                    </div>
                    {currentJob && (
                      <JobView
                        job={currentJob}
                        base={base}
                        showLogs={showLogs}
                        setShowLogs={setShowLogs}
                        onCancel={() =>
                          task("Cancelling job", async () => {
                            await api(
                              base + "/jobs/" + currentJob.id + "/cancel",
                              { method: "POST" },
                            );
                            await refresh(project.id);
                          })
                        }
                        onResults={() => {
                          setJobId(currentJob.id);
                          setStage(4);
                          if (currentJob.manifest?.outputs[0])
                            selectOutput(
                              currentJob.manifest.outputs[0],
                              currentJob,
                            );
                        }}
                      />
                    )}
                  </>
                )}
                {stage === 4 && (
                  <>
                    <div className="section-index">
                      05 / RESULTS & PROVENANCE
                    </div>
                    <h2>Inspect your run</h2>
                    <p>
                      Georeferenced outputs, pixel values, and a reproducible
                      record of the workflow.
                    </p>
                    {project.jobs.length ? (
                      <>
                        <label className="field">
                          Run history
                          <select
                            value={currentJob?.id || ""}
                            onChange={(e) => {
                              setJobId(e.target.value);
                              setSelected(null);
                              setSummary(null);
                            }}
                          >
                            {project.jobs.map((j) => (
                              <option value={j.id} key={j.id}>
                                {new Date(j.created_at).toLocaleString()} ·{" "}
                                {j.state}
                              </option>
                            ))}
                          </select>
                        </label>
                        {currentJob?.state === "succeeded" ? (
                          <>
                            <div className="synthetic-note">{DEMO_LABEL}</div>
                            {currentJob.manifest?.outputs.map((o) => (
                              <div
                                className={
                                  "output-row " +
                                  (selected?.id === o.id ? "selected" : "")
                                }
                                key={o.id}
                              >
                                <button
                                  onClick={() => selectOutput(o, currentJob)}
                                >
                                  <span className="layer-swatch synthetic" />
                                  <span>
                                    {o.role === "shade"
                                      ? "Shade fraction"
                                      : "Mean radiant temperature"}
                                    <small>{o.units} · synthetic GeoTIFF</small>
                                  </span>
                                </button>
                                <a
                                  title="Download GeoTIFF"
                                  href={
                                    "/api" +
                                    base +
                                    "/jobs/" +
                                    currentJob.id +
                                    "/outputs/" +
                                    o.id +
                                    "/download"
                                  }
                                >
                                  <Download size={16} />
                                </a>
                              </div>
                            ))}
                            {summary && (
                              <div className="summary-card">
                                <span>SUMMARY / {summary.scope}</span>
                                <div>
                                  <b>
                                    {summary.mean?.toFixed(2) ?? "—"}
                                    <small>Mean · {summary.units}</small>
                                  </b>
                                  <b>
                                    {summary.minimum?.toFixed(1) ?? "—"}
                                    <small>Minimum</small>
                                  </b>
                                  <b>
                                    {summary.maximum?.toFixed(1) ?? "—"}
                                    <small>Maximum</small>
                                  </b>
                                </div>
                                <small>
                                  {summary.count.toLocaleString()} valid pixels
                                </small>
                              </div>
                            )}
                            <a
                              className="primary wide"
                              href={
                                "/api" +
                                base +
                                "/jobs/" +
                                currentJob.id +
                                "/download/package"
                              }
                            >
                              <Download size={16} /> Download run package
                            </a>
                            <a
                              className="secondary wide"
                              href={
                                "/api" +
                                base +
                                "/jobs/" +
                                currentJob.id +
                                "/download/manifest"
                              }
                            >
                              <FileText size={16} /> Download manifest
                            </a>
                            <button
                              className="text-action"
                              onClick={() => {
                                setConfig({
                                  ...currentJob.config,
                                  baseline_configuration_id: currentJob.id,
                                });
                                setStage(3);
                              }}
                            >
                              <Copy size={15} /> Duplicate run configuration
                            </button>
                          </>
                        ) : (
                          <div className="note">
                            <Info size={16} />
                            <span>
                              This run is {currentJob?.state}. Outputs are
                              published only after successful completion.
                            </span>
                          </div>
                        )}
                        <JobView
                          job={currentJob!}
                          base={base}
                          showLogs={showLogs}
                          setShowLogs={setShowLogs}
                          onCancel={() =>
                            task("Cancelling job", async () => {
                              await api(
                                base + "/jobs/" + currentJob!.id + "/cancel",
                                { method: "POST" },
                              );
                              await refresh(project.id);
                            })
                          }
                        />
                        <button
                          className="text-action"
                          onClick={() =>
                            task("Reading process log", async () =>
                              setProcessLog(
                                (
                                  await api<{ log: string }>(
                                    base +
                                      "/jobs/" +
                                      currentJob!.id +
                                      "/process-log",
                                  )
                                ).log || "No subprocess output.",
                              ),
                            )
                          }
                        >
                          Read subprocess output
                        </button>
                        {processLog && <pre className="logs">{processLog}</pre>}
                      </>
                    ) : (
                      <div className="empty-result">
                        <Activity size={30} />
                        <h3>No runs yet</h3>
                        <p>
                          Validate your inputs and run a demonstration to see
                          results here.
                        </p>
                        <button
                          className="secondary"
                          onClick={() => setStage(3)}
                        >
                          Configure a run
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
            <div className="panel-footer">
              <ShieldCheck size={14} /> Sources preserved · processing is
              explicit
            </div>
          </section>
        </div>
        <footer>
          <span>
            <span className="dot" /> {busy || "Workspace ready"}
          </span>
          <span>
            UMEP Studio <b>v0.1</b> <span className="footer-divider">/</span>{" "}
            Local-first urban climate analysis
          </span>
        </footer>
      </div>
      {busy && (
        <div className="busy">
          <LoaderCircle size={16} className="spin" />
          {busy}
        </div>
      )}
      {modal && (
        <div className="modal-backdrop">
          <form
            role="dialog"
            aria-label="Create project"
            className="modal"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) create();
            }}
          >
            <button
              type="button"
              className="close-modal"
              onClick={() => setModal(false)}
            >
              <X size={18} />
            </button>
            <span className="eyebrow">NEW PROJECT</span>
            <h2>A new urban perspective</h2>
            <p>
              Give your study a name. Your data and runs will stay together.
            </p>
            <label className="field">
              Project name
              <input
                autoFocus
                required
                maxLength={100}
                placeholder="e.g. Riverside district"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button className="primary wide" disabled={!!busy || !name.trim()}>
              Create project <ArrowUpRight size={16} />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
function JobView({
  job,
  showLogs,
  setShowLogs,
  onCancel,
  onResults,
}: {
  job: Job;
  base: string;
  showLogs: boolean;
  setShowLogs: (v: boolean) => void;
  onCancel: () => void;
  onResults?: () => void;
}) {
  if (!job) return null;
  return (
    <div className="job-card">
      <div className="job-title">
        <Activity size={16} />
        <b>Processing job</b>
        <span className={"status " + job.state}>{job.state}</span>
      </div>
      <div className="progress">
        <div style={{ width: job.progress + "%" }} />
      </div>
      <small>
        {job.progress}% · {job.config.engine} engine
      </small>
      {["queued", "running"].includes(job.state) && (
        <button className="text-action" onClick={onCancel}>
          Cancel job <X size={14} />
        </button>
      )}
      {job.state === "succeeded" && onResults && (
        <button className="primary wide" onClick={onResults}>
          Explore results <ArrowUpRight size={16} />
        </button>
      )}
      <button className="log-toggle" onClick={() => setShowLogs(!showLogs)}>
        <ChevronDown size={14} /> Processing log
      </button>
      {showLogs && (
        <pre className="logs">
          {job.logs.length
            ? job.logs.join("\n")
            : "Queued — waiting for local worker."}
        </pre>
      )}
    </div>
  );
}
