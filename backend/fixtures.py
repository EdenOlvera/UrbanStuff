from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin


def create_fixture(path):
    y, x = np.indices((180, 220))
    data = (12 + 1.5 * np.sin(x / 18) * np.cos(y / 21)).astype("float32")
    for bx, by, w, h, height in [
        (25, 25, 28, 40, 20),
        (75, 30, 35, 28, 27),
        (130, 20, 24, 48, 21),
        (45, 95, 45, 26, 18),
        (120, 100, 42, 38, 29),
        (178, 65, 23, 52, 24),
    ]:
        data[by : by + h, bx : bx + w] += height
    data[:4, :] = -9999
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=220,
        height=180,
        count=1,
        dtype="float32",
        crs="EPSG:32632",
        transform=from_origin(691000, 5330000, 2, 2),
        nodata=-9999,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(
            description="Demonstration data — not a scientific simulation.",
            synthetic="true",
        )


if __name__ == "__main__":
    Path("examples").mkdir(exist_ok=True)
    create_fixture("examples/demo-surface.tif")
