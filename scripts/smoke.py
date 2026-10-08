"""Live API + separate worker smoke test; services must already be running."""

import argparse, io, json, time, zipfile
import httpx
from backend.fixtures import create_fixture
from pathlib import Path
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url + "/api", timeout=30) as c:

        def request(method, path, **kwargs):
            r = c.request(method, path, **kwargs)
            r.raise_for_status()
            return r

        p = request("POST", "/projects", json={"name": "Smoke test district"}).json()
        base = "/projects/" + p["id"]
        with tempfile.TemporaryDirectory() as d:
            fixture = Path(d) / "surface.tif"
            create_fixture(fixture)
            with fixture.open("rb") as f:
                a = request(
                    "POST",
                    base + "/assets",
                    files={"file": ("surface.tif", f, "image/tiff")},
                ).json()
        request(
            "PUT",
            base + "/assets/" + a["id"],
            json={
                "role": "surface_dsm",
                "units": "m",
                "height_reference": "absolute",
                "vertical_reference": "synthetic datum",
                "nature": "synthetic",
            },
        )
        cfg = {
            "engine": "demo",
            "vegetation": "absent",
            "air_temperature": 25,
            "solar_altitude": 45,
        }
        report = request("POST", base + "/validate", json=cfg).json()
        assert report["valid"], report
        j = request("POST", base + "/jobs", json=cfg).json()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            j = request("GET", base + "/jobs/" + j["id"]).json()
            if j["state"] in ("succeeded", "failed", "cancelled", "interrupted"):
                break
            time.sleep(0.25)
        assert j["state"] == "succeeded", j
        prefix = base + "/jobs/" + j["id"]
        m = request("GET", prefix + "/download/manifest").json()
        assert m["synthetic"] and len(m["outputs"]) == 2 and "study_area" in m
        o = m["outputs"][0]
        b = o["metadata"]["geographic_bounds"]
        pixel = request(
            "GET",
            prefix + "/outputs/" + o["id"] + "/pixel",
            params={"lon": (b[0] + b[2]) / 2, "lat": (b[1] + b[3]) / 2},
        ).json()
        assert pixel["value"] in (0, 1)
        assert request(
            "GET", prefix + "/outputs/" + o["id"] + "/preview.png"
        ).content.startswith(b"\x89PNG")
        with zipfile.ZipFile(
            io.BytesIO(request("GET", prefix + "/download/package").content)
        ) as z:
            assert "manifest.json" in z.namelist()
        assert request("GET", base).json()["assets"]
        print(
            json.dumps(
                {
                    "status": "passed",
                    "project_id": p["id"],
                    "job_id": j["id"],
                    "outputs": len(m["outputs"]),
                    "pixel": pixel["value"],
                    "label": m["label"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
