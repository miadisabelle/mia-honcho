# Honcho MCP server for the /v3 API — see server.py for why it exists.
FROM python:3.12-slim

WORKDIR /app

# Pinned so a rebuild months from now produces the same server. `mcp` carries
# the streamable-HTTP transport; starlette and uvicorn come with it, but are
# named explicitly because this file imports them directly.
RUN pip install --no-cache-dir \
      "mcp>=1.9,<2" \
      "httpx>=0.27,<1" \
      "uvicorn>=0.30,<1" \
      "starlette>=0.37,<1"

COPY server.py .

EXPOSE 8081

# Refuses to start without HONCHO_MCP_BEARER_TOKEN — deliberate, see server.py.
CMD ["python", "server.py"]
