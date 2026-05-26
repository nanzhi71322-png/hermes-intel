# Hermes 绩效日志

> 自动记录每次回测、优化和模拟盘运行的关键结果。

---

## 2026-05-24 — 阶段 P1：回测框架 MVP 启动

**动作**
- 创建 `backtest/` 模块（数据加载、指标、策略、引擎、绩效、走步、蒙特卡洛、优化器）
- 创建 `scripts/run_backtest.py` CLI
- 制定 10 阶段长期路线图

**策略**
- 市场结构策略（复刻 `intel/market_state.py` K 线逻辑）
- 入场：score ≥ 85 且 confirmation ≥ 3
- 出场：±1% TP/SL 或 5 bar TTL（对齐 paper_trading 300s）

**回测结果（BTC/USDT 1m × 3000 bars，约 2 天）**

| 指标 | 基线 | Optuna 最优 |
|------|------|-------------|
| 交易数 | 38 | 38 |
| 胜率 | 0.0% | 0.0% |
| 总收益 | -1.10% | -1.10% |
| 夏普 | -51.38 | -51.38 |
| 最大回撤 | 1.10% | 1.10% |

**结论**
- 纯市场结构策略（无 orderbook、无情绪信号）在当前参数下**不具备正期望**
- 所有交易均在 TTL（5 bar）退出，手续费+滑点导致 100% 亏损
- Optuna 15 次试验未能找到正收益参数组合

**根因分析**
1. 1m 周期 ±1% TP/SL 在 5 分钟内极难触发，几乎全部 TTL 退出
2. 回测缺少 orderbook 维度（live 系统有 bid/ask imbalance 过滤）
3. 缺少情绪/alpha 信号过滤（live 系统核心 alpha 来源）

**下一步（P2-P3）**
- 扩展数据至 5m/15m 周期对比
- 调整 TTL 与 TP/SL 比例（扩大 TTL 或缩小 TP）
- 引入 orderbook 历史代理或降低 min_confirmation
- 修复 feedback_engine 评估闭环
- 将情绪信号代理纳入回测（P5）

---

## 2026-05-24 — 阶段 P2/P3：多周期数据 + 参数优化

**动作**
- 下载 BTC/USDT 三周期 K 线缓存：`1m`(5000) / `5m`(2016) / `15m`(672)
- 新增 `scripts/run_multi_backtest.py`（多周期对比 + Optuna）
- 扩展 Optuna 搜索维度：加入 `position_ttl_bars` (3-30)

**多周期对比（基线参数，2026-05-26 重跑）**

| 周期 | K线数 | 交易数 | 胜率 | 收益 | 最大回撤 |
|------|-------|--------|------|------|----------|
| 1m | 5000 | 77 | 1.3% | -1.95% | 1.95% |
| 5m | 2016 | 15 | 6.7% | -0.48% | 0.48% |
| 15m | 672 | 5 | 0.0% | -0.20% | 0.22% |

**5m Optuna 最优参数（20 trials）**
- TP=2.13%, SL=2.72%, TTL=23 bars, min_score=78, min_confirmation=3
- 最优得分：-8.56（仍为负，但优于 1m 的 -41）

**结论**
- 数据已跑通，5m 周期表现优于 1m（回撤更小、胜率略高）
- 纯 K 线市场结构策略仍无正期望，Optuna 未能找到盈利参数
- 根因不变：缺少 orderbook + 情绪 alpha

**当前阶段**：P2 完成 | P3 进行中（策略逻辑需改进，非仅调参）

**下一步**：P4 修复 feedback_engine → P5 情绪信号代理回测

---

## 2026-05-26 — 阶段 P3/P4/P5：多策略对比 + 自动调参 + 运行状态检查

**动作**
- 新增 4 套策略：`market_structure` / `momentum_breakout` / `hybrid_alpha` / `mean_reversion`
- 新增 `scripts/run_strategy_compare.py`（同数据横向对比 + Top2 自动 Optuna 调参）
- 新增 `scripts/check_runtime_status.py`（本地数据/回测/远程 bot 状态）
- 修复 `feedback_engine`：决策价 fallback 到 market_price；评估延迟 60s 避免同价误判

**策略对比排名（BTC/USDT 5m × 2016 bars，刚拉最新数据）**

| 排名 | 策略 | 交易 | 胜率 | 收益 | 回撤 | 调参 |
|------|------|------|------|------|------|------|
| 1 | 市场结构 | 14 | 35.7% | **-0.02%** | 0.19% | 是 |
| 2 | 动量突破 | 56 | 21.4% | -1.34% | 1.34% | 是 |
| 3 | 混合(结构+动量) | 32 | 25.0% | -0.69% | 0.70% | 否 |
| 4 | 均值回归 | 17 | 23.5% | -0.41% | 0.49% | 否 |

**最优参数（market_structure 调参后）**
- TP=2.22%, SL=2.84%, TTL=30 bars, min_score=81, min_confirmation=2
- 已写入 `data/backtest/best_strategy.json`

**运行状态**
- 远程 `hermes-bot`：**active**（正在跑，日志 01:39 有 agent_loop 输出）
- TRADING_MODE=live, TRADING_TESTNET=true（testnet 模式）
- 本地无 paper_portfolio / feedback 文件（数据在服务器 `/opt/hermes`）

**结论**
- 调参后市场结构策略**接近盈亏平衡**（-0.02%），优于其他策略
- 下一步：将最优参数同步到 live 模拟盘，并加入情绪信号增强

**下一步**
- 同步 best_strategy 参数到 paper_trading / pipeline
- 服务器上拉 feedback 统计验证 live 表现
- 继续迭代 hybrid 策略（结构+动量+叙事权重）

---

## 2026-05-26 — 自动迭代引擎上线（并行多策略 + 进化筛选）

**动作**
- 新增 `backtest/parallel_runner.py` — 6-8 路并行回测，无需等 live 时间
- 新增 `backtest/evolve.py` — 优胜者参数变异，生成下一代候选
- 新增 `backtest/iterate.py` + `scripts/run_auto_iterate.py` — 多代循环筛选
- **已启动后台持续迭代**（每 15 分钟 5 代 × ~20 候选）

**工作流**
```
种子池(4策略×3周期+变异) → 并行回测 → 排名 → Top3变异 → 下一代 → 重复
                                              ↓
                              iterate_history.jsonl + best_strategy.json
```

**首轮 3 代结果（~50 秒，21→12 候选/代）**

| 代数 | 最优策略 | 收益 | 胜率 | 得分 |
|------|----------|------|------|------|
| 1 | hybrid_alpha | -0.15% | 38.5% | -9.13 |
| 2 | hybrid_alpha（变异） | **-0.12%** | 30.8% | **-6.44** |
| 3 | hybrid_alpha | -0.12% | 30.8% | -6.44 |

**结论**：并行迭代比等 live 快 100x+；混合策略（结构+动量）持续领先

**命令**
```bash
# 单次迭代
python scripts/run_auto_iterate.py --generations 5 --workers 8

# 持续自动迭代（已在后台运行）
python scripts/run_auto_iterate.py --continuous --sleep-minutes 15
```

---

## 模板（后续条目复制此格式）

```
## YYYY-MM-DD — 阶段 PX：标题

**动作**: ...
**策略/参数**: ...
**回测结果**: 交易数 / 胜率 / 收益 / 夏普 / 最大回撤
**模拟盘结果**: balance / 7日PnL
**结论**: ...
**下一步**: ...
```

---

## 2026-05-27 — 迭代评分与 gate 对齐

**动作**: `iteration_score` 与晋级门槛绑定；`sentiment_hybrid` 增加 soft 模式；新增 `run_gate_optimize.py`；修复 `is_better_candidate` 新旧评分不可比问题。

**回测结果**（当前 `best_strategy.json`）: 14 笔 / 胜率 42.9% / 收益 -0.055% / 夏普 -1.33 — **未过 gate**

**下一步**: 后台 Optuna + 多代并行迭代直至 `gate.py` 全部通过，再进入 P9 七天模拟盘验证。
