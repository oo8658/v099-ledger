# v099-ledger

**纯记账与独立复核工具。** 输入已经指定的成交、标记价、资金费率；输出现金、持仓、费用和盈亏。程序不决定何时买卖、买卖多少或何时退出。

Policy-free linear perpetual accounting for supplied fills, with an independent verifier. Runtime uses the Python standard library only.

当前版本：0.2.0。单标的、报价币结算、基础币数量、多头或空头、一次一个净持仓。支持完整开仓/平仓；末端可以保留持仓。没有策略、信号、仓位分配、止损、参数搜索、交易所客户端、账户或下单接口。

## 安装和演示

需要 Python 3.11 或更新版本。在本目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
v099-ledger demo --output ./demo-report
v099-ledger verify ./demo-report
```

Windows 命令提示符的激活命令为 `.venv\Scripts\activate`。也可以用 `python -m v099_ledger` 替代命令。安装后运行不需要网络或第三方运行依赖。已有输出目录会被拒绝覆盖。

演示是 6 个人工标记价点和 4 笔人工指定成交，共 2 笔完整交易。数量和时点是写在示例中的算术输入，不根据价格变化产生，没有盈利有效性含义。`SYNTH` 标签、毫秒时点和价格全部为合成示例。源码见 [demo.py](src/v099_ledger/demo.py)。

## 最小调用

```python
from v099_ledger.accounting import account
from v099_ledger.demo import synthetic_inputs
from v099_ledger.report import save_report

market, fills = synthetic_inputs()
result = account(market, fills, initial_cash=1000)
save_report("my-report", market, fills, result, data_kind="synthetic")
```

[examples/account_fills.py](examples/account_fills.py) 是可直接运行的版本。调用者必须显式提供初始现金；每笔成交必须显式提供价格、数量和费率。工具没有预设的真实交易参数。

`market` 是按时间严格递增的字典列表：

| 字段 | 含义 |
|---|---|
| `timestamp` | 非负、精确整数的 Unix 毫秒；不要求固定周期 |
| `mark_price` | 该时点用于结算和估值的正标记价 |
| `funding_rate` | 带符号小数；无结算时为 0 |

`fills` 是已发生或人工给定的成交列表，按时间排序；相同时点保留输入顺序：

| 字段 | 含义 |
|---|---|
| `timestamp` | 必须对应一个 `market` 时点 |
| `quantity` | 带符号的基础币数量，买入为正、卖出为负 |
| `price` | 已经给定的成交价，工具不生成成交价格 |
| `fee_rate` | 该笔成交的非负费率小数，必须显式提供 |

本版要求已有持仓只能用反向相同数量全部平仓。加仓、部分平仓和单笔反手会拒收；可以先平仓再开仓。这个限制属于输入格式支持范围。工具不会自动平仓、补发成交或限制用户给定的敞口。

字段严格按白名单接收，不接收信号、研究参数或任意附加字段。实际行情、成交和费率的正确性由调用者负责；私有使用者不应把真实成交报告当成可公开的示例。

## 会计公式

```text
手续费 = abs(成交数量) × 已给定成交价 × 已给定费率
平仓毛盈亏 = 平仓前持仓数量 × (平仓成交价 - 开仓成交价)
资金费现金流 = -结算前持仓数量 × 标记价 × 资金费率
现金变化 = 已实现盈亏 - 手续费 + 资金费现金流
未实现盈亏 = 当前持仓数量 × (标记价 - 开仓成交价)
权益 = 现金 + 未实现盈亏
```

开仓不扣名义本金，只扣手续费。每个时点先按已有仓位结算资金费，再处理输入成交，再按该标记价估值。该顺序明确写入 `run.json`；它是本报告的会计约定，使用者必须先将真实来源对齐到这个约定。

示例的手算结果：

- 多头：2 单位在 100 开仓、103 平仓；手续费共 0.406，资金费 -2.02，净盈亏 +3.574。
- 空头：1 单位在 100 开仓、97 平仓；手续费共 0.197，资金费 -0.98，净盈亏 +1.823。
- 初始 1,000，最终权益 1,005.397。这是人工构造的会计例题。

没有保证金、强平、订单簿、滑点生成、成交队列、历史步长或手续费返佣模型。非正现金或权益会按给定数据继续记账，不代表模拟了真实账户处置。

## 独立验证与报告

报告只包含下列文件：

| 文件 | 内容 |
|---|---|
| `run.json` | 格式版本、会计约定、数量/现金单位、初始现金、标签 |
| `market.csv` | 调用者提供的估值和结算输入 |
| `fills.csv` | 调用者提供的成交数量、价格和费率 |
| `ledger.jsonl` | 按顺序编号的开仓、结算、平仓记账事件 |
| `equity.csv` | 每个时点的现金、持仓和权益 |
| `trades.csv` | 已完成交易的盈亏、费用与资金费 |
| `summary.json` | 总体现金、权益、费用、资金费及未平仓数量 |
| `manifest.json` | 上述七个文件的 SHA-256 |

`verification.py` 从输入成交和估值重新计算预期事件，再核对账本、权益和汇总。它不导入 `accounting.py` 或调用其会计函数；只共享格式和序列化检查。少一笔成交、漏记资金费、错误数量、改动汇总后重新生成哈希，都不能靠文件哈希绕过计算检查。

缺文件、未知格式、格式错误或数值不符会报错，CLI 返回非零退出码；没有跳过检查后仍算通过的路径。验证不依赖 Python `assert`，`python -O` 下仍执行。

**PASS 只表示相对于给定输入的会计一致性。** 数据和所有产物如果一起被改成另一套自洽结果，工具不能证明其来源真实。它不认证数据、不验证策略、不证明成交合理或收益可复制。输入中已经缺失的真实资金费也无法凭空恢复。

使用 float：现金/盈亏比较绝对容差为 `1e-7`、相对容差 `1e-10`；价格、数量和费率仅使用相对容差，零值须精确相等。适用于研究复核，不是定点精度的交易所账单系统。

## 开发

```bash
python -m pip install '.[test]' build
python -m pytest
python -m build
```

测试覆盖手算多空、正负资金费、结算时点、末端保留仓位、输入拒收、重新写哈希后的篡改、独立验证器导入、CLI 与拒绝覆盖。CI 配置覆盖 Python 3.11/3.12/3.13；配置存在不等于已经在 GitHub 运行通过。

0.2.0 使用报告格式 v2，不接收旧格式。旧接口不作为兼容层保留，以避免重新带入决策逻辑。

代码按 [MIT License](LICENSE) 提供。来源边界见 [PROVENANCE.md](PROVENANCE.md)。
