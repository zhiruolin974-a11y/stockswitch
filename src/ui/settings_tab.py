"""Read-only, grouped view of the effective desktop configuration.

AppConfig is immutable and this tab does not imply that edits are persisted.  The
runtime toggle for the demonstration strategy belongs to the paper-trading UI.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from src.app.config import AppConfig
from src.app.paths import AppPaths, PROJECT_ROOT, resource_path
from src.ui.formatting import money, percent_ratio
from src.ui.i18n import tr


_PROFILES = {
    "unknown": "未指定（回测不允许成交）",
    "main_normal": "主板普通股票",
    "main_st": "主板 ST 股票",
    "chinext": "创业板",
    "star": "科创板",
}


def _active_config_source(paths: AppPaths) -> Path:
    if paths.app_data_dir == PROJECT_ROOT and (PROJECT_ROOT / "config.toml").exists():
        return PROJECT_ROOT / "config.toml"
    if paths.config_path.exists():
        return paths.config_path
    return resource_path("config.example.toml")


class SettingsTab(QWidget):
    """Settings information without mutation or misleading Save controls."""

    def __init__(self, config: AppConfig, *, paths: AppPaths | None = None):
        super().__init__()
        self.config = config
        self.paths = paths or AppPaths.for_runtime()
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        self.read_only_label = QLabel(tr("settings.read_only"))
        self.read_only_label.setWordWrap(True)
        self.read_only_label.setObjectName("settingsReadOnlyNotice")
        layout.addWidget(self.read_only_label)

        general = self._group(layout, "常规")
        self._row(general, "界面语言", "简体中文（zh_CN）",
                  "当前完整支持简体中文，已预留国际化结构；英文界面尚未开放。")

        account = self._group(layout, "模拟账户与行情")
        self._row(account, "初始模拟资金", money(config.initial_cash),
                  "仅在建立新的模拟账户时使用，不会覆盖已保存的账户。")
        self._row(account, "启动自选股", "、".join(config.watchlist) or "暂无")
        self._row(account, "交易时段行情刷新", f"{config.market_refresh_seconds} 秒")
        self._row(account, "非交易时段行情刷新", f"{config.closed_refresh_seconds} 秒")
        self._row(account, "允许的行情最大年龄", f"{config.max_quote_age_seconds} 秒",
                  "行情时间过期、倒退或数据无效时，交易会停止。")
        self.paper_note_label = QLabel(tr("settings.paper_note"))
        self.paper_note_label.setWordWrap(True)
        layout.addWidget(self.paper_note_label)

        costs = self._group(layout, "模拟成交与费用")
        self._row(costs, "最小交易单位", f"{config.lot_size:,} 股",
                  "卖出全部可用零股时允许例外。")
        self._row(costs, "模拟滑点", f"{config.slippage_bps:g} 基点",
                  "1 基点 = 0.01%；仅用于模拟成交价格。")
        self._row(costs, "佣金费率", percent_ratio(config.commission_rate),
                  "每笔模拟成交按金额乘以费率计算，并受最低佣金约束。")
        self._row(costs, "最低佣金", money(config.minimum_commission), "每笔模拟成交佣金的最低金额。")
        self._row(costs, "卖出印花税率", percent_ratio(config.stamp_tax_rate), "仅模拟卖出时，按成交金额乘以税率计算。")

        risk = self._group(layout, "风险控制")
        self._row(risk, "单只证券持仓上限", percent_ratio(config.max_single_position),
                  "相对于当前模拟总资产。")
        self._row(risk, "总持仓上限", percent_ratio(config.max_total_position),
                  "相对于当前模拟总资产。")
        self._row(risk, "单笔委托上限", percent_ratio(config.max_order_fraction),
                  "相对于当前模拟总资产。")
        self._row(risk, "当日模拟亏损上限", percent_ratio(config.max_daily_loss),
                  "相对于当日开始时的模拟总资产。")
        self._row(risk, "允许模拟买入", tr("common.yes") if config.allow_buy else tr("common.no"))
        self._row(risk, "允许模拟卖出", tr("common.yes") if config.allow_sell else tr("common.no"))

        strategy = self._group(layout, "演示策略（启动默认值）")
        self._row(strategy, "配置中的自动策略默认值", tr("common.enabled") if config.strategy_enabled else tr("common.disabled"),
                  "桌面界面每次启动先停止自动模拟，需在模拟交易页确认后启动；此值不代表当前运行状态。")
        self._row(strategy, "桌面自动模拟启动方式", "在模拟交易页确认后启动")
        self._row(strategy, "短均线窗口", f"{config.short_window} 次采样")
        self._row(strategy, "长均线窗口", f"{config.long_window} 次采样")
        self._row(strategy, "突破窗口", f"{config.breakout_window} 次采样")
        self._row(strategy, "成交量倍数阈值", f"{config.volume_multiplier:g} 倍")
        self._row(strategy, "信号委托数量", f"{config.order_quantity:,} 股")
        strategy_note = QLabel(tr("settings.strategy_note"))
        strategy_note.setWordWrap(True)
        layout.addWidget(strategy_note)

        backtest = self._group(layout, "历史回测默认值")
        self._row(backtest, "基准指数", config.backtest_benchmark)
        self._row(backtest, "无风险年化利率", percent_ratio(config.backtest_risk_free_rate))
        self._row(backtest, "年化交易日数", f"{config.backtest_annualization_factor} 日")
        self._row(backtest, "证券板块核验", _PROFILES.get(config.backtest_security_profile, "未知"),
                  "未核验的证券板块在回测中不能成交。")

        storage = self._group(layout, "本地文件位置")
        self.config_source_label = self._row(storage, "当前配置来源", str(_active_config_source(self.paths)))
        self.data_dir_label = self._row(storage, "应用数据目录", str(self.paths.app_data_dir))
        self._row(storage, "模拟交易数据库", str(self.paths.database_path))
        self._row(storage, "历史回测数据库", str(self.paths.backtests_path))
        self._row(storage, "历史行情缓存目录", str(self.paths.history_dir))
        self._row(storage, "日志目录", str(self.paths.logs_dir))
        self._row(storage, "导出目录", str(self.paths.exports_dir))
        path_note = QLabel(tr("settings.path_note"))
        path_note.setWordWrap(True)
        layout.addWidget(path_note)
        layout.addStretch(1)

    @staticmethod
    def _group(layout: QVBoxLayout, title: str) -> QFormLayout:
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addWidget(group)
        return form

    @staticmethod
    def _row(form: QFormLayout, label: str, value: str, tooltip: str = "") -> QLabel:
        widget = QLabel(value)
        widget.setWordWrap(True)
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if tooltip:
            widget.setToolTip(tooltip)
        form.addRow(label, widget)
        return widget
