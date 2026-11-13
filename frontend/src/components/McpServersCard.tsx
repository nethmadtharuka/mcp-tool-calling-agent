import { Folder, GitBranch } from "lucide-react";
import { Link } from "react-router";
import { Card, Eyebrow, Pill, ReadOnlyPill } from "./ui";

export const NOT_REPORTED_TITLE = "The API doesn't expose MCP server status; the agent skips a server that's down.";

const SERVERS = [
  { name: "GitHub MCP", icon: GitBranch, detail: "Repositories your token can read" },
  { name: "Filesystem MCP", icon: Folder, detail: "/projects · .env hidden" },
];

export function McpServersCard() {
  return (
    <Card className="p-5">
      <Eyebrow>Connected MCP tools</Eyebrow>
      <ul className="mt-4 space-y-3">
        {SERVERS.map(({ name, icon: Icon, detail }) => (
          <li key={name} className="rounded-xl border border-ink-700 bg-ink-900/60 p-3.5">
            <div className="flex items-center justify-between gap-2">
              <p className="flex items-center gap-2.5 text-sm text-white">
                <Icon aria-hidden className="size-[18px]" strokeWidth={1.8} />
                {name}
              </p>
              <Pill tone="neutral" title={NOT_REPORTED_TITLE}>
                Not reported
              </Pill>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <p className="font-mono text-xs leading-relaxed text-ink-500">{detail}</p>
              <ReadOnlyPill />
            </div>
          </li>
        ))}
      </ul>
      <Link to="/tools" className="mt-3 inline-flex h-9 items-center rounded-lg px-3 text-[15px] font-medium text-white/90 transition-colors hover:bg-white/5 hover:text-white">
        Review tools
      </Link>
    </Card>
  );
}
