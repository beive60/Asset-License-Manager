"""core モジュールの単体テスト。"""

from __future__ import annotations

import json
from pathlib import Path

from asset_license_manager.core import (
    AssetLicenseCore,
    AssetRecord,
    STATUS_FILE_NOT_FOUND,
    STATUS_FILLED,
    STATUS_MISSING,
)


def _touch_file(path: Path) -> None:
    """テスト用の空ファイルを作成する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_scan_asset_files_creates_required_directories_and_filters_extensions(
    tmp_path: Path,
) -> None:
    """走査時に必須ディレクトリを生成し、対象拡張子のみ収集する。"""
    root = tmp_path / "assets"
    _touch_file(root / "audio" / "bgm" / "track.MP3")
    _touch_file(root / "audio" / "bgm" / "memo.txt")
    _touch_file(root / "picture" / "item" / "item01.png")
    _touch_file(root / "video" / "effect" / "effect01.mkv")

    core = AssetLicenseCore(root)
    scanned = core.scan_asset_files()

    assert "audio/bgm/track.MP3" in scanned["audio"]
    assert "audio/bgm/memo.txt" not in scanned["audio"]
    assert "picture/item/item01.png" in scanned["picture"]
    assert "video/effect/effect01.mkv" in scanned["video"]
    assert (root / "audio" / "se").exists()
    assert (root / "picture" / "character").exists()
    assert (root / "video" / "transition").exists()


def test_load_genre_json_creates_empty_file_when_missing(tmp_path: Path) -> None:
    """JSONファイルが無い場合は初期化して空辞書を返す。"""
    root = tmp_path / "assets"
    root.mkdir(parents=True)
    core = AssetLicenseCore(root)

    data = core.load_genre_json("audio")

    assert data == {}
    json_path = root / "audio-assets-license.json"
    assert json_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8")) == {}


def test_synchronize_detects_missing_filled_and_file_not_found(tmp_path: Path) -> None:
    """同期処理がステータスと差分を正しく判定する。"""
    root = tmp_path / "assets"
    _touch_file(root / "audio" / "bgm" / "new_track.mp3")
    _touch_file(root / "audio" / "se" / "filled.wav")
    _touch_file(root / "picture" / "background" / "bg.jpg")

    (root / "audio-assets-license.json").write_text(
        json.dumps(
            {
                "audio/se/filled.wav": {
                    "url": "",
                    "attribution": "SE by Author",
                    "category": "audio/se",
                },
                "audio/bgm/old_track.mp3": {
                    "url": "https://example.com/old",
                    "attribution": "",
                    "category": "audio/bgm",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "picture-assets-license.json").write_text(
        json.dumps(
            {
                "picture/background/bg.jpg": {
                    "url": "",
                    "attribution": "",
                    "category": "picture/background",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "video-assets-license.json").write_text("{}", encoding="utf-8")

    core = AssetLicenseCore(root)
    result = core.synchronize()
    status_by_path = {record.path: record.status for record in result.records}

    assert status_by_path["audio/bgm/new_track.mp3"] == STATUS_MISSING
    assert status_by_path["audio/se/filled.wav"] == STATUS_FILLED
    assert status_by_path["audio/bgm/old_track.mp3"] == STATUS_FILE_NOT_FOUND
    assert status_by_path["picture/background/bg.jpg"] == STATUS_MISSING

    assert {record.path for record in result.diff.missing} == {
        "audio/bgm/new_track.mp3",
        "picture/background/bg.jpg",
    }
    assert {record.path for record in result.diff.filled} == {"audio/se/filled.wav"}
    assert {record.path for record in result.diff.file_not_found} == {"audio/bgm/old_track.mp3"}


def test_save_records_splits_json_by_genre(tmp_path: Path) -> None:
    """保存時にジャンル別JSONへ正しく書き分ける。"""
    root = tmp_path / "assets"
    root.mkdir(parents=True)
    core = AssetLicenseCore(root)
    records = [
        AssetRecord(
            path="audio/bgm/theme.mp3",
            genre="audio",
            category="audio/bgm",
            url="https://example.com/theme",
            attribution="Theme by Composer",
            status=STATUS_FILLED,
        ),
        AssetRecord(
            path="picture/item/sword.png",
            genre="picture",
            category="picture/item",
            url="",
            attribution="",
            status=STATUS_MISSING,
        ),
    ]

    core.save_records(records)

    audio_data = json.loads((root / "audio-assets-license.json").read_text(encoding="utf-8"))
    picture_data = json.loads((root / "picture-assets-license.json").read_text(encoding="utf-8"))
    video_data = json.loads((root / "video-assets-license.json").read_text(encoding="utf-8"))

    assert audio_data == {
        "audio/bgm/theme.mp3": {
            "url": "https://example.com/theme",
            "attribution": "Theme by Composer",
            "category": "audio/bgm",
        }
    }
    assert picture_data == {
        "picture/item/sword.png": {
            "url": "",
            "attribution": "",
            "category": "picture/item",
        }
    }
    assert video_data == {}