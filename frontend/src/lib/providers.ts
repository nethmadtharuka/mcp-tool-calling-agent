/** The providers app/agent/llm.py supports, with config.py's default models. */
export const PROVIDERS = [
  { id: "gemini", name: "Gemini", detail: "gemini-flash-lite-latest", env: "LLM_PROVIDER=gemini" },
  { id: "openai", name: "OpenAI", detail: "gpt-4o-mini", env: "LLM_PROVIDER=openai" },
  { id: "mock", name: "Mock", detail: "No API key needed", env: "LLM_PROVIDER=mock" },
] as const;
