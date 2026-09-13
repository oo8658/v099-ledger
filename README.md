# v099-ledger

**纯记账与独立复核工具。** 输入已经指定的成交、标记价、资金费率；输出现金、持仓、费用和盈亏。程序不决定何时买卖、买卖多少或何时退出。

Policy-free linear perpetual accounting for supplied fills, with an independent verifier. Runtime uses the Python standard library only.

当前版本：0.3.0。单标的、报价币结算、基础币数量、多头或空头、一次一个净持仓。新增 v3 显式事件接口，支持加仓、部分平仓、反手和延迟入账资金费；原 v2 接口及报告格式保留。没有策略、信号、仓位分配、止损、参数搜索、交易所客户端、账户或下单接口。

## 安装和演示

需要 Python 3.11 或更新版本。在本目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
v099-ledger demo --output ./demo-report
v099-ledger verify ./demo-report
v099-ledger demo-events --output ./event-report
v099-ledger verify-events ./event-report
```

Windows 命令提示符的激活命令为 `.venv\Scripts\activate`。也可以用 `python -m v099_ledger` 替代命令。安装后运行不需要网络或第三方运行依赖。已有输出目录会被拒绝覆盖。

v2 演示是 6 个人工标记价点和 4 笔人工指定成交，共 2 笔完整交易。v3 演示是 13 个显式人工事件，其中有 6 笔人工成交。数量和时点都写死在算术示例中，不根据价格变化产生，没有盈利有效性含义。`SYNTH` 标签、毫秒时点和价格全部为合成示例。源码见 [demo.py](src/v099_ledger/demo.py) 和 [event_demo.py](src/v099_ledger/event_demo.py)。

## v3：显式事件记账

```python
from v099_ledger.event_accounting import account_events
from v099_ledger.event_demo import synthetic_events
from v099_ledger.event_report import save_event_report
from v099_ledger.event_verification import verify_event_report

events = synthetic_events()
result = account_events(events, initial_cash=1000)
save_event_report("event-report", events, result, data_kind="synthetic")
print(verify_event_report("event-report"))
```

`events` 按输入顺序处理，同一毫秒内也不重排；第一个事件必须是 `mark`。每个事件只接受下表列出的字段，不接收任意附加字段。

| 事件 | 必需字段 | 含义 |
|---|---|---|
| `mark` | `timestamp`, `kind`, `price` | 更新正标记价，仅用于估值 |
| `fill` | `timestamp`, `kind`, `quantity`, `price`, `fee_rate` | 已给定的带符号成交数量、成交价与费率；可加仓、部分平仓或反手 |
| `funding_due` | `timestamp`, `kind`, `id` | 记录此刻的持仓数量及所属交易周期，等待结算输入 |
| `funding_post` | `timestamp`, `kind`, `id`, `rate`, `settlement_mark` | 根据匹配到期事件的数量和明确给定的费率、结算价入账 |

`timestamp` 是非负精确整数毫秒，整体非递减。资金费 `id` 在一份报告内唯一，且每个 `funding_due` 必须在报告结束前恰好对应一次 `funding_post`；可以在原持仓已经平掉之后入账，现金流仍归到原交易周期。正费率下，多头支付、空头收取。空仓到期记录的资金费为零。`funding_post` 的 `settlement_mark` 是调用者提供的结算价，不由最近估值推断。延迟入账之前的权益不包含尚未入账的资金费。

同向加仓采用成交数量加权成本价。部分平仓只对已平数量实现盈亏，剩余持仓继续使用原成本价。单笔反手先平旧仓、再以同一成交价建立反向仓，并按数量比例分配该笔手续费。`trades.json` 只列已完整平掉的交易周期，`summary.json` 同时保留尚未平掉的仓位和未实现盈亏。已平交易的资金费可以在后来入账，历史交易合计在最终报告中更新。

v3 报告文件固定为 `run.json`、`events.json`、`ledger.json`、`trades.json`、`summary.json` 和 `manifest.json`。独立的 `event_verification.py` 从 `events.json` 重新记账，并核对每一行账本、每笔已平交易和汇总；它不导入 `event_accounting.py`。修改派生文件后重新写哈希仍会被拒绝。`verify-events` 不接受 v2 格式，`verify` 不接受 v3 格式。v3 新接口同样不对输入事件真实性作认证。

下文的 `account`、`save_report`、`verify_report`、`demo` 与 `verify` 继续说明 v2 完整平仓接口，其计算约定和格式未改变。

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

v2 接口要求已有持仓只能用反向相同数量全部平仓。加仓、部分平仓和单笔反手会拒收；这些操作请使用上面的 v3 显式事件接口。工具不会自动平仓、补发成交或限制用户给定的敞口。

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

v2 使用 float 会计；v3 内部使用 Decimal 记账，报告仍序列化为 JSON 数字。两个验证器的现金/盈亏比较绝对容差为 `1e-7`、相对容差为 `1e-10`；价格和数量仅使用相对容差，零值须精确相等。适用于研究复核，不是定点精度的交易所账单系统。

## 开发

```bash
python -m pip install '.[test]' build
python -m pytest
python -m build
```

测试覆盖手算多空、正负资金费、部分平仓、反手、延迟入账、结算时点、末端保留仓位、输入拒收、重新写哈希后的篡改、独立验证器导入、CLI 与拒绝覆盖。CI 配置覆盖 Python 3.11/3.12/3.13；配置存在不等于已经在 GitHub 运行通过。

0.2.0 起使用报告格式 v2；0.3.0 增加格式 v3，二者的命令和报告分别验证，不互相解释。没有兼容早期实验格式的接口，以避免重新带入决策逻辑。

代码按 [MIT License](LICENSE) 提供。来源边界见 [PROVENANCE.md](PROVENANCE.md)。
