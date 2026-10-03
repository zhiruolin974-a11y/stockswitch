"""User-facing desktop text. Business-layer messages remain unchanged in logs.

The GUI defaults to Simplified Chinese.  A small English catalogue is retained so
future locale selection need not change the business layer; missing English entries
fall back to Chinese instead of leaking an untranslated implementation key.
"""

from __future__ import annotations

import logging
from enum import Enum


LOG = logging.getLogger(__name__)
DEFAULT_LOCALE = "zh_CN"


def install_qt_chinese(app):
    """Use Qt's shipped Chinese catalogue for calendar and standard edit menus."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    QLocale.setDefault(QLocale(DEFAULT_LOCALE))
    if not hasattr(app, "_stockswitch_qt_translator"):
        translator = QTranslator(app)
        if not translator.load("qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            LOG.warning("Qt Simplified Chinese catalogue could not be loaded")
        app.installTranslator(translator)
        app._stockswitch_qt_translator = translator
    return app._stockswitch_qt_translator

_ZH_CN = {
    "app.title": "StockSwitch · 模拟交易",
    "app.paper_only": "仅模拟交易 · 不连接真实券商 · 不发送真实订单",
    "app.first_run_title": "使用前请先了解",
    "app.first_run_warning": "本软件仅供个人研究与模拟交易。行情可能延迟、缺失或不准确；不构成投资建议，也不会连接真实券商或发送真实订单。",
    "app.do_not_show_again": "下次不再提示",
    "nav.overview": "总览",
    "nav.paper": "模拟交易",
    "nav.backtest": "历史回测",
    "nav.records": "交易记录",
    "nav.settings": "设置",
    "common.none": "暂无",
    "common.unknown": "未知",
    "common.not_available": "—",
    "common.buy": "买入",
    "common.sell": "卖出",
    "common.hold": "观望",
    "common.enabled": "启用",
    "common.disabled": "停用",
    "common.yes": "是",
    "common.no": "否",
    "common.confirm": "确认",
    "common.cancel": "取消",
    "common.close": "关闭",
    "common.time": "时间",
    "common.symbol": "证券代码",
    "common.name": "名称",
    "common.quantity": "数量（股）",
    "common.price": "价格（元/股）",
    "common.source": "数据来源",
    "common.no_data": "暂无数据",
    "status.connected": "已连接",
    "status.disconnected": "未连接，停止交易",
    "status.stale": "行情过期或异常，停止交易",
    "status.delayed": "近似实时／可能延迟",
    "status.normal": "行情已更新",
    "status.market_open": "交易时段",
    "status.market_closed": "已收盘 / 休市",
    "status.lunch_break": "午间休市",
    "status.new": "待处理",
    "status.filled": "已模拟成交",
    "status.rejected": "已拒绝",
    "status.cancelled": "已取消",
    "status.unknown": "状态未知",
    "source.tencent": "腾讯财经公开行情",
    "source.fake": "离线模拟行情",
    "source.historical": "历史日线行情",
    "strategy.manual": "手动模拟交易",
    "strategy.trend": "趋势突破策略",
    "strategy.unknown": "未知策略",
    "signal.trend_exit": "价格或均线走弱，触发趋势退出",
    "signal.trend_entry": "均线趋势、前高突破及成交量条件满足",
    "signal.manual": "用户发起的模拟委托",
    "signal.unknown": "策略信号（详情请查看日志）",
    "risk.unknown": "风控原因未识别，请查看日志",
    "risk.stale": "行情过期或时间异常，停止交易",
    "error.unknown": "操作未完成，请查看应用日志了解详情。",
    "error.network": "行情请求失败，请检查网络连接后重试。",
    "error.provider": "行情服务未连接，请先启动行情监控。",
    "error.market_data": "行情数据缺失或无效，已停止交易。",
    "error.stale": "行情已过期或时间异常，已停止交易。",
    "error.symbol": "证券代码不受支持，请输入有效的 A 股代码。",
    "error.watchlist_full": "自选股最多可添加 8 只。",
    "error.watchlist_held": "该证券仍有模拟持仓，不能从自选股移除。",
    "error.watchlist_missing": "该证券不在自选股中。",
    "error.database": "无法访问本地交易数据，请检查应用数据目录。",
    "error.permission": "没有权限访问所需文件，请检查应用数据目录。",
    "error.backtest": "历史回测失败，请检查输入和历史数据。",
    "error.config": "配置文件无效，请检查配置后重新启动。",
    "error.start_monitoring": "请先启动行情监控。",
    "settings.read_only": "此页展示当前启动配置，不能在这里保存修改。需要调整时，请编辑配置文件并重启应用。",
    "settings.paper_note": "初始模拟资金只用于新建账户；已有模拟账户从本地交易日记恢复，不会因此重置。",
    "settings.strategy_note": "实时行情模拟按采样次数计算窗口；历史回测使用已完成的日线。这里显示的是配置默认值。",
    "settings.path_note": "本地路径仅用于保存模拟数据、日志和导出文件。不会读取真实券商账户。",
}

_EN_US = {
    "app.title": "StockSwitch · Paper Trading",
    "app.paper_only": "Paper trading only · No brokerage connection · No real orders",
    "nav.overview": "Overview",
    "nav.paper": "Paper Trading",
    "nav.backtest": "Historical Backtest",
    "nav.records": "Trade Records",
    "nav.settings": "Settings",
    "common.buy": "Buy",
    "common.sell": "Sell",
    "common.hold": "Hold",
    "common.enabled": "Enabled",
    "common.disabled": "Disabled",
    "status.connected": "Connected",
    "status.disconnected": "Disconnected; trading stopped",
    "status.stale": "Stale or invalid data; trading stopped",
    "status.delayed": "Approximate / possibly delayed",
    "status.normal": "Quotes updated",
    "strategy.manual": "Manual paper trade",
    "strategy.trend": "Trend breakout demonstration strategy",
}

CATALOGS = {"zh_CN": _ZH_CN, "en_US": _EN_US}

_ZH_CN.update({
    "account.equity": "总资产", "account.cash": "可用资金", "account.value": "持仓市值",
    "account.daily": "今日盈亏", "account.cumulative": "累计盈亏", "account.initial": "起始资金",
    "market.connect": "连接行情", "market.stop": "停止监控", "market.add": "添加自选",
    "market.remove": "移除自选", "market.code_hint": "股票代码，如 000001",
    "market.indexes": "主要指数", "market.watchlist": "自选行情", "market.empty": "连接行情后显示报价。",
    "market.normal": "● 行情正常", "market.delayed": "● 行情延迟", "market.stale": "● 行情数据已过期",
    "market.disconnected": "● 行情断开", "market.connecting": "正在连接行情…",
    "paper.account": "模拟账户", "paper.manual": "手动模拟交易", "paper.auto": "策略自动模拟",
    "paper.buy": "模拟买入", "paper.sell": "模拟卖出", "paper.estimate": "预计金额：约 {amount}（未含费用）",
    "paper.reference": "股票：{name}  {symbol}\n数量：{quantity} 股\n参考价格：{price}\n预计金额：约 {amount}\n\n这是模拟交易，不会产生真实订单。",
    "paper.confirm": "确认{action}", "paper.holdings": "模拟持仓", "paper.no_positions": "当前没有模拟持仓。",
    "paper.signals": "交易信号与风控结果", "paper.no_signals": "当前暂无交易信号。",
    "paper.start_auto": "启动自动模拟", "paper.stop_auto": "停止自动模拟",
    "paper.auto_warning": "本功能仅使用虚拟资金，不会产生真实证券订单。是否启动趋势突破策略自动模拟？",
    "paper.running": "运行中", "paper.stopped": "已停止", "paper.paused": "行情暂不可用，自动模拟已暂停",
    "paper.first_notice": "StockSwitch 当前为模拟交易模式。\n所有资金均为虚拟资金，\n不会连接券商或产生真实证券订单。",
    "paper.pending": "模拟委托处理中…", "paper.no_quote": "尚无可用报价，请先连接行情并添加该股票。",
    "paper.success": "{action}成功 · 成交价格 {price} · 数量 {quantity} 股 · 手续费 {fees} · 剩余资金 {cash}",
    "paper.failure": "{action}未完成：{reason}",
    "backtest.empty": "请设置参数后运行历史回测。", "backtest.run": "开始回测",
    "backtest.cancel": "取消回测", "backtest.running": "正在回测…", "backtest.export": "导出 CSV / JSON",
    "backtest.loading": "正在加载历史行情…", "backtest.calculating": "正在计算历史回测…",
    "backtest.cancel_requested": "正在取消回测…", "backtest.cancelled": "回测已取消，未保存未完成结果。",
    "backtest.invalid": "回测参数无效，请检查股票代码、日期范围和证券类别。",
    "backtest.failed": "历史回测失败，请检查历史数据或查看日志。",
    "backtest.exported": "已导出至 {path}", "backtest.export_failed": "导出失败，请检查目录权限和日志。",
})


def tr(key: str, locale: str = DEFAULT_LOCALE, **params: object) -> str:
    """Translate a semantic UI key, defaulting safely to Simplified Chinese."""
    catalog = CATALOGS.get(locale, _ZH_CN)
    value = catalog.get(key, _ZH_CN.get(key))
    if value is None:
        LOG.warning("Missing UI translation: %s", key)
        return "未翻译文案"
    return value.format(**params) if params else value


def _value(item: object) -> str:
    return str(item.value if isinstance(item, Enum) else item)


_SIDES = {"BUY": "common.buy", "SELL": "common.sell", "HOLD": "common.hold"}
_STATUSES = {
    "NEW": "status.new", "FILLED": "status.filled", "REJECTED": "status.rejected",
    "CANCELLED": "status.cancelled", "Market Open": "status.market_open",
    "Market Closed": "status.market_closed", "Lunch Break": "status.lunch_break",
    "connected": "status.connected", "disconnected": "status.disconnected",
    "stale": "status.stale", "delayed": "status.delayed", "normal": "status.normal",
}
_STRATEGIES = {"Manual Paper": "strategy.manual", "TrendBreakoutStrategy": "strategy.trend"}
_SIGNAL_REASONS = {
    "Trend exit: price or moving averages weakened": "signal.trend_exit",
    "MA trend, prior-high breakout and volume filter": "signal.trend_entry",
    "User paper order": "signal.manual",
}
_RISK_REASONS = {
    "A-share market is not open": "A 股市场当前未开市，停止交易",
    "Only BUY and SELL can become orders": "只有买入和卖出信号可形成模拟委托",
    "Signal symbol does not match quote": "信号证券代码与行情不一致，停止交易",
    "Deferred signal must precede execution quote": "延后信号与执行行情顺序异常，停止交易",
    "Signal does not match current market quote": "信号与当前行情不一致，停止交易",
    "Quantity must be a positive lot multiple or a full odd-lot exit": "数量必须为正数且符合整手规则；清仓零股除外",
    "Daily virtual loss limit reached": "已达到当日模拟亏损上限，停止交易",
    "Selling disabled by configuration": "配置已禁止模拟卖出",
    "Insufficient T+1 available holdings": "今日买入的 A 股当前不可卖出（T+1），或可卖持仓不足",
    "Sell allowed": "模拟卖出风控已通过",
    "Buying disabled by configuration": "配置已禁止模拟买入",
    "Insufficient virtual cash": "模拟可用资金不足",
    "Single order limit exceeded": "单笔模拟委托超过限额",
    "Single position limit exceeded": "单只证券持仓超过限额",
    "Total position limit exceeded": "总持仓超过限额",
    "Buy allowed": "模拟买入风控已通过",
    "Disconnected / Data Stale": "行情未连接或已过期，停止交易",
    "Invalid paper order": "模拟委托无效",
    "insufficient_cash": "可用资金不足",
    "position_limit": "单只股票仓位超过上限",
    "total_position_limit": "总仓位超过上限",
    "daily_loss_limit": "今日亏损已达到风控上限",
    "t1_restriction": "今日买入的 A 股当前不可卖出（T+1）",
    "stale_market_data": "行情数据已过期，系统已暂停交易",
}


def side_label(side: object, locale: str = DEFAULT_LOCALE) -> str:
    return tr(_SIDES.get(_value(side).upper(), "common.unknown"), locale)


def status_label(status: object, locale: str = DEFAULT_LOCALE) -> str:
    raw = _value(status)
    return tr(_STATUSES.get(raw, _STATUSES.get(raw.upper(), "status.unknown")), locale)


def strategy_label(name: object, locale: str = DEFAULT_LOCALE) -> str:
    return tr(_STRATEGIES.get(_value(name), "strategy.unknown"), locale)


def signal_reason(reason: object, locale: str = DEFAULT_LOCALE) -> str:
    return tr(_SIGNAL_REASONS.get(_value(reason), "signal.unknown"), locale)


def risk_reason(reason: object, locale: str = DEFAULT_LOCALE) -> str:
    """Localize known RiskManager decisions without changing stored reasons."""
    raw = _value(reason)
    if raw.startswith("Data stale:"):
        return tr("risk.stale", locale)
    return _RISK_REASONS.get(raw, tr("risk.unknown", locale))


def data_source_label(source: object, locale: str = DEFAULT_LOCALE) -> str:
    raw = _value(source)
    if "Fake" in raw:
        return tr("source.fake", locale)
    if "Tencent" in raw:
        return tr("source.tencent", locale)
    if "Historical" in raw:
        return tr("source.historical", locale)
    return tr("common.unknown", locale)


def user_error(message: str) -> str:
    """Classify known technical errors; never expose raw exceptions in the GUI."""
    raw = str(message)
    lower = raw.lower()
    if raw in _RISK_REASONS or raw.startswith("Data stale:"):
        return risk_reason(raw)
    if "start monitoring" in lower:
        return tr("error.start_monitoring")
    if "unsupported a-share symbol" in lower or "invalid symbol" in lower:
        return tr("error.symbol")
    if "watchlist is limited" in lower:
        return tr("error.watchlist_full")
    if "cannot remove a stock with an open paper position" in lower:
        return tr("error.watchlist_held")
    if "not in list" in lower:
        return tr("error.watchlist_missing")
    if "quote age" in lower or "timestamp regressed" in lower or "stale" in lower:
        return tr("error.stale")
    if "market provider is disconnected" in lower:
        return tr("error.provider")
    if "market request failed" in lower or "timed out" in lower or "urlopen" in lower:
        return tr("error.network")
    if any(part in lower for part in ("missing quotes", "incomplete quote", "invalid quote", "market response", "oversized quote")):
        return tr("error.market_data")
    if any(part in lower for part in ("sqlite", "database is locked", "unable to open database")):
        return tr("error.database")
    if "permission denied" in lower or "access is denied" in lower:
        return tr("error.permission")
    if "backtest" in lower or "historical" in lower:
        return tr("error.backtest")
    if "config" in lower or "toml" in lower:
        return tr("error.config")
    return tr("error.unknown")
