"""Small display-only building blocks shared by the desktop pages."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel,
                              QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setAlternatingRowColors(True)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.verticalHeader().setVisible(False)
    return widget


def fill_table(widget, rows, colors=None, tooltips=None):
    widget.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if colors and (row, column) in colors:
                item.setForeground(QColor(colors[row, column]))
            if tooltips:
                item.setToolTip(tooltips[row])
            widget.setItem(row, column, item)
    widget.resizeColumnsToContents()


class MetricStrip(QWidget):
    def __init__(self, titles):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.values = {}
        for key, title in titles:
            card = QWidget()
            card.setStyleSheet("background: white; border-radius: 4px;")
            body = QVBoxLayout(card)
            label = QLabel(title)
            label.setStyleSheet("color: #667085;")
            value = QLabel("—")
            value.setMinimumHeight(46)
            value.setStyleSheet("font-size: 17px; font-weight: 600;")
            body.addWidget(label)
            body.addWidget(value)
            layout.addWidget(card, 1)
            self.values[key] = value

    def set_value(self, key, text, color=None, tooltip=""):
        label = self.values[key]
        label.setText(text)
        label.setToolTip(tooltip)
        label.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {color or '#1d2939'};")
