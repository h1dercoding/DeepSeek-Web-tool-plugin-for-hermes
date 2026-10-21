# DeepSeek Web Tool for Hermes

Hermes 独立用户插件，将现有的 `web_search` 和 `web_extract` 工具接入 DeepSeek 官方 Search / Fetch API。使用 Hermes 已配置的 `DEEPSEEK_API_KEY`，与聊天模型的选择独立。

## 源码

- `provider.py`：Search / Fetch 请求、结果转换和原有搜索质量过滤。
- `__init__.py`：通过 `register_web_search_provider()` 注册后端。
- `plugin.yaml`：插件清单，插件名 `web-deepseek`，后端名 `deepseek`。
- `install.ps1`：备份、复制安装、启用插件并设置两个 Web 后端。

源码从本机已有的 1.1.0 用户插件整理而来。1.1.1 移除了对 Hermes 内部中断模块的依赖，中断由 Hermes 工具层处理，并移除了清单中的固定价格文字。

## 安装和更新

前提：默认需要先在 Hermes 中配置好 DeepSeek 模型 API Key（`DEEPSEEK_API_KEY`，通常保存在 `HERMES_HOME` 下的 `.env` 文件中）。本插件直接复用这个 Key，无需单独配置搜索密钥；当前聊天模型可以使用其他供应商。

在本目录运行：

```powershell
.\install.ps1
```

安装到当前 `HERMES_HOME` 的 `plugins\web\deepseek`；未设置该变量时，使用 Windows 的 `%LOCALAPPDATA%\hermes`。也可以显式指定：

```powershell
.\install.ps1 -HermesHome 'C:\Users\admin\AppData\Local\hermes'
```

脚本先备份原插件和 `config.yaml` 到 Hermes 的 `backups\deepseek-web-tool-时间戳`，然后使用官方 CLI 启用 `web-deepseek` 并设置：

```yaml
web:
  search_backend: deepseek
  extract_backend: deepseek
```

修改此目录中的源码后，重新运行安装脚本，再重启正在运行的 Hermes 会话或网关：

```powershell
hermes gateway restart
```

安装使用文件副本；Hermes 运行时不依赖本目录的盘符。API Key 从 Hermes 配置读取，源码中不保存密钥。

## 可选环境变量

沿用原插件的选项；均可不设置：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DEEPSEEK_SEARCH_BASE_URL` | `https://api.deepseek.com` | Search / Fetch API 根地址，不包含 `/v1` |
| `DEEPSEEK_SEARCH_MIN_AUTHORITY` | `0` | 搜索结果的最低权威度，未知权威度保留 |
| `DEEPSEEK_SEARCH_MIN_SCORE` | `0.6` | 搜索结果的最低相关性得分 |
| `DEEPSEEK_SEARCH_SUMMARY_CHARS` | `700` | 每条搜索摘要的最大字符数，`0` 表示不截断 |

搜索结果保留 `authority`、`rerank_score`、日期和站点名称。过滤后不足两条时，沿用原插件的行为，返回原始结果供模型判断。Fetch 每次处理一个 URL，多 URL 请求逐条执行。

HTTP 客户端使用 Hermes 运行环境已有的 `httpx`，无需额外安装依赖。

## 检查

```powershell
hermes plugins validate . --json
hermes plugins doctor web/deepseek --ci
hermes plugins list --plain --no-bundled
```

接口定义和计费以 [DeepSeek 官方文档](https://api-docs.deepseek.com/zh-cn/guides/search/) 为准。
