"""ui モジュールのヘッドレス結合テスト。"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from asset_license_manager.core import STATUS_FILE_NOT_FOUND, STATUS_FILLED, STATUS_MISSING
from asset_license_manager.ui import AssetLicenseMainWindow


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
    """ウィンドウ初期化時に基本UI構造が生成される。"""
    window = AssetLicenseMainWindow()
    qtbot.addWidget(window)

    assert window.table.columnCount() == 7
    assert window.table.horizontalHeaderItem(window.COLUMN_CHECK).text() == "[選]"
    assert window.table.horizontalHeaderItem(window.COLUMN_ATTRIBUTION).text() == "Attribution"
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

    statuses = [
        window.table.item(row, window.COLUMN_STATUS).text()
        for row in range(window.table.rowCount())
    ]
    assert STATUS_FILE_NOT_FOUND not in statuses
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
