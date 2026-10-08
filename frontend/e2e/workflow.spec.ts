import { test, expect } from "@playwright/test";
test("project → dataset → validation → demo → results → manifest", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page.getByLabel("Project name").fill("Browser acceptance district");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Start with a boundary" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load demo dataset" }).click();
  await expect(
    page.getByRole("heading", { name: "demo-surface.tif" }),
  ).toBeVisible();
  await expect(
    page
      .getByText("Demonstration data — not a scientific simulation.", {
        exact: true,
      })
      .first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Validate inputs", exact: true })
    .click();
  await expect(
    page.getByText("Ready for explicit demo processing"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Configure simulation" }).click();
  await page.getByLabel("Vegetation state").selectOption("absent");
  await page
    .getByRole("button", { name: "Run demonstration", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Explore results" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Explore results" }).click();
  await expect(
    page.getByRole("heading", { name: "Inspect your run" }),
  ).toBeVisible();
  await expect(page.getByText("SUMMARY / raster extent")).toBeVisible();
  await page
    .getByRole("button", {
      name: "Mean radiant temperature °C · synthetic GeoTIFF",
    })
    .click();
  await expect(page.getByText("Mean · °C")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download manifest" }).click();
  expect((await download).suggestedFilename()).toBe("manifest.json");
  await page.screenshot({
    path: "/tmp/umep-studio-results.png",
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByText("Browser acceptance district").first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
