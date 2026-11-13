import { Cpu } from "lucide-react";
import { Card, ConceptTag, Eyebrow, IconTile, PageHeader } from "../components/ui";
import { PROVIDERS } from "../lib/providers";

const NOTES: Record<(typeof PROVIDERS)[number]["id"], string> = {
  gemini: "Google AI Studio key. Supports real tool calling; returns content blocks, which the backend flattens to one string.",
  openai: "OpenAI API key. Supports real tool calling.",
  mock: "Echoes the request and never calls a tool. For development and tests: no key, no cost.",
};

export function ProvidersPage() {
  return (
    <div className="mx-auto max-w-[1180px]">
      <PageHeader
        title="Providers"
        description="LLM providers the backend supports. One is active, chosen on the server by LLM_PROVIDER and LLM_MODEL."
        extra={<ConceptTag title="Choosing a provider from the UI is a design concept: the API neither reports nor changes it." />}
      />

      <div className="grid gap-6 md:grid-cols-3">
        {PROVIDERS.map((p) => (
          <Card key={p.id} className="flex flex-col p-5">
            <div className="flex items-center gap-3">
              <IconTile className="size-10">
                <Cpu aria-hidden className="size-[18px]" strokeWidth={1.8} />
              </IconTile>
              <div>
                <h2 className="text-lg font-semibold text-white">{p.name}</h2>
                <p className="font-mono text-xs text-ink-300">{p.env}</p>
              </div>
            </div>
            <p className="mt-4 text-[15px] leading-relaxed text-ink-300">{NOTES[p.id]}</p>
            <div className="mt-auto pt-5">
              <Eyebrow>Default model</Eyebrow>
              <p className="mt-1.5 font-mono text-sm text-white">{p.id === "mock" ? "–" : p.detail}</p>
            </div>
          </Card>
        ))}
      </div>

      <Card className="mt-6 p-5">
        <h2 className="text-lg font-semibold text-white">Switching providers</h2>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-300">
          Set these on the backend and restart it. Keys live only on the server and never reach this app.
        </p>
        <pre className="mt-4 overflow-x-auto rounded-xl border border-ink-700 bg-ink-900 p-4 font-mono text-[13px] leading-6 text-ink-300">
          {"LLM_PROVIDER=gemini            # gemini | openai | mock\nLLM_MODEL=gemini-flash-lite-latest\nLLM_API_KEY=<server-side secret>"}
        </pre>
      </Card>
    </div>
  );
}
