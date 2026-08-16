# Claude MCP Python クライアント 設計書

## Context

`claude mcp serve` は stdioベースのMCPサーバーとしてClaude Codeのツール（Bash, Read, Write, Edit, WebSearch等29個）を公開する。Pythonの`mcp`パッケージ（v1.28.1, Python 3.12）でクライアントを作成し、他プログラムから呼び出せるようにする。

**要件:**
- セッションを維持（再接続不要）
- 他プログラムから呼び出し可能
- ツールの引数でプロンプトを指定可能
- Python 3.12互換（`python` コマンド使用）

## 構成

```
Pythonスクリプト (ClaudeMCPClient)
    ↓ asyncio + stdio
claude mcp serve (MCPサーバー)
    ↓
Claude Code (セッション維持中)
```

## 作成ファイル

### 1. `claude_mcp_client.py` — メインクライアント

```python
class ClaudeMCPClient:
    """claude mcp serve への非同期クライアント"""

    def __init__(self, command: str = "claude", mcp_args: list[str] | None = None,
                 env: dict[str, str] | None = None, cwd: str | None = None):
        # 接続パラメータ設定

    async def __aenter__(self):
        # stdio接続確立 + セッション初期化

    async def __aexit__(self, ...):
        # 接続閉じる

    async def call_tool(self, name: str, arguments: dict) -> dict
        # 汎用ツール呼び出し（全29ツール対応）

    async def prompt(self, text: str, system_prompt: str | None = None) -> str
        # 自然言語プロンプト送信
        # Bashツール経由で 'claude -p "text"' を実行

    async def bash(self, command: str, description: str = "",
                   timeout: int = 120000) -> dict
        # Bashツールショートカット

    async def read(self, file_path: str) -> str
        # Readツールショートカット

    async def write(self, file_path: str, content: str) -> dict
        # Writeツールショートカット

    async def edit(self, file_path: str, old_string: str, new_string: str,
                   replace_all: bool = False) -> dict
        # Editツールショートカット

    async def list_tools(self) -> list[dict]
        # 利用可能なツール一覧

    @property
    def is_connected(self) -> bool
        # 接続状態の確認
```

### 2. `example_mcp_client.py` — 使用例

```python
async def main():
    async with ClaudeMCPClient() as client:
        # 接続確認
        print(f"Connected: {client.is_connected}")

        # ツール一覧
        tools = await client.list_tools()
        for t in tools:
            print(f"  - {t['name']}")

        # Bash実行
        result = await client.bash("ls -la /tmp")

        # ファイル操作
        await client.write("/tmp/hello.txt", "Hello MCP!")
        content = await client.read("/tmp/hello.txt")

        # 自然言語プロンプト
        answer = await client.prompt("What files are in /tmp?")
        print(answer)

        # 複数ツール呼び出し（セッション維持）
        await client.edit("/tmp/hello.txt", "Hello", "Goodbye")
```

## 実装のポイント

- `mcp.client.stdio.stdio_client` + `mcp.ClientSession` を使用
- `async with` コンテキストマネージャーで接続管理
- `claude mcp serve` を subprocessとして自動起動
- エラー時は `CallToolResult.isError` を確認
- 返り値は JSON文字列をパースした dict に統一

## 検証方法

1. `python -c "import mcp; print(mcp.__version__)"` でパッケージ確認
2. `example_mcp_client.py` を実行し、全メソッドが動作することを確認
3. 接続維持したまま複数ツールを連続呼び出しできることを確認
