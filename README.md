# Claude MCP Python Client

`claude mcp serve`（stdioベースのMCPサーバー）をPythonから操作するための非同期クライアントライブラリです。Claude Codeが公開するツール（Bash, Read, Write, Edit, WebSearch など29個）を、Pythonプログラムから呼び出すことができます。

## 目次

- [特徴](#特徴)
- [アーキテクチャ](#アーキテクチャ)
- [インストール](#インストール)
- [使い方](#使い方)
  - [基本](#基本)
  - [ツール一覧](#ツール一覧)
  - [ファイル操作](#ファイル操作)
  - [シェルスクリプト実行](#シェルスクリプト実行)
  - [自然言語プロンプト](#自然言語プロンプト)
  - [汎用ツール呼び出し](#汎用ツール呼び出し)
- [APIリファレンス](#apiリファレンス)
  - [ClaudeMCPClient](#claude-mcpclient)
  - [メソッド](#メソッド)
  - [プロパティ](#プロパティ)
  - [例外](#例外)
- [利用可能なツール](#利用可能なツール)
- [要件](#要件)
- [プロジェクト構成](#プロジェクト構成)

## 特徴

- **セッション維持** — 再接続不要。`async with` で開いたセッション内で複数回のツール呼び出しが可能
- **非同期API** — `asyncio` ベースで、他の非同期コードとシームレスに統合
- **ショートカットメソッド** — 頻出ツール（Bash, Read, Write, Edit）を簡潔なメソッドで呼び出し可能
- **統一された返り値** — 全ツールの結果を JSON-serializable な dict にパースして返す

## アーキテクチャ

```
Pythonスクリプト (ClaudeMCPClient)
    ↓ asyncio + stdio
claude mcp serve (MCPサーバー)
    ↓
Claude Code (セッション維持中)
```

`ClaudeMCPClient` は `claude mcp serve` を subprocess として起動し、stdio経由で双方向通信します。

## インストール

前提として、以下のパッケージがインストールされている必要があります：

```bash
# Python 3.12 以上
python --version

# mcpパッケージ（v1.28.1 以上）
pip install mcp
```

## 使い方

### 基本

```python
import asyncio
from claude_mcp_client import ClaudeMCPClient

async def main():
    async with ClaudeMCPClient() as client:
        print(f"Connected: {client.is_connected}")

asyncio.run(main())
```

### 環境変数の継承

デフォルトでは親プロセスの環境変数（`os.environ`）をすべて継承します。

```python
# デフォルト: 親の環境変数をすべて継承
async with ClaudeMCPClient() as client:
    ...

# 環境変数を一部上書き
async with ClaudeMCPClient(env={"MY_VAR": "value"}):
    ...

# 環境変数を継承しない（最小限のデフォルト環境のみ）
async with ClaudeMCPClient(inherit_env=False):
    ...
```

### ツール一覧

利用可能なツールを一覧取得します：

```python
async with ClaudeMCPClient() as client:
    tools = await client.list_tools()
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")
```

### ファイル操作

Read, Write, Edit の各ショートカットメソッドを提供します：

```python
async with ClaudeMCPClient() as client:
    # ファイルに書き込み
    await client.write("/tmp/hello.txt", "Hello MCP!")

    # ファイルから読み込み（文字列が返る）
    content = await client.read("/tmp/hello.txt")
    print(content)  # Hello MCP!

    # ファイルを編集
    await client.edit("/tmp/hello.txt", "Hello", "Goodbye")

    # 編集後の確認
    content = await client.read("/tmp/hello.txt")
    print(content)  # Goodbye MCP!
```

### シェルスクリプト実行

Bash ツールのショートカットメソッドを提供します：

```python
async with ClaudeMCPClient() as client:
    result = await client.bash("ls -la /tmp")
    print(result.get("content", ""))
```

### 自然言語プロンプト

Claude Code に自然言語で質問し、回答を取得します：

```python
async with ClaudeMCPClient() as client:
    answer = await client.prompt("What files are in /tmp?")
    print(answer)
```

### 汎用ツール呼び出し

すべてのツールを `call_tool` で呼び出せます：

```python
async with ClaudeMCPClient() as client:
    # WebSearch ツールの呼び出し
    result = await client.call_tool("WebSearch", {"query": "Python 3.12 release date"})
    print(result.get("content", ""))

    # TaskCreate ツールの呼び出し
    result = await client.call_tool("TaskCreate", {
        "subject": "My Task",
        "description": "Task description"
    })
    print(result)
```

## APIリファレンス

### ClaudeMCPClient

```python
class ClaudeMCPClient:
    """claude mcp serve への非同期クライアント"""

    def __init__(
        self,
        command: str = "claude",
        mcp_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        inherit_env: bool = True,
    ):
        """接続パラメータを初期化。

        Args:
            command: MCPサーバー起動コマンド（デフォルト: "claude"）
            mcp_args: `claude mcp serve` への追加引数
            env: サブプロセスに渡す環境変数
            cwd: サブプロセスの作業ディレクトリ
            inherit_env: 親プロセスの環境変数を継承するかどうか
                （デフォルト: True。Falseの場合、最小限のデフォルト環境のみ）
        """
```

### メソッド

#### `call_tool(name: str, arguments: dict | None) -> dict`

ツールを呼び出す。全29ツールに対応。

```python
result = await client.call_tool("Bash", {"command": "echo hello"})
```

**返り値:** `dict` — `isError`, `content` キーを含む

**例外:**
- `ToolError` — ツールがエラーを返した場合
- `ConnectionError` — 接続していない場合

#### `prompt(text: str, system_prompt: str | None = None) -> str`

自然言語プロンプトを送信。Bashツール経由で `claude -p "text"` を実行。

```python
answer = await client.prompt("Explain how async/await works in Python")
```

**返り値:** `str` — Claudeの回答

#### `bash(command: str, description: str = "", timeout: int = 120000) -> dict`

Bashツールショートカット。

```python
result = await client.bash("ls -la /tmp", description="List /tmp contents")
```

#### `read(file_path: str) -> str`

Readツールショートカット。

```python
content = await client.read("/path/to/file.py")
```

**返り値:** `str` — ファイル内容

#### `write(file_path: str, content: str) -> dict`

Writeツールショートカット。

```python
result = await client.write("/tmp/output.txt", "Hello World")
```

#### `edit(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict`

Editツールショートカット。

```python
result = await client.edit("main.py", "old code", "new code")
```

#### `list_tools() -> list[dict]`

利用可能なツール一覧を取得。

```python
tools = await client.list_tools()
# [{"name": "Bash", "description": "...", "inputSchema": {...}}, ...]
```

### プロパティ

#### `is_connected: bool`

接続状態を確認。

```python
if client.is_connected:
    print("Connected!")
```

### 例外

| 例外 | 説明 |
|------|------|
| `ClaudeMCPError` | ベース例外 |
| `ConnectionError` | 接続失敗時 |
| `ToolError` | ツール呼び出しエラー時 |

## 利用可能なツール

`claude mcp serve` は以下の29ツールを公開します：

| カテゴリ | ツール |
|---------|--------|
| コード実行 | Agent, Bash, TaskOutput, TaskStop, Workflow |
| ファイル操作 | Read, Write, Edit, NotebookEdit |
| 検索 | WebSearch, WebFetch, ToolSearch |
| タスク管理 | TaskCreate, TaskGet, TaskUpdate, TaskList |
| セッション | EnterWorktree, ExitWorktree, SendMessage, ListAgents |
| スケジューリング | CronCreate, CronDelete, CronList, ScheduleWakeup |
| その他 | Skill, ReportFindings, DesignSync, Monitor, PushNotification |

## 要件

| 項目 | バージョン |
|------|-----------|
| Python | 3.12 以上 |
| mcp | 1.28.1 以上 |
| claude | CLIツールがインストールされていること |

## プロジェクト構成

```
.
├── claude_mcp_client.py    # メインクライアント
├── example_mcp_client.py   # 使用例
└── README.md               # このファイル
```

### ファイル説明

| ファイル | 説明 |
|---------|------|
| `claude_mcp_client.py` | `ClaudeMCPClient` クラス — メインの実装 |
| `example_mcp_client.py` | 全メソッドの使用例 |

## 実行方法

```bash
python example_mcp_client.py
```
