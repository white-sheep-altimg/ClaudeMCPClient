"""Example usage of ClaudeMCPClient.

Demonstrates:
- Connection management (async with)
- Tool listing
- File operations (write, read, edit)
- Session persistence (multiple calls without reconnecting)
"""

import asyncio
import logging

from claude_mcp_client import ClaudeMCPClient, ConnectionError, ToolError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
  try:
    async with ClaudeMCPClient() as client:
      # Connection status
      print(f"Connected: {client.is_connected}")

      # List available tools
      print("\n--- Available Tools ---")
      tools = await client.list_tools()
      for tool in tools:
        print(f"  - {tool['name']}")
        print(f"  Total: {len(tools)} tools")

      # Write a file
      print("\n--- Write: /tmp/hello.txt ---")
      await client.read("/tmp/hello.txt")  # いちど読み込まないとWriteできない（Claude Codeの仕様）
      await client.write("/tmp/hello.txt", "Hello MCP!")
      print("Written.")

      # Read the file
      print("\n--- Read: /tmp/hello.txt ---")
      content = await client.read("/tmp/hello.txt")
      print(f"Content: {content}")

      # Edit the file
      print("\n--- Edit: /tmp/hello.txt ---")
      await client.edit("/tmp/hello.txt", "Hello", "Goodbye")
      content = await client.read("/tmp/hello.txt")
      print(f"Content after edit: {content}")

      # Bash execution (may fail in restricted environments)
      print("\n--- Bash: echo hello ---")
      try:
        result = await client.bash("echo hello")
        print(result.get("content", ""))
      except ToolError as exc:
        print(f"Bash tool unavailable (environment restriction): {exc}")

      # Prompt: "こんにちは。お名前を教えてください。"
      print("\n--- Prompt: What files are in /tmp? ---")
      answer = await client.prompt("こんにちは。お名前を教えてください。")
      print(answer)

  except ConnectionError as exc:
    logger.error("Connection failed: %s", exc)
  except ToolError as exc:
    logger.error("Tool error: %s", exc)


if __name__ == "__main__":
  asyncio.run(main())
