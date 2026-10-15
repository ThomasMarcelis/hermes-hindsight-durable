# Durable Hindsight memory for Hermes

Retain conversation exchanges and explicitly saved facts in Hindsight, then recall
or reflect on them across sessions. This independently maintained integration keeps
session-owned delivery queues, bounded settlement and retry, observation-scope
filtering, and optional automatic-only retention.

## Supported host

Requires Hermes **memory lifecycle API 1** in addition to the manifest's 0.22.2
version floor. Vanilla v0.22.2 lacks that contract: this provider refuses availability
and initialization there. The paired host supplies FIFO session-switch fencing,
bounded drain, and final-assistant identities for CLI/TUI rewind with or without
SQLite. The exact reviewed host revision is recorded in `HOST-COMPATIBILITY.md`
alongside this guide. Pin that host; a release number alone is insufficient.

The tested mode is `plugins.isolation: in_process`. Dedicated plugin-host process
isolation is not certified. Native validation reports inherited private host imports;
re-run compatibility tests before upgrading Hermes. This is a separate lineage from
the Vectorize catalog provider, despite sharing the name `hindsight`.

## Install and setup, per profile

Use the paired host and a reviewed full 40-character plugin commit. For example,
with a local Git checkout at `/opt/hermes-hindsight-durable`:

```bash
hermes -p example plugins install 'file:///opt/hermes-hindsight-durable#hindsight' --ref <40-character-plugin-commit> --yes-deps --enable
hermes -p example memory setup hindsight
```

Repeat for each profile. The native installer records the exact revision and installs
only the `hindsight` subdirectory under that profile's `$HERMES_HOME/plugins/hindsight`.
PM provisions **hindsight-client==0.6.1**. Restart if dependency setup requests it.
The wizard does not install packages itself. Do not use the bare catalog command
`hermes plugins install hindsight` to obtain this variant.

Choose cloud, `local_external` for a separately managed server, or `local_embedded`.
For manual setup, first install and prepare dependencies as above, then create
`$HERMES_HOME/hindsight/config.json`, configure the profile's credentials through
Hermes secret configuration, and select `memory.provider: hindsight` in
`$HERMES_HOME/config.yaml`. Example provider configuration, with no credentials:

```json
{
  "mode": "local_external",
  "api_url": "http://localhost:8888",
  "bank_id_template": "hermes-{profile}",
  "expose_retain_tool": false
}
```

No bank migration or rewrite is required. Existing settings and server data remain
in place. The paired host declines automatic replacement with the catalog lineage.
If replacing another implementation, review its configuration before installing;
this integration does not convert server data.

## Configuration and data flow

The first nonempty valid configuration object wins: `$HERMES_HOME/hindsight/config.json`,
then shared legacy `$HOME/.hindsight/config.json`. Files are not merged. With neither
file, environment fallbacks populate mode, bank and budget. An existing shared legacy
file can therefore select the same bank and credentials for multiple Hermes profiles.
Create a profile-local file and distinct bank selection when isolation is intended.
`memory.hindsight` in the host configuration is not read.

| Connection key | Default | Meaning |
|---|---|---|
| `mode` | `cloud` | `cloud`, `local_external`, or `local_embedded` |
| `api_url` | Cloud API, or `http://localhost:8888` locally | Config value, then scoped `HINDSIGHT_API_URL`, then mode default |
| `bank_id` | `hermes` | Static fallback bank |
| `bank_id_template` | unset | Placeholders `{profile}`, `{workspace}`, `{platform}`, `{user}`, `{session}`; empty segments collapse |
| `timeout` | `120` | Client request timeout in seconds |
| `prefetch_waits_for_retain` | `true` | Await bounded retain settlement before background recall |
| `prefetch_retain_drain_timeout` | `10` | Settlement budget in seconds; also bounds rewind repair and default drain |

`bank_mission` and `bank_retain_mission` were never applied by this implementation;
they are not supported settings. Configure bank missions on the server. Selecting a
starter bank template in the wizard can fetch public templates and write the selected
template to the configured bank.

### Recall

| Key | Default | Description |
|-----|---------|-------------|
| `recall_budget` | `mid` | Recall thoroughness: `low` / `mid` / `high` |
| `recall_prefetch_method` | `recall` | Auto-recall method: `recall` (raw facts) or `reflect` (LLM synthesis) |
| `recall_max_tokens` | `4096` | Maximum tokens for recall results |
| `recall_max_input_chars` | `800` | Maximum input query length for auto-recall |
| `recall_prompt_preamble` | — | Custom preamble for recalled memories in context |
| `recall_tags` | — | Tags to filter when searching memories |
| `recall_tags_match` | `any` | Tag matching mode: `any` / `all` / `any_strict` / `all_strict` |
| `recall_types` | `observation` | Fact types surfaced by recall (both auto-recall and the `hindsight_recall` tool). Comma-separated string or JSON list. Default is `observation` only. Set to `observation,world,experience` to also include raw facts. |
| `auto_recall` | `true` | Automatically recall memories before each turn |
| `recall_sync` | `false` | Recall synchronously against the *current* message each turn (higher relevance, adds recall latency). Default off: recall runs in the background and is injected on the next turn. |
| `recall_indicator` | `true` | Show a `👁️ Hindsight — recalled N memories` status line when auto-recall injects memory. Turn off for customer-facing agents. |

Recall defaults to consolidated `observation` facts. Set `recall_types` to
`observation,world,experience` to include raw facts in both automatic and tool recall.

### Retain

| Key | Default | Description |
|-----|---------|-------------|
| `auto_retain` | `true` | Automatically retain conversation turns |
| `retain_async` | `true` | Process retain asynchronously on the Hindsight server |
| `retain_every_n_turns` | `1` | Retain every N turns (1 = every turn) |
| `retain_context` | `conversation between Hermes Agent and the User` | Context label for retained memories |
| `retain_tags` | — | Default tags applied to retained memories; merged with per-call tool tags |
| `observation_scopes` | — | Explicit Hindsight observation scopes (`combined`, `per_tag`, `all_combinations`, or JSON tag lists). Explicit scopes take precedence over derived filtering. |
| `observation_scope_exclude_tag_prefixes` | — | Comma-separated or JSON-list volatile tag prefixes excluded when deriving an observation scope from merged retain and lineage tags. For example, `session:,parent:` keeps those lineage tags on facts while preventing per-session observation fragmentation. If every tag is excluded, Hermes sends an explicit empty scope. |
| `retain_source` | — | Opt-in `metadata.source` attached to retained memories (identifies the storing client, e.g. `hermes`). Empty by default — no attribution tag ships unless you set it. |
| `retain_indicator` | `true` | Show a `👁️ Hindsight — saving to memory…` status line when a turn is saved. Turn off for customer-facing agents. |
| `retain_user_prefix` | `User` | Label used before user turns in auto-retained transcripts |
| `retain_assistant_prefix` | `Assistant` | Label used before assistant turns in auto-retained transcripts |

### Integration

| Key | Default | Description |
|-----|---------|-------------|
| `memory_mode` | `hybrid` | How memories are integrated into the agent |
| `expose_retain_tool` | `true` | Expose `hindsight_retain` to the model. Set `false` to keep automatic retention active while hiding the schema, prompt mention, and direct handler. |

**memory_mode:**
- `hybrid` — automatic context injection + tools available to the LLM
- `context` — automatic injection only, no tools exposed
- `tools` — tools only, no automatic injection

### Local Embedded LLM

| Key | Default | Description |
|-----|---------|-------------|
| `llm_provider` | `openai` | `openai`, `anthropic`, `gemini`, `groq`, `openrouter`, `minimax`, `ollama`, `lmstudio`, `openai_compatible` |
| `llm_model` | per-provider | Model name (e.g. `gpt-4o-mini`, `qwen/qwen3.5-9b`) |
| `llm_base_url` | — | Endpoint URL for `openai_compatible` (e.g. `http://192.168.1.10:8080/v1`) |

The LLM API key is stored in `$HERMES_HOME/.env` as `HINDSIGHT_LLM_API_KEY`.

The embedded daemon is a subprocess that cannot see the per-turn secret
scope, so it reads the key from `$HOME/.hindsight/profiles/<profile>.env`
(materialized owner-only at setup and on config change). Key resolution
order is explicit config → secret scope → the on-disk profile env, and the
rewrite path is fail-closed: a build with no key never clobbers a profile
file that already holds one.

## Tools

Available in `hybrid` and `tools` memory modes:

| Tool | Description |
|------|-------------|
| `hindsight_retain` | Store information with auto entity extraction; supports optional per-call `tags` |
| `hindsight_recall` | Multi-strategy search (semantic + entity graph) |
| `hindsight_reflect` | Cross-memory synthesis (LLM-powered) |


## Credential and environment fallbacks

Credentials resolve through Hermes's owning-profile secret scope. Explicit legacy
`api_key` configuration precedes `HINDSIGHT_API_KEY`. Prefer scoped secrets over
credentials in the provider JSON. `HINDSIGHT_MODE`, `HINDSIGHT_BANK_ID`, and
`HINDSIGHT_BUDGET` are fallbacks only when no configuration file is loaded.
`HINDSIGHT_API_URL` supplies an unset URL. `HINDSIGHT_RECALL_TAGS` applies only
when `recall_tags` is absent; an explicit empty value suppresses it. Equivalent
retain shaping fallbacks include `HINDSIGHT_RETAIN_TAGS`, `HINDSIGHT_RETAIN_SOURCE`,
`HINDSIGHT_RETAIN_OBSERVATION_SCOPES`, and
`HINDSIGHT_RETAIN_OBSERVATION_SCOPE_EXCLUDE_TAG_PREFIXES`.

### Embedded mode

The runtime must already contain compatible `hindsight-all`, `hindsight-embed`,
`hindsight-client`, and `sentence-transformers`. Readiness checks imports and a callable
`hindsight.HindsightEmbedded` before saving embedded setup; it does not download a
server or upgrade client/embedding packages. The server dependency graph may conflict
with the host: prefer a separately managed `local_external` server if it is not
provisioned. Running as root or without the embedded stack disables this provider,
including tools, recall, automatic retention and client creation.

The embedded `profile` setting defaults to `hermes` and is **independent of the Hermes
profile name**. Distinct Hermes profiles using that default share an embedded daemon
and its `$HOME/.hindsight/profiles/hermes.env` credentials. Set distinct embedded
`profile` values as well as banks to isolate them. Startup can materialize its
owner-only profile environment and restart its daemon when configuration changes.
An absent key never overwrites an existing embedded profile key.

Startup log: `$HERMES_HOME/logs/hindsight-embed.log`. Daemon log:
`$HOME/.hindsight/profiles/<embedded-profile>.log`. Embedded UI:
`hindsight-embed -p <embedded-profile> ui start`.

## Retention and rewind limits

Automatic retention sends user and final assistant text to the configured endpoint.
Local `message_uid` bookkeeping is stripped from remote content. Explicit retain
sends the supplied text. Built-in Hermes memory writes are not mirrored.

On Hindsight API ≥0.5.0 with source-text storage enabled, the session document may contain older provider lifetimes'
memories. This plugin **never replaces or deletes that shared document on rewind**.
CLI/TUI undo and retry cancel undispatched removed turns using message identities;
already dispatched turns remain retained, including a removed answer. A subsequent
retry may retain both versions. This conservative refusal protects earlier source
content and extracted memories across restarts and A→B→A revisits.

Unique per-lifetime documents on servers without append support can be repaired only
when the local ledger and acknowledged request outcomes establish ownership. An
unacknowledged request instead retains its original settlement ledger and future
writes use a fresh document. `store_document_text=false` selects these unique
documents; the plugin never enables server source-text storage.

Messaging-gateway `/undo` and `/retry` do not notify memory before eviction in the
paired host. They do not revoke retained memory. This inherited gap is not fixed by
installing the plugin; CLI/TUI rewind guarantees must not be assumed for the gateway.

Delivery state is in memory, not a disk outbox. Shutdown drains within a deadline,
reports unresolved work, and releases settled buffers. Unresolved local work is lost
on process exit. A timeout cancels the local coroutine where possible but cannot
retract a request already accepted remotely; retries can duplicate appends. There is
no exact-once guarantee. Foreground tools and recall wait behind a queued session
switch, failing closed if the new owner is not ready.

## Troubleshooting

- Unavailable host: install the pinned host with memory lifecycle API 1; do not bypass
  the capability check.
- Missing client: run native memory setup or `hermes pm repair`, then restart when asked.
- Missing embedded stack: provision it separately or select `local_external`.
- Unexpected shared memories: check both the legacy fallback file and bank/embedded
  profile selection. Changing profiles does not migrate existing bank contents.
- Rewind refusal or shutdown deadline: retained data is preserved. Check server
  operation status; do not repeatedly retry expecting an idempotent remote undo.

See the repository's test launcher for offline development. License and attribution
are included in `LICENSE` and `NOTICE`; this project is not endorsed by Nous Research
or Vectorize.
