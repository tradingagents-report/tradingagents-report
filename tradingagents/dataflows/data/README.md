# Package data for dataflows

- `exchanges.json` — local exchange catalog used by `exchange_catalog.py`
  (copied into this package at build time). Each row has `asset_type` for the
  primary TradingView source class: `stock`, `futures`, `index`, `options`,
  `bond`, `crypto`, `forex`, or `economy`. `group` remains the geographic /
  crypto / forex / economy bucket.
