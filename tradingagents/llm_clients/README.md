# LLM clients

`llm_clients` creates LangChain chat models for the research graph and confines
vendor differences (auth, endpoints, model capabilities, response shape) to an
adapter layer. It does not contain agent prompts or business decisions. Callers
get a model from the factory and inject it into graph role nodes.

There are no subpackages today. Layout is vendor adapters plus shared support
modules.

## Creation path

Public entry: `create_llm_client(provider, model, base_url=None, **kwargs)`

1. `factory.py` identifies native API vendors such as Anthropic, Google, Azure,
   and Bedrock.
2. Remaining registered OpenAI-compatible providers go through `OpenAIClient`.
3. `get_llm()` returns the configured LangChain chat model. `validate_model()`
   checks or warns on known model names.
4. Adapters normalize chunked response content to a string so agents can read
   `response.content` consistently.

Unsupported providers raise `ValueError`. There is no silent fallback to an
unconfigured endpoint.

## Vendor adapters

| Module | Role |
| --- | --- |
| `anthropic_client.py` | Claude `ChatAnthropic`; passes extended-thinking `effort` only on supported models |
| `google_client.py` | Gemini `ChatGoogleGenerativeAI`; unified API-key args and thinking-level compatibility |
| `azure_client.py` | Azure OpenAI deployment client; Azure deployment name and env config |
| `bedrock_client.py` | Amazon Bedrock Converse API; optional `langchain-aws`, AWS credential chain or Bedrock bearer token |
| `openai_client.py` | OpenAI-compatible APIs: OpenAI, xAI, DeepSeek, Qwen, GLM, MiniMax, OpenRouter, Ollama, Mistral, Kimi, Groq, NVIDIA, and generic endpoints |

`OPENAI_COMPATIBLE_PROVIDERS` in `openai_client.py` is the compatibility
registry: default base URL, env overrides, whether a key is required,
placeholder keys, endpoint requirements, and Chat class. Extra request shaping
for DeepSeek, MiniMax, and similar models also lives here.

## Shared modules

| Module | Role |
| --- | --- |
| `__init__.py` | Exports `BaseLLMClient` and `create_llm_client` |
| `base_client.py` | Abstract client, model-validation warnings, response-content normalization |
| `factory.py` | Builds the matching client; lazy-imports vendor SDKs |
| `api_key_env.py` | Provider → API-key env mapping for CLI and clients |
| `capabilities.py` | Declarative tool-call, JSON, and reasoning-parameter support |
| `model_catalog.py` | Known and optional model lists for config UI and validation |
| `validators.py` | Catalog-based model-name checks; local runtimes, generic endpoints, and aggregators allow any name |
| `token_usage.py` | LangChain callback for input, output, reasoning, cache, and tool-call usage |
| `pricing.py` | Pricing fetch/parse and USD cost by model, with built-in fallback prices |

## Auth and config boundaries

- Keep API-key env names in `api_key_env.py`. Do not hard-code keys in agents
  or business modules.
- Bedrock uses the AWS credential chain or `AWS_BEARER_TOKEN_BEDROCK`, not a
  single API key. Optional deps install via `tradingagents[bedrock]`.
- Local runtimes such as Ollama and generic OpenAI-compatible endpoints can run
  without a key. Generic endpoints still need an explicit base URL.
- `base_url` and client kwargs come from the caller or config layer. New
  vendors must declare boundaries in the registry, key map, catalog, and
  validators together.

## Conventions

- Prefer `BaseLLMClient` and the `OpenAIClient` registry. Add a native client
  only when the API protocol is actually different.
- Model-specific parameter limits belong in `capabilities.py` or a local
  adapter, not in agent business code.
- Keep the `response.content` string contract. Do not leak vendor reasoning or
  tool metadata into downstream prompts.
- Pricing fetch failure must not block analysis. Cost totals should keep a
  traceable price source and unmatched-model state.
