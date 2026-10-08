import csv, hashlib, io
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import rasterio
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.transform import from_bounds
from shapely.geometry import shape, box
from shapely.ops import transform
from pyproj import Transformer, CRS
from PIL import Image

LABEL = "Demonstration data — not a scientific simulation."


def checksum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_raster(path):
    with rasterio.open(path) as src:
        if src.driver != "GTiff":
            raise ValueError("Only GeoTIFF rasters are supported")
        if src.width * src.height > 25_000_000:
            raise ValueError("Raster exceeds the MVP limit of 25 million pixels")
        valid = missing = 0
        for _, win in src.block_windows(1):
            mask = src.read(1, window=win, masked=True)
            finite = np.isfinite(mask.data) & ~np.ma.getmaskarray(mask)
            valid += int(finite.sum())
            missing += mask.size - int(finite.sum())
        bounds = list(src.bounds)
        geographic = (
            list(transform_bounds(src.crs, "EPSG:4326", *bounds, densify_pts=21))
            if src.crs
            else None
        )
        return {
            "crs": src.crs.to_string() if src.crs else None,
            "bounds": bounds,
            "geographic_bounds": geographic,
            "width": src.width,
            "height": src.height,
            "resolution": list(src.res),
            "transform": list(src.transform)[:6],
            "nodata": float(src.nodata)
            if src.nodata is not None and np.isfinite(src.nodata)
            else None,
            "nodata_fraction": missing / (missing + valid),
            "bands": src.count,
            "dtype": src.dtypes[0],
            "kind": "raster",
        }


def grid_from(metadata):
    return {
        "crs": metadata["crs"],
        "pixel_size": metadata["resolution"],
        "origin": [metadata["transform"][2], metadata["transform"][5]],
        "bounds": metadata["bounds"],
        "width": metadata["width"],
        "height": metadata["height"],
        "nodata_policy": "Preserve input mask; unknown is never zero.",
    }


def validate_geometry(value):
    geometry = value.get("geometry", value) if value.get("type") == "Feature" else value
    geom = shape(geometry)
    if (
        geom.geom_type not in ("Polygon", "MultiPolygon")
        or not geom.is_valid
        or geom.is_empty
    ):
        raise ValueError("Provide a valid GeoJSON polygon or multipolygon")
    if not box(-180, -90, 180, 90).covers(geom):
        raise ValueError("GeoJSON must use longitude/latitude (EPSG:4326)")
    return geom.__geo_interface__


def weather(path, timezone):
    ZoneInfo(timezone)
    rows = list(csv.DictReader(path.open()))
    if not rows:
        raise ValueError("Weather CSV is empty")
    required = {
        "timestamp",
        "air_temperature_c",
        "relative_humidity_pct",
        "global_horizontal_w_m2",
    }
    if not required.issubset(rows[0]):
        raise ValueError("Required columns: " + ", ".join(sorted(required)))
    dates = []
    for r in rows:
        dt = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError(
                "Timestamps must include a UTC offset; ambiguous local times are not accepted"
            )
        dates.append(dt)
        temp, rh, ghi = [
            float(r[k])
            for k in (
                "air_temperature_c",
                "relative_humidity_pct",
                "global_horizontal_w_m2",
            )
        ]
        if (
            not np.isfinite([temp, rh, ghi]).all()
            or not -80 <= temp <= 65
            or not 0 <= rh <= 100
            or ghi < 0
        ):
            raise ValueError("Weather values outside documented ranges")
        for name in ("direct_normal_w_m2", "diffuse_horizontal_w_m2", "wind_speed_m_s"):
            if r.get(name) and (not np.isfinite(float(r[name])) or float(r[name]) < 0):
                raise ValueError(f"Invalid {name}")
        if r.get("wind_speed_m_s") and (
            not r.get("wind_height_m") or float(r["wind_height_m"]) <= 0
        ):
            raise ValueError("Wind speed requires positive wind_height_m")
    if len(set(dates)) != len(dates):
        raise ValueError("Duplicate weather timestamps")
    if dates != sorted(dates):
        raise ValueError("Weather timestamps must be increasing")
    gaps = [int((b - a).total_seconds()) for a, b in zip(dates, dates[1:])]
    return {
        "kind": "weather",
        "rows": len(rows),
        "timezone": timezone,
        "start": dates[0].isoformat(),
        "end": dates[-1].isoformat(),
        "warnings": [
            "Irregular weather time intervals; resolve gaps before scientific use."
        ]
        if gaps and (len(set(gaps)) > 1 or max(gaps) > 3600)
        else [],
    }


def validate(project, assets, config):
    findings = []

    def add(severity, code, message, remedy, aid=None):
        findings.append(
            dict(
                severity=severity,
                code=code,
                message=message,
                remedy=remedy,
                asset_id=aid,
            )
        )

    rasters = [a for a in assets if a["metadata"].get("kind") == "raster"]
    surfaces = [a for a in rasters if a["role"] in ("building_dsm", "surface_dsm")]
    if len(surfaces) > 1:
        add(
            "error",
            "ambiguous_surface",
            "Multiple surface DSMs are selected.",
            "Select one DSM with a scenario input override, or change the non-target roles.",
        )
    if not surfaces:
        add(
            "error",
            "surface_missing",
            "A declared surface DSM is required.",
            "Upload a GeoTIFF and assign its surface role.",
        )
    if not project.get("study_area"):
        add(
            "warning",
            "boundary_missing",
            "No reporting or processing boundary is defined.",
            "Draw or upload a study polygon; the demo will use the raster extent.",
        )
    if config.get("vegetation") == "unknown":
        add(
            "warning",
            "vegetation_unknown",
            "Vegetation is unknown, not confirmed absent.",
            "Declare absent vegetation or provide canopy and trunk layers.",
        )
    if config.get("vegetation") == "provided" and not all(
        any(a["role"] == role for a in rasters)
        for role in ("canopy_height", "trunk_height")
    ):
        add(
            "error",
            "vegetation_missing",
            "Vegetation was declared provided but canopy/trunk layers are missing.",
            "Upload and assign both height-above-ground layers.",
        )
    reference = surfaces[0]["metadata"] if surfaces else None
    for a in assets:
        m = a["metadata"]
        aid = a["id"]
        if a["role"] == "unassigned":
            add(
                "warning",
                "unassigned",
                f"{a['filename']} has no semantic role.",
                "Assign its meaning explicitly.",
                aid,
            )
        if m.get("kind") != "raster":
            continue
        if not m["crs"]:
            add(
                "error",
                "missing_crs",
                "Raster CRS is missing.",
                "Create a derived GeoTIFF with the correct source CRS; do not guess.",
                aid,
            )
            continue
        if not CRS(m["crs"]).is_projected or any(
            ax.unit_name.lower() not in ("metre", "meter")
            for ax in CRS(m["crs"]).axis_info
        ):
            add(
                "error",
                "projected_crs",
                "This workflow requires a projected CRS in metres.",
                "Reproject into a suitable local projected CRS as a derived asset.",
                aid,
            )
        if m["transform"][1] != 0 or m["transform"][3] != 0:
            add(
                "error",
                "rotated_grid",
                "Rotated raster grids are unsupported in the MVP.",
                "Create a north-up derived raster.",
                aid,
            )
        if a["units"] == "unknown":
            add(
                "warning",
                "unknown_units",
                "Raster units are unknown.",
                "Declare units from source documentation.",
                aid,
            )
        if a["role"] in (
            "terrain",
            "building_dsm",
            "surface_dsm",
            "canopy_height",
            "trunk_height",
        ):
            expected = (
                "above_ground"
                if a["role"] in ("canopy_height", "trunk_height")
                else "absolute"
            )
            if a["units"] != "m":
                add(
                    "error",
                    "height_units",
                    "Height rasters must use declared metre units.",
                    "Convert feet into a new derived asset, or declare verified metre units.",
                    aid,
                )
            if a["height_reference"] != expected:
                add(
                    "error",
                    "height_reference",
                    f"{a['role']} requires {expected} heights.",
                    "Verify and declare the height reference.",
                    aid,
                )
            if a["vertical_reference"] == "unknown":
                add(
                    "warning",
                    "vertical_unknown",
                    "Vertical datum is unknown.",
                    "Document the datum before scientific use.",
                    aid,
                )
        if m["nodata_fraction"] == 1:
            add(
                "error",
                "all_nodata",
                "Raster contains no valid pixels.",
                "Provide a raster with valid coverage.",
                aid,
            )
        elif m["nodata_fraction"] > 0:
            add(
                "warning",
                "nodata",
                "Raster has missing pixels; zero values remain valid.",
                "Review gaps and preserve the quality mask.",
                aid,
            )
        if reference and (
            m["crs"] != reference["crs"]
            or m["width"] != reference["width"]
            or m["height"] != reference["height"]
            or not np.allclose(
                m["transform"], reference["transform"], rtol=0, atol=1e-7
            )
        ):
            add(
                "error",
                "grid_alignment",
                "Raster does not match the shared surface grid.",
                "Create an aligned derived asset; nearest-neighbour for categories, bilinear for continuous data. Finer pixels do not increase source accuracy.",
                aid,
            )
        if (
            project.get("grid")
            and m["crs"] == project["grid"]["crs"]
            and (
                m["width"] != project["grid"]["width"]
                or m["height"] != project["grid"]["height"]
                or not np.allclose(m["resolution"], project["grid"]["pixel_size"])
            )
        ):
            add(
                "error",
                "project_grid",
                "Raster dimensions/resolution differ from the project grid.",
                "Align a derived raster to the documented project grid.",
                aid,
            )
        if project.get("study_area"):
            transformer = Transformer.from_crs("EPSG:4326", m["crs"], always_xy=True)
            boundary = transform(
                transformer.transform, shape(project["study_area"]["processing"])
            )
            if not box(*m["bounds"]).buffer(1e-6).covers(boundary):
                add(
                    "error",
                    "coverage",
                    "Raster does not cover the processing boundary.",
                    "Supply surrounding coverage or reduce the processing boundary.",
                    aid,
                )
    # Compare declared related layers on the same grid, ignoring masked pixels.
    from .storage import managed_path

    by_role = {a["role"]: a for a in rasters}
    for lower_role, upper_role, code in [
        ("terrain", "building_dsm", "surface_below_terrain"),
        ("terrain", "surface_dsm", "surface_below_terrain"),
        ("trunk_height", "canopy_height", "trunk_above_canopy"),
    ]:
        lower, upper = by_role.get(lower_role), by_role.get(upper_role)
        if not lower or not upper:
            continue
        lm, um = lower["metadata"], upper["metadata"]
        if (
            lm["crs"] != um["crs"]
            or lm["width"] != um["width"]
            or lm["height"] != um["height"]
            or not np.allclose(lm["transform"], um["transform"], rtol=0, atol=1e-7)
        ):
            continue
        if lm["crs"] is None:
            continue
        try:
            with (
                rasterio.open(managed_path(lower["storage_location"])) as l,
                rasterio.open(managed_path(upper["storage_location"])) as u,
            ):
                inconsistent = 0
                for _, window in l.block_windows(1):
                    lv = l.read(1, window=window, masked=True)
                    uv = u.read(1, window=window, masked=True)
                    both = (
                        ~np.ma.getmaskarray(lv)
                        & ~np.ma.getmaskarray(uv)
                        & np.isfinite(lv.data)
                        & np.isfinite(uv.data)
                    )
                    inconsistent += int(
                        np.count_nonzero(both & (lv.data > uv.data + 0.05))
                    )
                if inconsistent:
                    add(
                        "error",
                        code,
                        f"{inconsistent} pixels in {lower_role} exceed {upper_role}.",
                        "Check height references, datum, roles, and source alignment; preserve originals.",
                    )
        except rasterio.errors.RasterioError:
            add(
                "error",
                "unreadable",
                "A related raster can no longer be read.",
                "Re-upload the original raster.",
            )
    if config.get("weather_asset_id"):
        w = next(
            (
                a
                for a in assets
                if a["id"] == config["weather_asset_id"] and a["role"] == "weather"
            ),
            None,
        )
        if not w:
            add(
                "error",
                "weather_missing",
                "Selected weather asset is not in this project.",
                "Choose a weather CSV from this project.",
            )
        elif w["metadata"].get("timezone") != config.get("timezone"):
            add(
                "error",
                "weather_timezone",
                "Weather interpretation and configuration timezone differ.",
                "Use the same explicit timezone.",
            )
    if config.get("engine") == "umep":
        add(
            "error",
            "umep_unavailable",
            "Scientific UMEP execution is not enabled in this MVP.",
            "Connect and verify a QGIS/UMEP provider and implement its installed parameter mapping; demo is a separate explicit engine.",
        )
    return {
        "valid": not any(f["severity"] == "error" for f in findings),
        "findings": findings,
    }


def preview(path, quantity="height"):
    with rasterio.open(path) as src:
        if not src.crs:
            raise ValueError("A CRS is required for georeferenced preview")
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        width = 512
        height = max(
            1,
            min(
                512,
                round(512 * (bounds[3] - bounds[1]) / max(bounds[2] - bounds[0], 1e-9)),
            ),
        )
        dest = np.full((height, width), np.nan, dtype="float32")
        reproject(
            rasterio.band(src, 1),
            dest,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=from_bounds(*bounds, width, height),
            dst_crs="EPSG:4326",
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
        valid = np.isfinite(dest)
        lo, hi = np.percentile(dest[valid], [2, 98]) if valid.any() else (0, 1)
        t = np.clip(
            (np.nan_to_num(dest, nan=float(lo)) - lo) / max(hi - lo, 1e-6), 0, 1
        )
        colors = np.array(
            [
                [41, 73, 63],
                [105, 145, 100],
                [217, 215, 148],
                [232, 159, 90],
                [177, 68, 49],
            ],
            dtype=float,
        )
        rgb = np.stack(
            [np.interp(t, np.linspace(0, 1, 5), colors[:, i]) for i in range(3)],
            axis=-1,
        ).astype("uint8")
        rgba = np.concatenate([rgb, (valid * 215).astype("uint8")[..., None]], axis=-1)
        out = io.BytesIO()
        Image.fromarray(rgba).save(out, format="PNG")
        return out.getvalue()
