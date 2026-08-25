# Design Tokens — 全球市场金融资讯日报

> 本文档是前端设计规范的**唯一事实来源**。
> 实现侧在 `web/css/design-tokens.css` 的 `:root`（与 `[data-theme="light"]`）中落地同一套变量，
> 所有组件样式（`web/css/styles.css`）只引用变量，禁止写死颜色/字号。

## 1. 设计原则

1. **数据优先**：深色面板 + 高对比数值，数字用等宽字体对齐，一眼可读。
2. **涨跌语义遵循 A 股习惯**：红 = 涨，绿 = 跌（如面向海外读者可切 `--color-up/down` 对调）。
3. **克制用色**：主色仅用于品牌、链接与强调；涨跌色只用于数值。
4. **状态可解释**：每一条行情/新闻都带"核实"状态（✓ 通过 / ⚠ 单源 / ⚠ 冲突）。
5. **主题可切换**：深色为默认（`data-theme="dark"`），提供 `data-theme="light"` 覆盖层。

## 2. 变量清单

### 2.1 颜色

| 变量 | 深色默认 | 浅色覆盖 | 用途 |
| --- | --- | --- | --- |
| `--color-bg` | `#0b1220` | `#f3f5f9` | 页面背景 |
| `--color-bg-grad-1` | `#0b1220` | `#f3f5f9` | 背景渐变起始 |
| `--color-bg-grad-2` | `#0f1a30` | `#e8edf6` | 背景渐变结束 |
| `--color-surface` | `#111a2c` | `#ffffff` | 卡片表面 |
| `--color-surface-2` | `#1a2740` | `#f0f3f9` | 内嵌/表头 |
| `--color-surface-3` | `#223355` | `#e4eaf4` | 悬停/选中 |
| `--color-border` | `#243250` | `#dbe2ee` | 常规边框 |
| `--color-border-strong` | `#31456e` | `#c2cde0` | 强调边框 |
| `--color-text` | `#e8edf6` | `#17233d` | 主文本 |
| `--color-text-muted` | `#93a3c0` | `#55637f` | 次要文本 |
| `--color-text-faint` | `#5d7091` | `#8b98b3` | 弱文本 |
| `--color-text-on-accent` | `#ffffff` | `#ffffff` | 强调背景上的文字 |
| `--color-accent` | `#3b82f6` | `#2563eb` | 品牌主色/链接 |
| `--color-accent-soft` | `rgba(59,130,246,.14)` | `rgba(37,99,235,.1)` | 主色浅底 |
| `--color-up` | `#ef4444` | 同左 | 涨（红） |
| `--color-up-soft` | `rgba(239,68,68,.12)` | 同左 | 涨色浅底 |
| `--color-down` | `#22c55e` | 同左 | 跌（绿） |
| `--color-down-soft` | `rgba(34,197,94,.12)` | 同左 | 跌色浅底 |
| `--color-flat` | `#94a3b8` | 同左 | 平/无变化 |
| `--color-warn` | `#f59e0b` | 同左 | 警示/待核 |
| `--color-warn-soft` | `rgba(245,158,11,.12)` | 同左 | 警示浅底 |
| `--color-ok` | `#22c55e` | 同左 | 核实通过 |
| `--color-danger` | `#ef4444` | 同左 | 核实失败 |
| `--color-morning` | `#3b82f6` | 同左 | 成交额追踪·上午段 |
| `--color-morning-soft` | `rgba(59,130,246,.16)` | 同左 | 上午段浅底 |
| `--color-afternoon` | `#8b5cf6` | 同左 | 成交额追踪·下午段 |
| `--color-afternoon-soft` | `rgba(139,92,246,.18)` | 同左 | 下午段浅底 |

### 2.2 字体

| 变量 | 值 |
| --- | --- |
| `--font-sans` | `-apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif` |
| `--font-mono` | `"SF Mono", "JetBrains Mono", "Fira Code", Menlo, Consolas, monospace` |

### 2.3 字号（px）

`--text-xs: 11` · `--text-sm: 13` · `--text-md: 15` · `--text-lg: 18` · `--text-xl: 24` · `--text-2xl: 32`

### 2.4 间距（px）

`--space-1: 4` · `--space-2: 8` · `--space-3: 12` · `--space-4: 16` · `--space-5: 24` · `--space-6: 32`

### 2.5 圆角 / 阴影 / 布局

- 圆角：`--radius-sm: 6` · `--radius-md: 10` · `--radius-lg: 16` · `--radius-pill: 999`
- 阴影：`--shadow-card`（卡片）· `--shadow-pop`（浮层）
- 动效：`--transition: 0.18s ease`
- 布局：`--max-width: 1200px` · `--header-height: 64px`

## 3. 使用约定

- 数值统一用 `.num` 类 + 等宽字体右对齐；涨跌色用 `.pct-up / .pct-down / .pct-flat`。
- 状态语义：`--color-ok` 通过、`--color-warn` 单源/待核、`--color-danger` 冲突/失败。
- 新组件一律在 `styles.css` 中引用上述变量；如需新 token，先更新本文件与 `design-tokens.css`。

## 4. 主题

- 默认深色；`<html>`/`<body>` 上 `data-theme="light"` 即切浅色（变量覆盖在 `design-tokens.css` 底部）。
- 主题选择持久化在 `localStorage["theme"]`。
