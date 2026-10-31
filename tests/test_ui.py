"""ui モジュールのヘッドレス結合テスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from asset_license_manager.core import STATUS_FILE_NOT_FOUND, STATUS_FILLED, STATUS_MISSING
from asset_license_manager.ui import AssetLicenseMainWindow
from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QAbstractItemView, QApplication, QMessageBox


@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path: Path):
    """各テストでQSettings保存先を隔離する。"""
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / "qsettings"))
    settings = QSettings(
        AssetLicenseMainWindow.SETTINGS_ORG,
        AssetLicenseMainWindow.SETTINGS_APP,
    )
    settings.clear()
    settings.sync()
    yield


def _touch_file(path: Path) -> None:
    """テスト用ファイルを作成する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _prepare_assets_root(tmp_path: Path) -> Path:
    """UIテスト用の素材ルートを作成する。"""
    root = tmp_path / "assets"
    _touch_file(root / "audio" / "bgm" / "missing.mp3")
    _touch_file(root / "audio" / "se" / "filled.wav")

    (root / "audio-assets-license.json").write_text(
        json.dumps(
            {
                "audio/bgm/missing.mp3": {
                    "url": "",
                    "attribution": "",
                    "category": "audio/bgm",
                },
                "audio/se/filled.wav": {
                    "url": "https://example.com/se",
                    "attribution": "",
                    "category": "audio/se",
                },
                "audio/bgm/vanished.mp3": {
                    "url": "https://example.com/vanished",
                    "attribution": "",
                    "category": "audio/bgm",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "picture-assets-license.json").write_text("{}", encoding="utf-8")
    (root / "video-assets-license.json").write_text("{}", encoding="utf-8")
    return root


def _find_row_by_file_name(window: AssetLicenseMainWindow, file_name: str) -> int:
    """ファイル名に対応する行インデックスを返す。"""
    for row in range(window.table.rowCount()):
        item = window.table.item(row, window.COLUMN_FILE_NAME)
        if item is not None and item.text() == file_name:
            return row
    raise AssertionError(f"指定ファイル名の行が見つかりません: {file_name}")


def test_main_window_initializes_with_table_structure(qtbot) -> None:
    """ウィンドウ初期化時に基本UI構造とセル選択モードが生成される。"""
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)

    assert window.table.columnCount() == 7
    assert window.table.horizontalHeaderItem(window.COLUMN_CHECK).text() == ""
    assert window.table.horizontalHeaderItem(window.COLUMN_ATTRIBUTION).text() == "Attribution"
    assert window.table.selectionMode() == QAbstractItemView.ExtendedSelection
    assert window.table.selectionBehavior() == QAbstractItemView.SelectItems
    assert window.table.rowCount() == 0
    assert window.is_dirty is False


def test_set_root_directory_populates_grid_and_clears_dirty(tmp_path: Path, qtbot) -> None:
    """ルート設定時に同期され、グリッドが更新される。"""
    root = _prepare_assets_root(tmp_path)
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)

    window.set_root_directory(root)

    assert window.table.rowCount() == 3
    assert str(root) in window.path_label.text()
    assert window.is_dirty is False


def test_restore_last_root_directory_from_qsettings(tmp_path: Path, qtbot) -> None:
    """起動時に前回素材フォルダを復元し自動同期する。"""
    root = _prepare_assets_root(tmp_path)
    settings = QSettings(
        AssetLicenseMainWindow.SETTINGS_ORG,
        AssetLicenseMainWindow.SETTINGS_APP,
    )
    settings.setValue(AssetLicenseMainWindow.SETTINGS_LAST_ROOT_KEY, str(root))
    settings.sync()

    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)

    assert window.current_root_dir == root
    assert window.table.rowCount() == 3
    assert window.is_dirty is False


def test_editing_url_updates_status_to_filled_and_sets_dirty(tmp_path: Path, qtbot) -> None:
    """URL編集時にステータス更新とDirty化が行われる。"""
    root = _prepare_assets_root(tmp_path)
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)
    window.set_root_directory(root)

    target_row = _find_row_by_file_name(window, "missing.mp3")
    url_item = window.table.item(target_row, window.COLUMN_URL)
    status_item = window.table.item(target_row, window.COLUMN_STATUS)
    assert url_item is not None
    assert status_item is not None
    assert status_item.text() == STATUS_MISSING

    url_item.setText("https://example.com/missing")
    qtbot.waitUntil(lambda: window.table.item(target_row, window.COLUMN_STATUS).text() == STATUS_FILLED)

    assert window.table.item(target_row, window.COLUMN_STATUS).text() == STATUS_FILLED
    assert window.is_dirty is True


def test_prune_file_not_found_removes_rows_and_sets_dirty(tmp_path: Path, qtbot) -> None:
    """一括削除で File not found 行が削除される。"""
    root = _prepare_assets_root(tmp_path)
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)
    window.set_root_directory(root)
    window.is_dirty = False

    window.prune_file_not_found_rows()

    statuses = [window.table.item(row, window.COLUMN_STATUS).text() for row in range(window.table.rowCount())]
    assert STATUS_FILE_NOT_FOUND not in statuses
    assert window.is_dirty is True


def test_remove_selected_rows_from_toolbar_sets_dirty(tmp_path: Path, qtbot) -> None:
    """ツールバー削除で選択行が除外される。"""
    root = _prepare_assets_root(tmp_path)
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)
    window.set_root_directory(root)
    window.is_dirty = False

    target_row = _find_row_by_file_name(window, "filled.wav")
    window.table.selectRow(target_row)
    qtbot.mouseClick(window.delete_selected_button, Qt.LeftButton)

    file_names = [window.table.item(row, window.COLUMN_FILE_NAME).text() for row in range(window.table.rowCount())]
    assert "filled.wav" not in file_names
    assert window.is_dirty is True


def test_generate_credit_text_writes_expected_sections(tmp_path: Path, qtbot, monkeypatch) -> None:
    """テキスト生成で指定フォーマットのファイルが保存される（Markdownサニタイズなし）。"""
    root = _prepare_assets_root(tmp_path)
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)
    window.set_root_directory(root)

    missing_row = _find_row_by_file_name(window, "missing.mp3")
    filled_row = _find_row_by_file_name(window, "filled.wav")
    window.table.item(missing_row, window.COLUMN_CHECK).setCheckState(Qt.Checked)
    window.table.item(filled_row, window.COLUMN_CHECK).setCheckState(Qt.Checked)
    window.table.item(filled_row, window.COLUMN_ATTRIBUTION).setText(
        "[SE素材](https://commons.nicovideo.jp/material/nc12345)"
    )
    window.table.item(filled_row, window.COLUMN_URL).setText("https://example.com/path\\nhttps://example.com/path2")

    output_path = tmp_path / "credit.txt"
    monkeypatch.setattr(
        "asset_license_manager.ui.QFileDialog.getSaveFileName",
        lambda *_a, **_k: (str(output_path), "Text Files (*.txt)"),
    )

    window.generate_credit_text()
    output = output_path.read_text(encoding="utf-8")

    assert "【クレジット表記】" in output
    assert "[SE素材](https://commons.nicovideo.jp/material/nc12345)" in output
    assert "https://example.com/path\nhttps://example.com/path2" in output
    assert "【ニコニ・コモンズ 親作品登録用ID】" in output
    assert "nc12345" in output
    assert "【出展確認素材（要確認リスト）】" in output
    assert "audio/bgm/missing.mp3" in output


def test_copy_selected_cells_stores_tsv_in_clipboard(tmp_path: Path, qtbot) -> None:
    """URLとAttributionの2セルを選択してCtrl+CでTSVコピーできる。"""
    root = _prepare_assets_root(tmp_path)
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)
    window.show()
    window.set_root_directory(root)

    filled_row = _find_row_by_file_name(window, "filled.wav")
    window.table.item(filled_row, window.COLUMN_URL).setText("https://example.com/copied")
    window.table.item(filled_row, window.COLUMN_ATTRIBUTION).setText("Copied Author")

    selection_model = window.table.selectionModel()
    selection_model.clearSelection()
    url_index = window.table.model().index(filled_row, window.COLUMN_URL)
    attr_index = window.table.model().index(filled_row, window.COLUMN_ATTRIBUTION)
    selection_model.select(url_index, QItemSelectionModel.Select)
    selection_model.select(attr_index, QItemSelectionModel.Select)

    QApplication.clipboard().clear()
    copy_event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_C, Qt.ControlModifier)
    window.table.keyPressEvent(copy_event)

    assert QApplication.clipboard().text() == "https://example.com/copied\tCopied Author"


def test_intelligent_paste_repeats_single_row_for_multi_selection(tmp_path: Path, qtbot, monkeypatch) -> None:
    """1行TSVを複数選択行へ繰り返し貼り付けできる。"""
    root = _prepare_assets_root(tmp_path)
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)
    window.show()
    window.set_root_directory(root)

    window.table.setCurrentCell(0, window.COLUMN_URL)
    window.table.setFocus()
    QApplication.clipboard().setText("https://example.com/new\tRepeated Attribution")

    class _Range:
        def topRow(self) -> int:
            return 0

        def bottomRow(self) -> int:
            return 1

        def leftColumn(self) -> int:
            return window.COLUMN_URL

    class _Index:
        def __init__(self, row: int) -> None:
            self._row = row

        def row(self) -> int:
            return self._row

    monkeypatch.setattr(window.table, "selectedRanges", lambda: [_Range()])
    monkeypatch.setattr(window.table, "selectedIndexes", lambda: [_Index(0), _Index(1)])

    window.table._paste_tabular_text()

    assert window.table.item(0, window.COLUMN_URL).text() == "https://example.com/new"
    assert window.table.item(0, window.COLUMN_ATTRIBUTION).text() == "Repeated Attribution"
    assert window.table.item(1, window.COLUMN_URL).text() == "https://example.com/new"
    assert window.table.item(1, window.COLUMN_ATTRIBUTION).text() == "Repeated Attribution"
    assert window.is_dirty is True


def test_close_event_behavior_follows_dirty_state(tmp_path: Path, qtbot, monkeypatch) -> None:
    """終了時確認ダイアログ分岐がDirty状態に応じて機能する。"""
    root = _prepare_assets_root(tmp_path)
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)
    window.set_root_directory(root)

    asked = {"count": 0}

    def should_not_be_called(*_args, **_kwargs):
        asked["count"] += 1
        return QMessageBox.Cancel

    monkeypatch.setattr("asset_license_manager.ui.QMessageBox.question", should_not_be_called)
    window.is_dirty = False
    clean_event = QCloseEvent()
    window.closeEvent(clean_event)
    assert clean_event.isAccepted() is True
    assert asked["count"] == 0

    monkeypatch.setattr("asset_license_manager.ui.QMessageBox.question", lambda *_a, **_k: QMessageBox.Cancel)
    window.is_dirty = True
    cancel_event = QCloseEvent()
    window.closeEvent(cancel_event)
    assert cancel_event.isAccepted() is False

    called = {"saved": False}

    def mark_saved() -> None:
        called["saved"] = True
        window.is_dirty = False

    monkeypatch.setattr(window, "save_current_records", mark_saved)
    monkeypatch.setattr("asset_license_manager.ui.QMessageBox.question", lambda *_a, **_k: QMessageBox.Yes)
    yes_event = QCloseEvent()
    window.is_dirty = True
    window.closeEvent(yes_event)

    assert yes_event.isAccepted() is True
    assert called["saved"] is True
