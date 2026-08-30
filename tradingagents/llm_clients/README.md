# LLM 客户端模块

`llm_clients` 为投研图统一创建 LangChain 聊天模型，并将不同供应商的认证、端点、模型能力和响应格式差异收敛在适配层。它不包含 Agent prompt 或业务决策逻辑；调用方通过工厂获得模型实例后再将其注入图中的角色节点。

该目录当前没有子目录，功能按供应商适配器和共享支持模块组织。

## 创建路径

公共入口是 `create_llm_client(provider, model, base_url=None, **kwargs)`：

1. `factory.py` 先识别 Anthropic、Google、Azure 和 Bedrock 等原生 API 提供商。
2. 其余已注册的 OpenAI 兼容提供商统一交由 `OpenAIClient` 创建。
3. 客户端的 `get_llm()` 返回已配置的 LangChain chat model；`validate_model()` 对已知模型执行校验或发出警告。
4. 所有适配器会将块状响应内容规范为字符串，使下游 Agent 可一致读取 `response.content`。

不支持的供应商会由工厂显式抛出 `ValueError`，避免静默回退到未配置的端点。

## 供应商适配器

| 模块 | 功能 |
| --- | --- |
| `anthropic_client.py` | 创建 Claude 的 `ChatAnthropic` 客户端；仅向支持的模型传递 extended-thinking `effort` 参数。 |
| `google_client.py` | 创建 Gemini 的 `ChatGoogleGenerativeAI` 客户端；处理统一 API Key 参数和 Gemini thinking level 兼容性。 |
| `azure_client.py` | 创建 Azure OpenAI 部署客户端；读取 Azure 部署名并支持 Azure OpenAI 的环境配置。 |
| `bedrock_client.py` | 通过 Amazon Bedrock Converse API 创建客户端；按需加载可选 `langchain-aws` 依赖，并使用 AWS 凭证链或 Bedrock bearer token。 |
| `openai_client.py` | OpenAI 兼容 API 的统一实现，覆盖 OpenAI、xAI、DeepSeek、Qwen、GLM、MiniMax、OpenRouter、Ollama、Mistral、Kimi、Groq、NVIDIA 和通用兼容端点。 |

`openai_client.py` 中的 `OPENAI_COMPATIBLE_PROVIDERS` 是兼容提供商的注册表，集中声明默认 base URL、环境变量覆盖、是否允许无 Key、占位 Key、端点要求及特定 Chat 类。DeepSeek 和 MiniMax 等需要额外请求格式处理的模型也在此层适配。

## 共享支持模块

| 模块 | 职责 |
| --- | --- |
| `__init__.py` | 对外导出 `BaseLLMClient` 与 `create_llm_client`。 |
| `base_client.py` | 定义客户端抽象基类、模型校验警告，以及跨供应商的响应内容规范化。 |
| `factory.py` | 根据 `provider` 创建对应客户端，并延迟导入供应商 SDK。 |
| `api_key_env.py` | 维护提供商到 API Key 环境变量的唯一映射，供 CLI 和客户端使用。 |
| `capabilities.py` | 以声明式模型能力表描述工具调用、JSON 输出和 reasoning 参数兼容性。 |
| `model_catalog.py` | 维护已知模型与可选模型列表，供配置界面和校验使用。 |
| `validators.py` | 基于模型目录校验模型名；本地运行时、通用端点和多模型聚合服务允许任意模型名。 |
| `token_usage.py` | LangChain callback，统一采集输入、输出、推理、缓存和工具调用用量，并按模型汇总。 |
| `pricing.py` | 拉取并解析模型定价数据，计算按模型与总计的 USD 成本，并带有内置回退价格。 |

## 认证与配置边界

- API Key 环境变量应通过 `api_key_env.py` 的映射维护，不应在 Agent 或业务模块中硬编码。
- Bedrock 使用 AWS 凭证链或 `AWS_BEARER_TOKEN_BEDROCK`，不是单一 API Key；其可选依赖需通过 `tradingagents[bedrock]` 安装。
- Ollama 等本地运行时和通用 OpenAI 兼容端点可以无 Key 运行；通用端点仍需要显式提供 base URL。
- `base_url` 和客户端 kwargs 由调用方或配置层传入。新增供应商时应在注册表、Key 映射、模型目录和校验规则中同步声明其边界。

## 开发约定

- 新供应商优先复用 `BaseLLMClient` 与 `OpenAIClient` 注册表；仅在 API 协议确实不同的情况下新增原生客户端。
- 模型专属的参数限制应加入 `capabilities.py` 或客户端局部适配，避免将判断散落到 Agent 业务代码。
- 保持 `response.content` 的字符串契约，避免将供应商的 reasoning 或工具元数据直接泄漏给下游 prompt。
- 价格抓取失败不应阻断分析运行；成本计算应保留可追溯的定价来源与未匹配模型状态。
