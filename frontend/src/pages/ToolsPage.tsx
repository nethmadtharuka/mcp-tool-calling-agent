import { Folder, GitBranch, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Disclosure } from "../components/Disclosure";
import { NOT_REPORTED_TITLE } from "../components/McpServersCard";
import { Card, Eyebrow, IconTile, PageHeader, Pill, ReadOnlyPill } from "../components/ui";
import { MAX_TOOL_STEPS } from "../config";
import { FILESYSTEM_ALLOWLIST, FILESYSTEM_ROOT, GITHUB_DEFAULT_TOOLSETS } from "../lib/mcp";

interface Server {
  name: string;
  icon: LucideIcon;
  subtitle: string;
  scope: string;
  chipsLabel: string;
  chips: readonly string[];
  chipsNote: string;
  technical: string[];
  connection: string[];
}

const SERVERS: Server[] = [
  {
    name: "GitHub MCP",
    icon: GitBranch,
    subtitle: "streamable HTTP · github-mcp-server",
    scope: "Scope: repositories your token can read",
    chipsLabel: "Toolsets (GITHUB_TOOLSETS default)",
    chips: GITHUB_DEFAULT_TOOLSETS,
    chipsNote: "The server discovers the exact tools at runtime; the API doesn’t list them.",
    technical: [
      "Image: ghcr.io/github/github-mcp-server v2.0.2 (pinned by digest)",
      "Headers: X-MCP-Readonly: true · X-MCP-Toolsets",
      "Client: app/agent/mcp_tools.py",
    ],
    connection: [
      "Transport: streamable HTTP",
      "Mode: --read-only (server flag)",
      "Auth: PAT sent per request; server holds none",
      "Default URL: http://github-mcp:8082/",
    ],
  },
  {
    name: "Filesystem MCP",
    icon: Folder,
    subtitle: "streamable HTTP · filesystem server",
    scope: "/projects (mounted read-only, .env hidden)",
    chipsLabel: "Read-only allowlist",
    chips: FILESYSTEM_ALLOWLIST,
    chipsNote: "Write tools (write_file, edit_file, move_file, create_directory) are filtered out before the LLM sees them.",
    technical: [
      "Image: mcp/filesystem behind supergateway (stdio → HTTP)",
      "Sessions: stateful, reaped after 60 s idle",
      "Network: no internet access",
    ],
    connection: [
      "Transport: streamable HTTP",
      `Mount: ${FILESYSTEM_ROOT} (read-only)`,
      "Hidden: .env files (never mounted)",
      "Default URL: http://filesystem-mcp:8000/mcp",
    ],
  },
];

function Mono({ lines }: { lines: string[] }) {
  return (
    <pre className="font-mono text-[13px] leading-6 break-words whitespace-pre-wrap text-ink-300">
      {lines.join("\n")}
    </pre>
  );
}

function ServerColumn({ s }: { s: Server }) {
  const Icon = s.icon;
  return (
    <div className="min-w-0 space-y-4">
      <Card className="p-5">
        <div className="flex items-start gap-3.5">
          <IconTile className="size-10">
            <Icon aria-hidden className="size-[18px]" strokeWidth={1.8} />
          </IconTile>
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-semibold text-white">{s.name}</h2>
            <p className="mt-0.5 truncate font-mono text-xs text-ink-300">{s.subtitle}</p>
          </div>
          <Pill tone="neutral" title={NOT_REPORTED_TITLE}>
            Not reported
          </Pill>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <ReadOnlyPill />
          <p className="font-mono text-[13px] text-ink-300">{s.scope}</p>
        </div>

        <Eyebrow className="mt-6">{s.chipsLabel}</Eyebrow>
        <ul className="mt-3 flex flex-wrap gap-2">
          {s.chips.map((c) => (
            <li key={c} className="rounded-md border border-ink-700 bg-ink-900/60 px-2.5 py-1 font-mono text-[13px] text-white/90">
              {c}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[13px] text-ink-500">{s.chipsNote}</p>

        <Disclosure label="Technical information" className="mt-5 border-t border-ink-700 pt-4" buttonClassName="gap-3">
          <div className="pt-3 pl-7">
            <Mono lines={s.technical} />
          </div>
        </Disclosure>
      </Card>

      <Card className="overflow-hidden">
        <Disclosure
          defaultOpen
          label="Connection details"
          buttonClassName="px-5 py-3.5 [&[aria-expanded=true]]:border-b [&[aria-expanded=true]]:border-ink-700"
        >
          <div className="px-5 py-4">
            <Mono lines={s.connection} />
          </div>
        </Disclosure>
      </Card>
    </div>
  );
}

function Policy({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900/50 p-4">
      <p className="text-[15px] text-white">{title}</p>
      <p className="mt-1.5 text-[15px] leading-relaxed text-ink-300">{children}</p>
    </div>
  );
}

export function ToolsPage() {
  return (
    <div className="mx-auto max-w-[1180px]">
      <PageHeader title="Connected Tools" description="MCP servers the agent can call. Both are read-only by policy." />

      <div className="grid gap-6 xl:grid-cols-2">
        {SERVERS.map((s) => (
          <ServerColumn key={s.name} s={s} />
        ))}
      </div>

      <Card className="mt-6 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-white">Access policy</h2>
          <ReadOnlyPill />
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <Policy title="GitHub">Read-only server mode; write tools are not exposed to the agent.</Policy>
          <Policy title="Filesystem">Authorised directory is mounted read-only. Files named .env are hidden.</Policy>
          <Policy title="Step limit">At most {MAX_TOOL_STEPS} tool steps per request, then the run stops with a notice.</Policy>
        </div>
      </Card>
    </div>
  );
}
