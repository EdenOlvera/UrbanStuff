import { describe, it, expect, vi, afterEach } from "vitest";
import { api, roleName, DEMO_LABEL } from "./types";
afterEach(() => vi.unstubAllGlobals());
describe("API client", () => {
  it("preserves structured validation errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          json: async () => ({
            detail: { valid: false, findings: [{ code: "missing_crs" }] },
          }),
        }),
    );
    await expect(api("/test")).rejects.toThrow("missing_crs");
  });
  it("sends the configured JSON request", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ id: "project" }) });
    vi.stubGlobal("fetch", fetch);
    expect(await api("/projects")).toEqual({ id: "project" });
    expect(fetch).toHaveBeenCalledWith("/api/projects", undefined);
  });
  it("names the surface role and labels demo output", () => {
    expect(roleName("surface_dsm")).toBe("Combined surface DSM");
    expect(DEMO_LABEL).toContain("not a scientific simulation");
  });
});
