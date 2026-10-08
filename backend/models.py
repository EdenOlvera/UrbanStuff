from typing import Literal
from pydantic import BaseModel, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROLES = [
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
]


class StudyArea(BaseModel):
    reporting: dict
    processing: dict


class GridSpecification(BaseModel):
    crs: str
    pixel_size: tuple[float, float]
    origin: tuple[float, float]
    bounds: tuple[float, float, float, float]
    width: int
    height: int
    nodata_policy: str = "Preserve input mask; never treat unknown as zero."


class Project(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    study_area: StudyArea | None = None
    grid: GridSpecification | None = None


class Asset(BaseModel):
    id: str
    project_id: str
    filename: str
    storage_location: str
    role: str = "unassigned"
    source: str = "unknown"
    acquisition_date: str | None = None
    vertical_reference: str = "unknown"
    units: Literal["unknown", "m", "ft", "category"] = "unknown"
    height_reference: Literal[
        "unknown", "absolute", "above_ground", "not_applicable"
    ] = "unknown"
    nature: Literal["observed", "derived", "estimated", "synthetic"] = "observed"
    checksum: str
    metadata: dict = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)


class AssetDeclaration(BaseModel):
    role: Literal[
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
    ]
    units: Literal["unknown", "m", "ft", "category"] = "unknown"
    height_reference: Literal[
        "unknown", "absolute", "above_ground", "not_applicable"
    ] = "unknown"
    vertical_reference: str = Field(default="unknown", max_length=100)
    source: str = Field(default="unknown", max_length=200)
    acquisition_date: str | None = None
    nature: Literal["observed", "derived", "estimated", "synthetic"] = "observed"


class SimulationConfiguration(BaseModel):
    engine: Literal["demo", "umep"] = "demo"
    air_temperature: float = Field(default=25, ge=-80, le=65)
    solar_altitude: float = Field(default=45, gt=0, le=90)
    vegetation: Literal["unknown", "absent", "provided"] = "unknown"
    weather_asset_id: str | None = None
    timezone: str = "UTC"
    baseline_configuration_id: str | None = None
    input_overrides: dict[str, str] = Field(default_factory=dict)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                "Use a valid IANA timezone, for example UTC or Europe/Berlin"
            ) from exc
        return value


class Finding(BaseModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    remedy: str
    asset_id: str | None = None


class ValidationReport(BaseModel):
    valid: bool
    findings: list[Finding]


class Job(BaseModel):
    id: str
    project_id: str
    state: Literal[
        "queued", "running", "succeeded", "failed", "cancelled", "interrupted"
    ]
    config: SimulationConfiguration
    progress: int = 0
    logs: list[str] = Field(default_factory=list)


class OutputAsset(BaseModel):
    id: str
    role: str
    units: str
    synthetic: bool
    checksum: str
    filename: str
    metadata: dict


class RunManifest(BaseModel):
    schema_version: str = "1"
    job_id: str
    project_id: str
    synthetic: bool
    label: str
    inputs: list[dict]
    configuration: dict
    grid: dict
    study_area: dict | None = None
    versions: dict
    stage_versions: dict
    started_at: str
    finished_at: str
    warnings: list[str]
    assumptions: list[str]
    outputs: list[dict]
