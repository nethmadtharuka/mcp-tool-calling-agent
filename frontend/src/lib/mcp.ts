/**
 * Static facts about the two MCP servers, taken from the backend source
 * and deployment files. The API exposes none of this at runtime (no
 * status, no tool list), so the UI labels it as configuration, not as
 * live discovery.
 */

/** _FILESYSTEM_READONLY_TOOLS in app/agent/mcp_tools.py. */
export const FILESYSTEM_ALLOWLIST = [
  "read_file",
  "read_text_file",
  "read_multiple_files",
  "read_media_file",
  "list_directory",
  "list_directory_with_sizes",
  "directory_tree",
  "search_files",
  "get_file_info",
  "list_allowed_directories",
] as const;

/** Default GITHUB_TOOLSETS in app/core/config.py. */
export const GITHUB_DEFAULT_TOOLSETS = ["repos", "issues", "pull_requests"] as const;

export const FILESYSTEM_ROOT = "/projects/mcp-tool-calling-agent";
