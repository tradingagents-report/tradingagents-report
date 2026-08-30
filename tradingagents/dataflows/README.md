# 数据源模块

`dataflows` 为投研图中的行情、基本面、新闻、宏观与情绪数据提供统一访问层。
它只获取和整理分析所需信息，不包含交易执行、券商接入或下单逻辑。

## 路由与使用方式

图和 Agent 应通过 [`interface.py`](./interface.py) 暴露的稳定工具接口取数，而不是直接依赖某个供应商目录。路由层根据 `default_config.py` 中的 `data_vendors` 与 `tool_vendors` 选择供应商：工具级配置优先于类别级配置；逗号分隔的显式值定义完整 fallback 链；未配置时使用 `DEFAULT_VENDOR_CHAINS`。

### Market-aware vendor chains

`TRADINGAGENTS_CN_DATA_VENDORS` and `TRADINGAGENTS_US_DATA_VENDORS` enable
ordered CN/US chains. Unset, empty, or `disabled` preserves the immutable
method defaults. Routing precedence is tool override, category override,
market chain, then method default. A selected market chain is intersected with
`VENDOR_METHODS[method]` and never falls through to an unlisted provider.

The CN adapters are PandaAI, AKShare, Tushare, and BaoStock. The US chain may
use PandaAI, TradingView, yfinance, Alpha Vantage, and Finnhub. SDK imports are
lazy, and no adapter fabricates missing data. Provider credentials remain in
environment variables and are not part of API request overrides.

See [data-source configuration, capability matrix, authentication, and licensing](../../docs/DATA_SOURCE_CONFIGURATION.md).

目前由路由层管理的能力包括：

| 数据类别 | 工具能力 | 默认供应商顺序 |
| --- | --- | --- |
| 标的身份 | `get_instrument_identity` | TradingView, yfinance |
| 行情 | `get_stock_data`, `get_ohlcv` | TradingView, yfinance, Alpha Vantage |
| 技术指标 | `get_indicators` | TradingView, yfinance, Alpha Vantage |
| 技术面仪表盘 | `get_ta_summary`, `get_ta_indicators` | TradingView（可选；不可用时降级） |
| 基本面与财务报表 | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | TradingView, yfinance, Alpha Vantage |
| 新闻与内部人交易 | `get_news`, `get_global_news`, `get_insider_transactions` | TradingView/yfinance/Alpha Vantage（按能力不同） |
| 事件日历 | `get_earnings_calendar`, `get_economic_calendar` | TradingView（可选；未来事件会隐藏 actual） |
| 同业对比 | `get_peer_comparison` | TradingView screener（可选） |
| 宏观数据 | `get_macro_indicators` | FRED |
| 预测市场 | `get_prediction_markets` | Polymarket |

宏观、预测市场、技术面仪表盘、事件日历和同业对比属于可选增强信息：供应商不可用时会返回可读的降级结果。行情、基本面及新闻是核心数据，路由失败会显式报错，避免在关键数据缺失时静默继续分析。

## 子目录数据源

### `alpha_vantage/`

Alpha Vantage 适配器，使用 `ALPHA_VANTAGE_API_KEY`。提供股票历史日线数据和带溯源信息的 OHLCV 数据、SMA/RSI/MACD 等技术指标、公司概览、资产负债表、现金流量表、利润表、个股与市场级新闻，以及内部人交易。其公共接口由 `__init__.py` 汇总，底层 `common.py` 统一处理认证、请求、限流和日期范围过滤。

### `tradingview/`

TradingView Data API 适配器，默认走 [Console](https://www.tradingviewapi.com/)（`TRADINGVIEW_API_KEY`，`Authorization: Bearer`）。遗留的 `TRADINGVIEW_RAPIDAPI_KEY` / `RAPIDAPI_KEY` 仍可作为 Console 凭据；`TRADINGVIEW_BACKEND=rapid` 才会改用 RapidAPI 主机。覆盖标的身份解析、股票及多资产 OHLCV、基于日线的技术指标、多周期 TA 仪表盘与指标快照、公司概览（含分析师共识/分红/财报日等扩展字段）与三大财务报表、个股和市场级新闻、财报/宏观事件日历、同业 screener 对比，以及社区 Ideas（供情绪分析 prefetch）。`symbols.py` 负责将通用标的转换为供应商符号，`client.py` 集中封装 API 客户端（支持 GET/POST，以及 list/object 两种 `data` 载荷）；`cache.py` 默认按 method+path+params+body 做进程内 memory TTL 缓存，并可叠加 Redis（`REDIS_URL`）；并发相同请求会合并；`TRADINGVIEW_CACHE_ENABLED=false` 可关闭。其余模块按行情、技术面、基本面、新闻、日历、ideas 和 peers 划分实现。

### `yfinance/`

yfinance 适配器，不需要本项目配置 API Key。`market.py` 提供 Yahoo Finance 标的身份、历史行情、OHLCV、基于 stockstats 的技术指标、公司基本面、三大财务报表和内部人交易；`news.py` 提供个股与市场新闻；`symbols.py` 负责符号规范化和安全校验，涵盖股票、加密资产等 Yahoo 符号形式。

### `fred/`

FRED（Federal Reserve Economic Data）宏观数据适配器，使用免费的 `FRED_API_KEY`。`get_macro_data()` 支持友好别名或原始 FRED series ID，获取政策利率、国债收益率、通胀、就业、增长、货币与市场、消费者信心和住房等时间序列。返回结果包含数据单位、频率、窗口内变化和近期观测值，并严格以传入日期作为上限，避免历史分析出现未来数据。

### `polymarket/`

Polymarket 预测市场适配器，使用公开 Gamma API，不需要认证。`get_prediction_markets()` 按主题检索仍处于开放状态且未到结算日的市场，按成交量排序，输出结果概率、成交量、结算日期和一周价格变化。该数据表示市场隐含概率，仅用于为新闻和宏观分析补充前瞻性背景，不应视为确定预测。

### `reddit/`

Reddit 讨论采集器，不需要 API Key。`fetch_reddit_posts()` 默认通过公开 Atom/RSS 搜索订阅 `wallstreetbets`、`stocks` 与 `investing` 等子版块中的标的讨论，并格式化为可供分析 Agent 使用的文本。模块支持配置开关、429 冷却和可选的单次重试；由于公开 JSON 搜索常受 WAF 限制，默认不依赖该路径。它是情绪信息的补充采集器，当前未注册到 `interface.py` 的供应商路由中。

### `stocktwits/`

StockTwits 公开消息流采集器，不需要 API Key。`fetch_stocktwits_messages()` 获取指定标的近期讨论，汇总用户标注的 Bullish、Bearish 与未标注情绪，并保留消息时间、作者和正文。模块会将加密货币交易对转换为 StockTwits 的 `<BASE>.X` 符号形式；网络或数据解析失败时返回占位文本，避免调用方需要单独处理异常。它同样是独立的情绪补充数据源，当前不在路由注册表中。

## 顶层共享模块

| 模块 | 职责 |
| --- | --- |
| `interface.py` | 供应商能力注册、配置优先级、显式 fallback 链及统一调用入口。 |
| `config.py` | 读取和更新运行时数据源配置。 |
| `provider_models.py` | 供应商无关的标的引用、供应商符号和带溯源的 `ProviderResult` 模型。 |
| `symbol_utils.py` | 标的、加密资产和文件名组件的规范化与安全处理。 |
| `market_data_validator.py` | 市场数据的质量与日期边界校验。 |
| `news_utils.py` | 新闻日期、内容和格式的共用处理。 |
| `structured_data.py` | 结构化数据的转换与输出辅助函数。 |
| `stockstats_utils.py` | 基于 OHLCV 数据生成技术指标的共用逻辑。 |
| `listings.py` | 交易所与上市标的相关的辅助数据。 |
| `exchange_catalog.py` | 读取包内 `data/exchanges.json`，将交易所映射为国家/地区、`asset_type` 与 TradingView `market_code`。 |
| `utils.py` | 各数据流复用的通用工具函数。 |
| `errors.py` | 未配置、限流、无市场数据和供应商不可用等统一异常类型。 |

## 开发约定

- 新增供应商能力时，同时更新 `VENDOR_METHODS` 和 `DEFAULT_VENDOR_CHAINS`，并在默认配置中显式声明可选供应商或 fallback 链。
- 直接调用供应商实现时仍应遵循其认证和日期参数要求；历史分析必须限制在请求的截止日期，避免 look-ahead bias。
- 不要让路由层静默访问未配置的供应商。核心数据失败应保留明确错误，只有已标记为可选的增强类别可以降级。
