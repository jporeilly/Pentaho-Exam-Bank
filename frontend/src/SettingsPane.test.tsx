import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsPane } from "./SettingsPane";
import type { DocsMcpStatus, Settings, SettingsResponse } from "./api";

const MCP_OK: DocsMcpStatus = {
  enabled: true, url: "https://docs.pentaho.com/~gitbook/mcp", ok: true,
  server: "Pentaho MCP Server", version: "0.27.2",
  tools: ["searchDocumentation", "getPage", "askQuestion", "sendFeedback"],
  ms: 640, searchTool: true, error: "",
};

function settings(over: Partial<Settings> = {}): Settings {
  return {
    sme_name: "Jo Bloggs",
    ai_provider: "ollama",
    anthropic_model: "claude-opus-5",
    openai_model: "gpt-4o",
    ollama_url: "http://localhost:11434",
    ollama_model: "gemma4:12b",
    ollama_enabled: true,
    ollama_num_ctx: 8192,
    docs_mcp_enabled: true,
    docs_mcp_url: "https://docs.pentaho.com/~gitbook/mcp",
    pcm_courses_dir: "C:/Projects/Pentaho-Content-Manager/courses",
    output_folder: "C:/Projects/Pentaho-Exam-Bank/assets/questions",
    duplicate_threshold: 0.85,
    validation_threshold: 0.7,
    questions_per_page: 25,
    default_difficulty: "Medium",
    default_bloom_level: "Apply",
    auto_export_on_save: true,
    default_export_format: "csv",
    auto_backup_enabled: false,
    auto_backup_interval_hours: 24,
    auto_backup_max_count: 5,
    ...over,
  };
}

function response(over: Partial<SettingsResponse> = {}): SettingsResponse {
  return {
    settings: settings(),
    providerKeys: { anthropic: false, openai: false },
    envOverridden: [],
    envNames: {
      ollama_url: "OLLAMA_URL",
      ollama_model: "OLLAMA_MODEL",
      ollama_num_ctx: "OLLAMA_NUM_CTX",
      ollama_enabled: "OLLAMA_ENABLED",
    },
    choices: {
      providers: ["ollama", "anthropic", "openai"],
      difficulties: ["Easy", "Medium", "Hard"],
      bloomLevels: ["Remember", "Understand", "Apply"],
      pageSizes: [10, 25, 50, 100],
      exportFormats: [{ format: "csv", label: "CSV" }, { format: "docx", label: "Word (.docx)" }],
    },
    paths: {
      database: "C:/Projects/Pentaho-Exam-Bank/assets/db/exam_bank.db",
      config: "C:/Projects/Pentaho-Exam-Bank/assets/config/config.json",
    },
    autoExport: { target: "C:/Exports/exam-bank.csv", at: "2026-09-30T10:00:00", path: "", count: 311, error: "" },
    autoBackup: { at: "", path: "", pruned: 0, error: "" },
    ...over,
  };
}

function mockApi(handlers: {
  get?: SettingsResponse;
  put?: SettingsResponse | { status: number; detail: string };
  mcp?: DocsMcpStatus;
  gpu?: unknown;
} = {}) {
  const calls: Array<{ method: string; body: unknown }> = [];
  const probes: string[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (String(url).includes("/api/docs-mcp/status")) {
      probes.push(new URL(String(url), "http://x").searchParams.get("url") ?? "");
      return Promise.resolve(new Response(JSON.stringify(handlers.mcp ?? MCP_OK), {
        status: 200, headers: { "Content-Type": "application/json" },
      }));
    }
    if (String(url).includes("/api/settings/gpu")) {
      return Promise.resolve(new Response(JSON.stringify(handlers.gpu ?? {
        ollama: true, model: "gemma4:12b", gpus: [], largestGpuGb: 0, models: [], loaded: [], advice: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } }));
    }
    calls.push({ method, body: init?.body ? JSON.parse(String(init.body)) : null });

    const json = (body: unknown, status = 200) =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );

    if (method === "PUT") {
      const r = handlers.put ?? handlers.get ?? response();
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    return json(handlers.get ?? response());
  });
  return Object.assign(calls, { probes });
}

afterEach(() => vi.unstubAllGlobals());

describe("what is shown", () => {
  it("says plainly that keys are not stored here", async () => {
    mockApi();
    render(<SettingsPane />);

    expect(await screen.findByText(/never stored by this app/)).toBeInTheDocument();
  });

  it("offers no field for an API key", async () => {
    // The one thing this pane must not have. A field implies a stored value.
    mockApi({ get: response({ settings: settings({ ai_provider: "anthropic" }) }) });
    render(<SettingsPane />);

    await screen.findByText(/is not set/);
    for (const box of screen.getAllByRole("textbox")) {
      expect((box.getAttribute("aria-label") ?? "").toLowerCase()).not.toContain("key");
    }
    expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument();
  });

  it("says why a provider cannot be used when its key is absent", async () => {
    mockApi({ get: response({ settings: settings({ ai_provider: "anthropic" }) }) });
    render(<SettingsPane />);

    expect(await screen.findByText(/cannot be used/)).toBeInTheDocument();
    expect(screen.getByText("ANTHROPIC_API_KEY")).toBeInTheDocument();
  });

  it("shows a key as present without showing the key", async () => {
    mockApi({
      get: response({
        settings: settings({ ai_provider: "anthropic" }),
        providerKeys: { anthropic: true, openai: false },
      }),
    });
    render(<SettingsPane />);

    expect(await screen.findByText(/is set/)).toBeInTheDocument();
  });

  it("shows where the database and config actually live", async () => {
    // Shown, never editable: moving the database from a form would leave the
    // running app holding a handle to the old file.
    mockApi();
    render(<SettingsPane />);

    expect(await screen.findByText(/exam_bank\.db/)).toBeInTheDocument();
    expect(screen.getByText(/config\.json/)).toBeInTheDocument();
  });
});

describe("settings the environment governs", () => {
  it("will not let one be edited, and names the variable", async () => {
    // Left editable it would save, appear to work, and revert on the next
    // start — worse than being told it is set elsewhere.
    mockApi({ get: response({ envOverridden: ["ollama_model"] }) });
    render(<SettingsPane />);

    expect(await screen.findByLabelText("Model")).toBeDisabled();
    expect(screen.getByText("OLLAMA_MODEL")).toBeInTheDocument();
    expect(screen.getByText(/would not survive a restart/)).toBeInTheDocument();
  });

  it("leaves a field alone when nothing governs it", async () => {
    mockApi();
    render(<SettingsPane />);

    expect(await screen.findByLabelText("Model")).toBeEnabled();
  });
});

describe("saving", () => {
  it("sends only what changed", async () => {
    // Sending the whole set would re-submit env-governed fields nobody
    // touched, and could fail a save over a path that changed elsewhere.
    const calls = mockApi();
    render(<SettingsPane />);

    const name = await screen.findByLabelText("Your name");
    await userEvent.clear(name);
    await userEvent.type(name, "Someone Else");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.body).toEqual({ settings: { sme_name: "Someone Else" } });
  });

  it("cannot be saved when nothing has changed", async () => {
    mockApi();
    render(<SettingsPane />);

    expect(await screen.findByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("shows the server's refusal rather than inventing one", async () => {
    mockApi({
      put: {
        status: 400,
        detail: "The Content Manager courses directory does not exist: C:/nope",
      },
    });
    render(<SettingsPane />);

    const dir = await screen.findByLabelText("Content Manager courses");
    await userEvent.clear(dir);
    await userEvent.type(dir, "C:/nope");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/does not exist: C:\/nope/)).toBeInTheDocument();
  });

  it("keeps the rejected value on screen so it can be corrected", async () => {
    // Reverting it would make the author retype what they meant, having been
    // told only that it was wrong.
    mockApi({ put: { status: 400, detail: "does not exist" } });
    render(<SettingsPane />);

    const dir = await screen.findByLabelText("Content Manager courses");
    await userEvent.clear(dir);
    await userEvent.type(dir, "C:/nope");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/does not exist/);

    expect(screen.getByLabelText("Content Manager courses")).toHaveValue("C:/nope");
  });

  it("confirms a save and settles clean", async () => {
    mockApi({ put: response({ settings: settings({ sme_name: "Someone Else" }) }) });
    render(<SettingsPane />);

    const name = await screen.findByLabelText("Your name");
    await userEvent.clear(name);
    await userEvent.type(name, "Someone Else");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});

describe("the Pentaho docs connection", () => {
  it("shows the server answering: who, how fast, which tools", async () => {
    mockApi();
    render(<SettingsPane />);

    expect(await screen.findByText(/Pentaho MCP Server 0\.27\.2, answered in 640 ms/)).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText(/Tools: searchDocumentation, getPage, askQuestion, sendFeedback\./)).toBeInTheDocument();
    expect(screen.getByText(/Search tool available/)).toBeInTheDocument();
  });

  it("says why it is not connected", async () => {
    mockApi({ mcp: { ...MCP_OK, ok: false, tools: [], ms: null, searchTool: false, error: "Could not reach the server: getaddrinfo failed." } });
    render(<SettingsPane />);

    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    expect(screen.getByText(/getaddrinfo failed/)).toBeInTheDocument();
  });

  it("warns when the server has no search tool", async () => {
    mockApi({ mcp: { ...MCP_OK, tools: ["getPage"], searchTool: false } });
    render(<SettingsPane />);

    expect(await screen.findByText(/AI Chat cannot search this server/)).toBeInTheDocument();
  });

  it("tests the address typed in the box, before it is saved", async () => {
    const calls = mockApi();
    render(<SettingsPane />);
    const box = await screen.findByRole("textbox", { name: "MCP server" });

    await userEvent.clear(box);
    await userEvent.type(box, "https://other.example/~gitbook/mcp");
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));

    await screen.findByText("Connected");
    expect(calls.probes.at(-1)).toBe("https://other.example/~gitbook/mcp");
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(0);
  });

  it("does not contact the docs site on opening when the connection is off", async () => {
    const calls = mockApi({ get: response({ settings: settings({ docs_mcp_enabled: false }) }) });
    render(<SettingsPane />);

    expect(await screen.findByText(/Off: AI Chat does not contact the docs site/)).toBeInTheDocument();
    expect(calls.probes).toHaveLength(0);
    expect(screen.getByRole("checkbox", { name: "Search docs.pentaho.com from AI Chat" })).not.toBeChecked();
  });

  it("saves the switch", async () => {
    const calls = mockApi();
    render(<SettingsPane />);

    await userEvent.click(await screen.findByRole("checkbox", { name: "Search docs.pentaho.com from AI Chat" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body).toEqual({ settings: { docs_mcp_enabled: false } });
  });
});

describe("export and backups", () => {
  // Three settings with nothing behind them until 1.10.0.
  it("shows where auto-export writes, and saves the backup schedule", async () => {
    const calls = mockApi();
    render(<SettingsPane />);

    expect(await screen.findByText("C:/Exports/exam-bank.csv")).toBeInTheDocument();
    expect(screen.getByText(/Last written 2026-09-30 10:00:00: 311 questions/)).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Back up the bank automatically"));
    const every = screen.getByLabelText("Every (hours)");
    await userEvent.clear(every);
    await userEvent.type(every, "6");
    await userEvent.selectOptions(screen.getByLabelText("Default export format"), "docx");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const sent = (calls.find((c) => c.method === "PUT")!.body as { settings: Record<string, unknown> }).settings;
    expect(sent).toMatchObject({ auto_backup_enabled: true, auto_backup_interval_hours: 6,
                                 default_export_format: "docx" });
  });
});

describe("GPU advice", () => {
  // get_gpu_info and a model catalogue sat in the code since the NiceGUI days
  // with nothing on screen; the catalogue also added the two cards together.
  it("says what the machine can run, and lists every pulled model's fit", async () => {
    mockApi({ gpu: {
      ollama: true, model: "gemma4:12b", largestGpuGb: 12,
      gpus: [{ name: "NVIDIA GeForce RTX 3060", totalGb: 12, freeGb: 11 },
             { name: "NVIDIA GeForce RTX 3060", totalGb: 12, freeGb: 10 }],
      models: [
        { name: "gemma4:12b", sizeGb: 7, needGb: 8.7, fit: "fits", selected: true },
        { name: "gemma3:27b", sizeGb: 16.2, needGb: 18.8, fit: "split", selected: false },
      ],
      loaded: [],
      advice: ["2 × NVIDIA GeForce RTX 3060, 12 GB each. A model has to fit on ONE card to run at full speed.",
               "gemma4:12b needs about 8.7 GB and fits on one 12 GB card, so it runs on the GPU at full speed."],
    } });
    render(<SettingsPane />);

    expect(await screen.findByText(/has to fit on ONE card/)).toBeInTheDocument();
    expect(screen.getByText("gemma4:12b (in use)")).toBeInTheDocument();
    expect(screen.getByText("Needs more than one card")).toBeInTheDocument();
  });

  it("is not shown for a hosted provider", async () => {
    mockApi({ get: response({ settings: settings({ ai_provider: "anthropic" }) }) });
    render(<SettingsPane />);

    await screen.findByText("The model");
    expect(screen.queryByText("GPU advice")).not.toBeInTheDocument();
  });
});
