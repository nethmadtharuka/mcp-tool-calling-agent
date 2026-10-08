# mcp/filesystem (a stdio-only MCP server) fronted by supergateway, which
# exposes it as streamable HTTP. Stateful mode: one stdio child per MCP
# session, reaped after --sessionTimeout of inactivity.
# Both pinned so every rebuild is identical (see README "Updating pinned
# versions").
FROM mcp/filesystem@sha256:35fcf0217ca0d5bf7b0a5bd68fb3b89e08174676c0e0b4f431604512cf7b3f67

RUN npm install -g supergateway@4.1.0 && npm cache clean --force

# The base image runs as root; node (uid 1000) ships with it.
USER node

EXPOSE 8000
ENTRYPOINT ["supergateway", \
    "--stdio", "node /app/dist/index.js /projects/mcp-tool-calling-agent", \
    "--outputTransport", "streamableHttp", "--stateful", \
    "--sessionTimeout", "60000", "--port", "8000"]
