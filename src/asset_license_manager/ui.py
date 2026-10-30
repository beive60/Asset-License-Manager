"""Asset License Manager のUI実装。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import (
    STATUS_FILE_NOT_FOUND,
    STATUS_FILLED,
    STATUS_MISSING,
    AssetLicenseCore,
    AssetRecord,
)


class AssetTableWidget(QTableWidget):
    """URL/Attribution 列への複数セル貼り付けを扱うテーブル。"""

    EDITABLE_COLUMNS = {5, 6}

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        """貼り付けショートカットを処理する。

        Args:
            event: キーイベント。
        """
        if event.matches(QKeySequence.Paste):
            self._paste_tabular_text()
            return
        super().keyPressEvent(event)

    def _paste_tabular_text(self) -> None:
        """クリップボードのTSVテキストを現在セル起点で貼り付ける。"""
        start_row = self.currentRow()
        start_col = self.currentColumn()
        if start_row < 0 or start_col < 0:
            return
        text = QApplication.clipboard().text()
        if not text:
            return

        rows = text.splitlines()
        for row_offset, row_text in enumerate(rows):
            target_row = start_row + row_offset
            if target_row >= self.rowCount():
                break
            values = row_text.split("\t")
            for col_offset, value in enumerate(values):
                target_col = start_col + col_offset
                if target_col >= self.columnCount():
                    break
                if target_col not in self.EDITABLE_COLUMNS:
                    continue
                item = self.item(target_row, target_col)
                if item is None:
                    item = QTableWidgetItem()
                    self.setItem(target_row, target_col, item)
                item.setText(value)


class AssetLicenseMainWindow(QMainWindow):
    """素材ライセンス管理画面を提供するメインウィンドウ。"""

    COLUMN_CHECK = 0
    COLUMN_STATUS = 1
    COLUMN_GENRE = 2
    COLUMN_CATEGORY = 3
    COLUMN_FILE_NAME = 4
    COLUMN_URL = 5
    COLUMN_ATTRIBUTION = 6
    COLUMN_HEADERS = ("[選]", "Status", "Genre", "Category", "File Name", "URL", "Attribution")
    MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    BLANK_LINE_PATTERN = re.compile(r"\n{3,}")
    NC_ID_PATTERN = re.compile(r"nc\d+")

    def __init__(self, root_dir: str | Path | None = None) -> None:
        """メインウィンドウを初期化する。

        Args:
            root_dir: 初期素材ルートディレクトリ。
        """
        super().__init__()
        self.setWindowTitle("Asset License Manager")
        self.resize(1200, 700)

        self.core: AssetLicenseCore | None = None
        self.current_root_dir: Path | None = None
        self.is_dirty = False
        self._is_populating = False
        self._header_checked = False

        self._build_ui()

        if root_dir is not None:
            self.set_root_directory(root_dir)

    def _build_ui(self) -> None:
        """メインレイアウトとウィジェットを構築する。"""
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        toolbar_layout = QHBoxLayout()
        root_layout.addLayout(toolbar_layout)

        self.select_dir_button = QPushButton("素材フォルダ選択")
        self.sync_button = QPushButton("同期")
        self.prune_button = QPushButton("File not foundを一括削除")
        self.delete_selected_button = QPushButton("選択行を削除（JSONから除外）")
        self.save_button = QPushButton("保存")
        self.generate_button = QPushButton("テキスト生成")
        self.path_label = QLabel("素材ルート: 未選択")

        toolbar_layout.addWidget(self.select_dir_button)
        toolbar_layout.addWidget(self.sync_button)
        toolbar_layout.addWidget(self.prune_button)
        toolbar_layout.addWidget(self.delete_selected_button)
        toolbar_layout.addWidget(self.save_button)
        toolbar_layout.addWidget(self.generate_button)
        toolbar_layout.addWidget(self.path_label, 1)

        self.table = AssetTableWidget()
        self.table.setColumnCount(len(self.COLUMN_HEADERS))
        self.table.setHorizontalHeaderLabels(list(self.COLUMN_HEADERS))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.horizontalHeader().sectionClicked.connect(self._toggle_check_column)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        root_layout.addWidget(self.table)

        self.select_dir_button.clicked.connect(self.select_root_directory)
        self.sync_button.clicked.connect(self.synchronize)
        self.prune_button.clicked.connect(self.prune_file_not_found_rows)
        self.delete_selected_button.clicked.connect(self.remove_selected_rows)
        self.save_button.clicked.connect(self.save_current_records)
        self.generate_button.clicked.connect(self.generate_credit_text)

    def select_root_directory(self) -> None:
        """素材ルートディレクトリを選択して同期する。"""
        selected = QFileDialog.getExistingDirectory(self, "素材ルートフォルダを選択")
        if selected:
            self.set_root_directory(selected)

    def set_root_directory(self, root_dir: str | Path) -> None:
        """素材ルートディレクトリを設定する。

        Args:
            root_dir: 設定する素材ルートディレクトリ。
        """
        self.current_root_dir = Path(root_dir)
        self.core = AssetLicenseCore(self.current_root_dir)
        self.path_label.setText(f"素材ルート: {self.current_root_dir}")
        self.synchronize()

    def synchronize(self) -> None:
        """コア同期を実行し、グリッドを最新化する。"""
        if self.core is None:
            return
        sync_result = self.core.synchronize()
        self._populate_rows(sync_result.records)
        self.is_dirty = False

    def prune_file_not_found_rows(self) -> None:
        """`File not found` 行を一括削除する。"""
        removed = False
        for row in reversed(range(self.table.rowCount())):
            status_item = self.table.item(row, self.COLUMN_STATUS)
            if status_item and status_item.text() == STATUS_FILE_NOT_FOUND:
                self.table.removeRow(row)
                removed = True
        if removed:
            self.is_dirty = True

    def save_current_records(self) -> None:
        """現在グリッドの内容をJSONへ保存する。"""
        if self.core is None:
            return
        self.core.save_records(self._collect_records())
        self.is_dirty = False

    def generate_credit_text(self) -> None:
        """チェック済み行から概要欄向けテキストを書き出す。"""
        default_root = self.current_root_dir if self.current_root_dir else Path.cwd()
        default_name = default_root / "概要欄コピペ用_クレジット一覧.txt"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "概要欄テキストを保存",
            str(default_name),
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return

        output = self._build_credit_output()
        Path(path).write_text(output, encoding="utf-8", newline="\n")

    def remove_selected_rows(self) -> None:
        """選択行を削除してJSON保存対象から除外する。"""
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            return
        for row in selected_rows:
            self.table.removeRow(row)
        self.is_dirty = True

    def remove_row_by_index(self, row: int) -> None:
        """指定行を削除してDirtyフラグを立てる。

        Args:
            row: 削除行インデックス。
        """
        if 0 <= row < self.table.rowCount():
            self.table.removeRow(row)
            self.is_dirty = True

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """終了時にDirty状態に応じた確認ダイアログを表示する。

        Args:
            event: クローズイベント。
        """
        if not self.is_dirty:
            event.accept()
            return

        answer = QMessageBox.question(
            self,
            "未保存の変更",
            "未保存の変更があります。終了前に保存しますか？",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )

        if answer == QMessageBox.Yes:
            self.save_current_records()
            event.accept()
        elif answer == QMessageBox.No:
            event.accept()
        else:
            event.ignore()

    def _populate_rows(self, records: Iterable[AssetRecord]) -> None:
        """レコード一覧をグリッドへ反映する。

        Args:
            records: 表示対象レコード。
        """
        self._is_populating = True
        self.table.setRowCount(0)
        for record in records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._set_row_items(row, record)
            self._apply_row_style(row, record.status)
        self._is_populating = False
        self._header_checked = False

    def _set_row_items(self, row: int, record: AssetRecord) -> None:
        """1行分のセルを設定する。"""
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
        check_item.setCheckState(Qt.Unchecked)
        self.table.setItem(row, self.COLUMN_CHECK, check_item)

        self.table.setItem(row, self.COLUMN_STATUS, self._readonly_item(record.status))
        self.table.setItem(row, self.COLUMN_GENRE, self._readonly_item(record.genre))
        self.table.setItem(row, self.COLUMN_CATEGORY, self._readonly_item(self._category_display(record)))
        self.table.setItem(row, self.COLUMN_FILE_NAME, self._readonly_item(Path(record.path).name))

        self.table.setItem(row, self.COLUMN_URL, self._editable_item(record.url))
        self.table.setItem(row, self.COLUMN_ATTRIBUTION, self._editable_item(record.attribution))

    def _on_item_changed(self, changed_item: QTableWidgetItem) -> None:
        """セル変更時にステータスとDirtyフラグを更新する。

        Args:
            changed_item: 変更されたセル。
        """
        if self._is_populating:
            return
        if changed_item.column() not in {self.COLUMN_URL, self.COLUMN_ATTRIBUTION}:
            return

        row = changed_item.row()
        status_item = self.table.item(row, self.COLUMN_STATUS)
        if status_item is not None and status_item.text() == STATUS_MISSING:
            url_text = self._item_text(row, self.COLUMN_URL).strip()
            attribution_text = self._item_text(row, self.COLUMN_ATTRIBUTION).strip()
            if url_text or attribution_text:
                self._is_populating = True
                status_item.setText(STATUS_FILLED)
                self._apply_row_style(row, STATUS_FILLED)
                self._is_populating = False
        self.is_dirty = True

    def _toggle_check_column(self, section: int) -> None:
        """チェック列ヘッダー押下時に全選択/全解除を行う。"""
        if section != self.COLUMN_CHECK:
            return

        target_state = Qt.Checked if not self._header_checked else Qt.Unchecked
        self._is_populating = True
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COLUMN_CHECK)
            if item is not None:
                item.setCheckState(target_state)
        self._is_populating = False
        self._header_checked = not self._header_checked

    def _show_context_menu(self, point: QPoint) -> None:
        """右クリックメニューを表示する。"""
        item = self.table.itemAt(point)
        if item is None:
            return

        self.table.selectRow(item.row())
        menu = QMenu(self.table)
        delete_action = QAction("この項目を削除（JSONから除外）", self.table)
        row = item.row()
        delete_action.triggered.connect(lambda: self.remove_row_by_index(row))
        menu.addAction(delete_action)
        menu.exec(self.table.viewport().mapToGlobal(point))

    def _iter_checked_records(self) -> Iterable[AssetRecord]:
        """チェック済み行を AssetRecord として列挙する。"""
        for row in range(self.table.rowCount()):
            check_item = self.table.item(row, self.COLUMN_CHECK)
            if check_item is None or check_item.checkState() != Qt.Checked:
                continue

            path = self._compose_path(row)
            yield AssetRecord(
                path=path,
                genre=self._item_text(row, self.COLUMN_GENRE),
                category=self._compose_category(row),
                url=self._item_text(row, self.COLUMN_URL),
                attribution=self._item_text(row, self.COLUMN_ATTRIBUTION),
                status=self._item_text(row, self.COLUMN_STATUS),
            )

    def _collect_records(self) -> list[AssetRecord]:
        """グリッド全行を AssetRecord の配列へ変換する。"""
        records: list[AssetRecord] = []
        for row in range(self.table.rowCount()):
            records.append(
                AssetRecord(
                    path=self._compose_path(row),
                    genre=self._item_text(row, self.COLUMN_GENRE),
                    category=self._compose_category(row),
                    url=self._item_text(row, self.COLUMN_URL),
                    attribution=self._item_text(row, self.COLUMN_ATTRIBUTION),
                    status=self._item_text(row, self.COLUMN_STATUS),
                )
            )
        return records

    def _compose_path(self, row: int) -> str:
        """行情報から相対パスを構築する。"""
        genre = self._item_text(row, self.COLUMN_GENRE)
        category_name = self._item_text(row, self.COLUMN_CATEGORY)
        file_name = self._item_text(row, self.COLUMN_FILE_NAME)
        if category_name:
            return f"{genre}/{category_name}/{file_name}"
        return f"{genre}/{file_name}"

    def _compose_category(self, row: int) -> str:
        """行情報から category 値を構築する。"""
        genre = self._item_text(row, self.COLUMN_GENRE)
        category_name = self._item_text(row, self.COLUMN_CATEGORY)
        return f"{genre}/{category_name}" if category_name else genre

    def _category_display(self, record: AssetRecord) -> str:
        """category の表示用文字列を返す。"""
        if "/" in record.category:
            return record.category.split("/", maxsplit=1)[1]
        return record.category

    def _item_text(self, row: int, column: int) -> str:
        """指定セル文字列を返す。"""
        item = self.table.item(row, column)
        return "" if item is None else item.text()

    def _build_credit_output(self) -> str:
        """チェック済み行から概要欄用テキストを組み立てる。"""
        credit_lines: list[str] = []
        unfilled_paths: list[str] = []
        nc_ids: list[str] = []
        seen_attributions: set[str] = set()

        for record in self._iter_checked_records():
            url = self._sanitize_markdown_text(record.url.strip())
            attribution = self._sanitize_markdown_text(record.attribution.strip())
            combined = f"{url}\n{attribution}".strip()
            if not combined:
                unfilled_paths.append(record.path)
                continue

            if attribution and attribution not in seen_attributions:
                credit_lines.append(attribution)
                seen_attributions.add(attribution)
            if url:
                credit_lines.append(url)

            for text in (url, attribution):
                for found in self.NC_ID_PATTERN.findall(text):
                    if found not in nc_ids:
                        nc_ids.append(found)

        credit_text = self._collapse_blank_lines("\n".join(credit_lines))
        nc_text = " ".join(nc_ids)
        unfilled_text = "\n".join(unfilled_paths)
        return (
            "【クレジット表記】\n"
            f"{credit_text}\n\n"
            "【ニコニ・コモンズ 親作品登録用ID】\n"
            f"{nc_text}\n\n"
            "【出展確認素材（要確認リスト）】\n"
            f"{unfilled_text}\n"
        )

    def _sanitize_markdown_text(self, text: str) -> str:
        """Markdownリンクをテキスト形式へ置換する。"""
        replaced = self.MARKDOWN_LINK_PATTERN.sub(r"\1 (\2)", text)
        return self._collapse_blank_lines(replaced)

    def _collapse_blank_lines(self, text: str) -> str:
        """連続空行を最大1行に圧縮する。"""
        return self.BLANK_LINE_PATTERN.sub("\n\n", text)

    def _apply_row_style(self, row: int, status: str) -> None:
        """ステータスに応じた行スタイルを適用する。"""
        if status == STATUS_MISSING:
            color = QColor("#d32f2f")
            strikeout = False
        elif status == STATUS_FILE_NOT_FOUND:
            color = QColor("#757575")
            strikeout = True
        else:
            color = self.palette().text().color()
            strikeout = False

        for column in range(self.table.columnCount()):
            item = self.table.item(row, column)
            if item is None:
                continue
            item.setForeground(color)
            font: QFont = item.font()
            font.setStrikeOut(strikeout)
            item.setFont(font)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        """読み取り専用セルを作成する。"""
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        return item

    @staticmethod
    def _editable_item(text: str) -> QTableWidgetItem:
        """編集可能セルを作成する。"""
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        return item
