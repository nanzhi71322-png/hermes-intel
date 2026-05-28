# tg-bot 暂停快照

## Gate（未通过）

- 收益 > 0% ❌ (-0.055%)
- 胜率 ≥ 45% ❌ (42.9%)
- 夏普 ≥ 0.3 ❌ (-1.33)
- 交易数 ≥ 10 ✅ (14)

## 数据文件（本地，多数在 .gitignore）

- `data/backtest/best_strategy.json`
- `data/backtest/status_snapshot.json`
- `data/backtest/deep_scan_history.jsonl`
- `data/backtest/BTC-USDT_5m.csv` (~4896 bars)

## 已推送脚本（hermes-intel main）

- `run_gate_optimize.py` — gate 对齐 Optuna
- `run_deep_scan_loop.py` — 每 2h 深度扫描
- `write_status_snapshot.py` — 状态快照
- `run_autonomous_cycle.py` — 达标晋级循环

## 环境变量清单

见仓库根目录 `.env.example` 与 `.env.deploy.example`。

本地填写后勿提交；从服务器拉回见：

```powershell
python scripts/pull_remote_env_to_local.py
```
