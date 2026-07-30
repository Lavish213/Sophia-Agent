import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ORIGINAL_ENV = { ...process.env };

async function loadRoute() {
  vi.resetModules();
  return await import("./route");
}

function post(body: unknown) {
  return new Request("http://localhost/api/lead", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const VALID = { name: "Maria", phone: "2095551212", address: "123 Main St" };

beforeEach(() => {
  process.env.INTAKE_WEBHOOK_SECRET = "test-secret";
  process.env.NEXT_PUBLIC_API_URL = "https://backend.example.com";
  vi.restoreAllMocks();
});

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
});

describe("POST /api/lead", () => {
  it("refuses to run when the intake secret is not configured", async () => {
    delete process.env.INTAKE_WEBHOOK_SECRET;
    const { POST } = await loadRoute();

    const res = await POST(post(VALID));

    expect(res.status).toBe(503);
  });

  it("never exposes the secret in its response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await loadRoute();

    const res = await POST(post(VALID));
    const text = await res.text();

    expect(text).not.toContain("test-secret");
  });

  it("forwards the secret to the backend as a header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await loadRoute();

    await POST(post(VALID));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://backend.example.com/api/intake/web-form");
    expect(init.headers["X-Intake-Secret"]).toBe("test-secret");
  });

  it("silently accepts a honeypot submission without calling the backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await loadRoute();

    const res = await POST(post({ ...VALID, company: "spam-bot" }));

    expect(res.status).toBe(200);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a submission with neither phone nor email", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await loadRoute();

    const res = await POST(post({ name: "No Contact", address: "123 Main St" }));

    expect(res.status).toBe(422);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts an email-only submission", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await loadRoute();

    const res = await POST(post({ email: "seller@example.com" }));

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalled();
  });

  it("rejects malformed json", async () => {
    const { POST } = await loadRoute();
    const bad = new Request("http://localhost/api/lead", { method: "POST", body: "not json" });

    const res = await POST(bad);

    expect(res.status).toBe(400);
  });

  it("reports a backend failure without leaking upstream detail", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("internal supabase trace", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await loadRoute();

    const res = await POST(post(VALID));
    const body = await res.json();

    expect(res.status).toBe(502);
    expect(JSON.stringify(body)).not.toContain("supabase");
  });

  it("handles the backend being unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("ECONNREFUSED"))
    );
    const { POST } = await loadRoute();

    const res = await POST(post(VALID));

    expect(res.status).toBe(502);
  });

  it("passes through the seller's qualifying answers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await loadRoute();

    await POST(post({ ...VALID, timeline: "ASAP", condition: "needs major work" }));

    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent.timeline).toBe("ASAP");
    expect(sent.condition).toBe("needs major work");
  });
});
