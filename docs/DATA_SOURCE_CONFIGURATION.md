# 数据源配置、认证与许可边界

本文说明美股与 A 股数据源的安装、路由、认证和许可边界。数据只用于投研分析，
本工程不提供券商接入或真实交易下单。

## 安装

新 SDK 均为可选依赖，未启用对应数据源时无需安装：

```bash
pip install ".[china-data]"   # AKShare + Tushare + BaoStock
pip install ".[pandaai]"      # panda_data
pip install ".[finnhub]"      # finnhub-python
pip install ".[market-data]"  # 上述全部 SDK
```

适配器采用延迟导入。路由选中未安装 SDK 的供应商时会产生
`VendorNotConfiguredError`，并且只在当前显式链内继续 fallback。

## 市场级路由

当前阶段策略：**新数据源只注册、默认不使用**。运行时继续走
`default_config.data_vendors` 的既有 TradingView-first 链。

```env
# 推荐保持 disabled，直到产品明确启用新源
TRADINGAGENTS_CN_DATA_VENDORS=disabled
TRADINGAGENTS_US_DATA_VENDORS=disabled

# 以后启用示例（顺序即优先级）
# TRADINGAGENTS_CN_DATA_VENDORS=pandaai,akshare,tushare,baostock
# TRADINGAGENTS_US_DATA_VENDORS=yfinance,alpha_vantage,finnhub
```

值是逗号分隔的完整优先级链。未设置、空值或 `disabled` 表示不启用市场链。
未知供应商、跨市场供应商、重复项，或把 `disabled` 与其他值混用，会在启动
加载配置时抛出 `ValueError`。

实际优先级为：

1. 非 `default` 的 `tool_vendors[method]`
2. 非 `default` 的 `data_vendors[category]`（当前默认已是显式 TradingView 链，
   因此即便以后写了市场链，也会被这里盖住，除非改成 `default`）
3. ticker 对应的 CN/US 环境链
4. `DEFAULT_VENDOR_CHAINS[method]`

市场链会按工具能力过滤。例如 PandaAI 不提供新闻能力，因此 CN 新闻链
`pandaai,akshare,tushare` 实际按 `akshare,tushare` 执行。过滤后不会追加链外供应商。
若最终链内供应商均失败，系统明确返回无数据或抛出既有供应商异常。

## ticker 格式

对外仍使用 provider-neutral ticker。A 股必须带交易所，例如：

- 上海：`600519.SS` 或 `SSE:600519`
- 深圳：`000001.SZ` 或 `SZSE:000001`
- 美股：`AAPL` 或 `NASDAQ:AAPL`

不带交易所的六位数字不会被静默猜测为 A 股。适配器内部才转换为 AKShare 的
`600519`、Tushare 的 `600519.SH` 或 BaoStock 的 `sh.600519`。

## 能力矩阵

| Vendor | 市场 | 已注册能力 |
| --- | --- | --- |
| PandaAI | A 股、美股 | 日线文本、结构化 OHLCV |
| AKShare | A 股 | 身份、日线、OHLCV、技术指标、基本面、三大报表、个股新闻 |
| Tushare | A 股 | 身份、日线、OHLCV、技术指标、基本面、三大报表、个股与市场新闻 |
| BaoStock | A 股 | 身份、日线、OHLCV、技术指标、摘要基本面 |
| yfinance | 美股等 | 保留现有能力 |
| Alpha Vantage | 美股 | 保留现有能力 |
| Finnhub | 美股 | 身份、基本面、个股/市场新闻、内部人交易 |

Finnhub 不注册历史 OHLCV；实时 quote 不会被伪装成历史 K 线。BaoStock 日线不描述为
实时行情。技术指标统一从对应供应商返回并完成日期过滤的 OHLCV 计算。

## 认证

TradingView Data API 在 Console 申请：https://www.tradingviewapi.com/

```env
TRADINGVIEW_API_KEY=
# 遗留 RapidAPI 变量名仍可作为 Console 凭据
# TRADINGVIEW_RAPIDAPI_KEY=
PANDAAI_USERNAME=
PANDAAI_PASSWORD=
PANDAAI_BASE_URL=       # 可选；留空时使用 SDK 默认服务地址
TUSHARE_TOKEN=
FINNHUB_API_KEY=
```

AKShare 无本工程级凭据。BaoStock 由 SDK 执行 `login()`，每次查询都保证
`logout()`。Tushare 和 Finnhub 分别需要 token/API key。

### PandaAI 专有接口

PandaAI 适配器通过 `panda_data.init_token(username=..., password=...,
base_url=...)` 认证；只有配置了 `PANDAAI_BASE_URL` 才传递 `base_url`。本次接入仅调用：

- A 股日线：`get_market_data(type="stock", fields=[])`
- 美股日线：`get_us_daily(fields=[])`

源工程还出现了港股和分钟数据接口，但不在本次已验证、已注册能力内。PandaAI 的身份、
新闻、基本面和实时报价也未注册，不会生成模拟结果补齐。

PandaAI 凭据只从进程环境读取，不进入 `default_config.py`、API 请求级配置、job 快照、
checkpoint、报告或持久化存储。认证错误转换为不含服务响应正文的通用异常；通用日志
脱敏器同时覆盖 username、password、authorization、API key、token 和 secret。

## 许可与数据权利

本仓库及本次新增 adapter 代码按本仓库 `LICENSE` 的 Apache License 2.0 发布。本次实现
参考了 `TradingAgents-CN` 的 Apache-2.0 `tradingagents/` provider 结构和公开调用契约，
没有移植其 `app/`、`frontend/`、MongoDB 配置、同步任务或 Web 管理代码；源工程把
`app/` 与 `frontend/` 标记为专有组件，商业使用需另行获得授权。

软件代码许可证不等于数据许可。`panda_data` SDK、PandaAI 服务及其返回数据的访问、
商业使用、缓存、展示和再分发权，均由 PandaAI 的 SDK 许可证、账号协议和服务条款决定。
AKShare、Tushare、BaoStock、Finnhub、Yahoo Finance、Alpha Vantage 及其上游数据也分别
受各自许可证和服务条款约束。部署方必须在启用前自行确认适用权利、频率限制和归属要求；
本工程只提供技术适配，不转授任何第三方数据权利。本文不是法律意见。

## 历史分析边界

行情按请求起止日期做闭区间过滤，财务数据和新闻按分析截止日过滤，防止把未来信息引入
历史分析。供应商空数据、字段变化、认证失败和限流不会用模拟数据兜底。真实连通性测试
应在显式安装 extras、提供测试账号并确认服务条款后单独执行；默认单元测试使用 fake SDK，
不访问外部服务。
