"""Claude MCP Python Client — async client for `claude mcp serve`.

Connects to `claude mcp serve` via stdio using the `mcp` package,
exposing tools (Bash, Read, Write, Edit, etc.) to Python programs.

Usage:
    async with ClaudeMCPClient() as client:
        result = await client.bash("ls -la /tmp")
        answer = await client.prompt("What files are in /tmp?")
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import anyio
import mcp.client.stdio as stdio
import mcp.types as types
from mcp import ClientSession

logger = logging.getLogger(__name__)


class ClaudeMCPError(Exception):
  """Base exception for Claude MCP Client errors."""


class ConnectionError(ClaudeMCPError):
  """Raised when connection to claude mcp serve fails."""


class ToolError(ClaudeMCPError):
  """Raised when a tool call returns an error."""


def _parse_result(result: types.CallToolResult) -> dict[str, Any]:
  """Convert a CallToolResult to a plain dict.

    Handles TextContent, ImageContent, EmbeddedResource, and
    structuredContent, returning a JSON-serializable dict.

    Special handling for Read tool: parses the JSON response and
    extracts the file content as a plain string.
    """
  output: dict[str, Any] = {"isError": result.isError}

  # Text content
  texts = [c.text for c in result.content if isinstance(c, types.TextContent)]
  if texts:
    raw = "\n".join(texts)

    # Special handling for Read tool response
    # Read returns: {"type":"text","file":{"filePath":"...","content":"...","numLines":...}}
    try:
      parsed = json.loads(raw)
      if isinstance(parsed, dict) and parsed.get("type") == "text" and "file" in parsed:
        file_info = parsed["file"]
        output["content"] = file_info.get("content", "")
        output["filePath"] = file_info.get("filePath", "")
        output["numLines"] = file_info.get("numLines", 0)
        output["totalLines"] = file_info.get("totalLines", 0)
        return output
    except (json.JSONDecodeError, TypeError):
      pass

    output["content"] = raw

  # Image content
  images = [c for c in result.content if isinstance(c, types.ImageContent)]
  if images:
    output["images"] = [
      {"data": img.data, "mimeType": img.mimeType} for img in images
    ]

  # Embedded resources
  resources = [c for c in result.content if isinstance(c, types.EmbeddedResource)]
  if resources:
    output["resources"] = [
      {
        "type": isinstance(r, types.EmbeddedResource),
        "resource": r,
      }
      for r in resources
    ]

  # Structured content (tool-specific structured output)
  if result.structuredContent is not None:
    output["structuredContent"] = result.structuredContent

  return output


class ClaudeMCPClient:
  """Async client for `claude mcp serve` via stdio.

    Usage:
        async with ClaudeMCPClient() as client:
            tools = await client.list_tools()
            result = await client.call_tool("bash", {"command": "ls"})
  """

  def __init__(
      self,
      command: str = "claude",
      mcp_args: list[str] | None = None,
      env: dict[str, str] | None = None,
      cwd: str | None = None,
      inherit_env: bool = True,
  ):
    """Initialize connection parameters.

        Args:
            command: Command to run the MCP server (default: "claude").
            mcp_args: Extra arguments for `claude mcp serve` (default: None).
            env: Environment variables passed to the subprocess.
            cwd: Working directory for the subprocess.
            inherit_env: Inherit parent process environment variables.
                When True (default), os.environ is used as the base and
                `env` overrides specific variables. When False, only the
                minimal default environment (HOME, SHELL, PATH, etc.) is used.
      """
    self._command = command
    self._mcp_args = mcp_args or []
    self._env = env
    self._cwd = cwd
    self._inherit_env = inherit_env
    self._session: ClientSession | None = None
    self._stdio_ctx: Any = None
    self._read: Any = None
    self._write: Any = None

  # ------------------------------------------------------------------
  # Context manager
  # ------------------------------------------------------------------

  async def __aenter__(self) -> ClaudeMCPClient:
    """Start stdio connection and initialize the session."""
    await self.connect()
    return self

  async def __aexit__(self, *exc: Any) -> None:
    """Close the connection."""
    await self.close()

  # ------------------------------------------------------------------
  # Connection lifecycle
  # ------------------------------------------------------------------

  async def connect(self) -> None:
    """Establish stdio connection and initialize the MCP session."""
    # Build environment: inherit parent env by default, then override
    if self._inherit_env:
      base_env = dict(__import__("os").environ)
      if self._env:
        base_env.update(self._env)
      env = base_env
    else:
      env = self._env

    server_params = stdio.StdioServerParameters(
      command=self._command,
      args=["mcp", "serve"] + self._mcp_args,
      env=env,
      cwd=self._cwd,
    )

    self._stdio_ctx = stdio.stdio_client(server_params)
    try:
      self._read, self._write = await self._stdio_ctx.__aenter__()
    except Exception as exc:
      self._stdio_ctx = None
      raise ConnectionError(f"Failed to open stdio transport: {exc}") from exc

    self._session = ClientSession(read_stream=self._read, write_stream=self._write)

    try:
      await self._session.__aenter__()
      await self._session.initialize()
      logger.info("Connected to claude mcp serve")
    except Exception as exc:
      await self._stdio_ctx.__aexit__(None, None, None)
      self._stdio_ctx = None
      self._session = None
      raise ConnectionError(f"Failed to initialize session: {exc}") from exc

  async def close(self) -> None:
    """Close the MCP session and stdio transport."""
    if self._session is not None:
      try:
        await self._session.__aexit__(None, None, None)
      except Exception as exc:
        logger.warning("Error closing session: %s", exc)
      self._session = None

    if self._stdio_ctx is not None:
      try:
        await self._stdio_ctx.__aexit__(None, None, None)
      except Exception as exc:
        logger.warning("Error closing stdio transport: %s", exc)
      self._stdio_ctx = None

    self._read = None
    self._write = None
    logger.info("Connection closed")

  # ------------------------------------------------------------------
  # Properties
  # ------------------------------------------------------------------

  @property
  def is_connected(self) -> bool:
    """Return True if connected to claude mcp serve."""
    return self._session is not None

  # ------------------------------------------------------------------
  # Core methods
  # ------------------------------------------------------------------

  async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a tool exposed by claude mcp serve.

        Args:
            name: Tool name (e.g. "bash", "read", "write", "edit").
            arguments: Tool arguments as a dict.

        Returns:
            Parsed result as a dict.

        Raises:
            ToolError: If the tool returns isError=True.
            ConnectionError: If not connected.
    """
    if self._session is None:
      raise ConnectionError("Not connected. Use 'async with ClaudeMCPClient()' or call connect() first.")

    result = await self._session.call_tool(name, arguments or {})

    output = _parse_result(result)

    if result.isError:
      msg = output.get("content", "Unknown error")
      raise ToolError(f"Tool '{name}' returned error: {msg}")

    return output

  async def prompt(self, text: str, system_prompt: str | None = None) -> str:
    """Send a natural language prompt via the bash tool.

        Executes `claude -p "text"` through the bash tool to get
        a natural language response from Claude Code.

        Args:
            text: The prompt text to send.
            system_prompt: Optional system prompt (not yet supported
                through this shortcut).

        Returns:
            Claude's response as a string.

        Raises:
            ToolError: If the tool call fails.
    """
    cmd = f'claude -p {repr(text)}'
    result = await self.call_tool("Bash", {"command": cmd})
    return result.get("content", "")

  # ------------------------------------------------------------------
  # Tool shortcuts
  # ------------------------------------------------------------------

  async def bash(
      self,
      command: str,
      description: str = "",
      timeout: int = 120000,
  ) -> dict[str, Any]:
    """Shortcut for the bash tool.

        Args:
            command: Shell command to execute.
            description: Description of what the command does.
            timeout: Timeout in milliseconds.

        Returns:
            Tool result dict.
    """
    args: dict[str, Any] = {"command": command}
    if description:
      args["description"] = description
    if timeout != 120000:
      args["timeout"] = timeout
    return await self.call_tool("Bash", args)

  async def read(self, file_path: str) -> str:
    """Shortcut for the read tool.

        Args:
            file_path: Absolute path to the file.

        Returns:
            File content as a string.
    """
    result = await self.call_tool("Read", {"file_path": file_path})
    return result.get("content", "")

  async def write(self, file_path: str, content: str) -> dict[str, Any]:
    """Shortcut for the write tool.

        Args:
            file_path: Absolute path to the file.
            content: Content to write.

        Returns:
            Tool result dict.
    """
    return await self.call_tool("Write", {"file_path": file_path, "content": content})

  async def edit(
      self,
      file_path: str,
      old_string: str,
      new_string: str,
      replace_all: bool = False,
  ) -> dict[str, Any]:
    """Shortcut for the edit tool.

        Args:
            file_path: Absolute path to the file.
            old_string: Text to replace.
            new_string: Replacement text.
            replace_all: Replace all occurrences.

        Returns:
            Tool result dict.
    """
    args: dict[str, Any] = {
      "file_path": file_path,
      "old_string": old_string,
      "new_string": new_string,
    }
    if replace_all:
      args["replace_all"] = True
    return await self.call_tool("Edit", args)

  async def list_tools(self) -> list[dict[str, Any]]:
    """List available tools.

        Returns:
            List of tool dicts with name, description, inputSchema.
    """
    if self._session is None:
      raise ConnectionError("Not connected.")

    result = await self._session.list_tools()
    return [
      {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.inputSchema,
      }
      for tool in result.tools
    ]
