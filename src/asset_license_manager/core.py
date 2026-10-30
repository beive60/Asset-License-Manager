"""素材ライセンス管理のコアロジックを提供するモジュール。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


ASSET_JSON_FILES: dict[str, str] = {
    "audio": "audio-assets-license.json",
    "picture": "picture-assets-license.json",
    "video": "video-assets-license.json",
}

REQUIRED_CATEGORY_DIRECTORIES: dict[str, tuple[str, ...]] = {
    "audio": ("bgm", "se"),
    "picture": ("background", "character", "item"),
    "video": ("background", "effect", "transition"),
}

SCAN_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "audio": (".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"),
    "picture": (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"),
    "video": (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".wmv", ".flv", ".mpeg", ".mpg"),
}

STATUS_MISSING = "Missing"
STATUS_FILLED = "Filled"
STATUS_FILE_NOT_FOUND = "File not found"


@dataclass(frozen=True)
class AssetRecord:
    """同期後の素材1件分の情報を表す。"""

    path: str
    genre: str
    category: str
    url: str
    attribution: str
    status: str


@dataclass(frozen=True)
class SyncDiff:
    """同期結果の差分集合を表す。"""

    missing: tuple[AssetRecord, ...]
    filled: tuple[AssetRecord, ...]
    file_not_found: tuple[AssetRecord, ...]


@dataclass(frozen=True)
class SyncResult:
    """同期処理の結果を表す。"""

    records: tuple[AssetRecord, ...]
    diff: SyncDiff


class AssetLicenseCore:
    """素材ルート走査・JSON永続化・同期差分抽出を提供するクラス。"""

    def __init__(self, root_dir: str | Path) -> None:
        """初期化する。

        Args:
            root_dir: 素材ルートディレクトリ。
        """
        self.root_dir = Path(root_dir)

    def ensure_required_directories(self) -> None:
        """必須ディレクトリ構造を作成する。"""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        for genre, categories in REQUIRED_CATEGORY_DIRECTORIES.items():
            for category in categories:
                (self.root_dir / genre / category).mkdir(parents=True, exist_ok=True)

    def scan_asset_files(self) -> dict[str, set[str]]:
        """素材ルートを走査して対象ファイルを収集する。

        Returns:
            ジャンルごとの正規化済み相対パス集合。
        """
        self.ensure_required_directories()
        scanned: dict[str, set[str]] = {genre: set() for genre in ASSET_JSON_FILES}

        for genre, extensions in SCAN_EXTENSIONS.items():
            genre_root = self.root_dir / genre
            if not genre_root.exists():
                continue

            for path in genre_root.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in extensions:
                    continue
                normalized = self._normalize_relative_path(path)
                scanned[genre].add(normalized)

        return scanned

    def load_genre_json(self, genre: str) -> dict[str, dict[str, str]]:
        """ジャンルJSONを読み込む。

        Args:
            genre: 対象ジャンル。

        Returns:
            ファイルパスをキーとする辞書。
        """
        json_path = self._get_json_path(genre)
        if not json_path.exists():
            self.save_genre_json(genre, {})
            return {}

        with json_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(f"JSONのルートは辞書型である必要があります: {json_path}")

        normalized_data: dict[str, dict[str, str]] = {}
        for key, value in data.items():
            if not isinstance(key, str):
                raise ValueError(f"JSONキーは文字列である必要があります: {json_path}")
            if not isinstance(value, dict):
                raise ValueError(f"JSON値は辞書型である必要があります: {json_path}")

            url = self._as_str(value.get("url", ""))
            attribution = self._as_str(value.get("attribution", ""))
            category = self._as_str(value.get("category", self._derive_category_from_path(key)))
            normalized_data[key] = {
                "url": url,
                "attribution": attribution,
                "category": category,
            }

        return normalized_data

    def save_genre_json(self, genre: str, data: dict[str, dict[str, str]]) -> None:
        """ジャンルJSONを保存する。

        Args:
            genre: 対象ジャンル。
            data: 保存データ。
        """
        json_path = self._get_json_path(genre)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with json_path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")

    def synchronize(self) -> SyncResult:
        """ファイル走査とJSONを突き合わせて同期結果を作成する。

        Returns:
            同期結果。
        """
        scanned = self.scan_asset_files()
        records: list[AssetRecord] = []

        for genre in ASSET_JSON_FILES:
            json_data = self.load_genre_json(genre)
            scanned_paths = scanned[genre]
            merged_paths = sorted(scanned_paths | set(json_data.keys()))
            for path in merged_paths:
                entry = json_data.get(path, {})
                url = self._as_str(entry.get("url", ""))
                attribution = self._as_str(entry.get("attribution", ""))
                category = self._as_str(entry.get("category", self._derive_category_from_path(path)))
                exists_in_scan = path in scanned_paths
                if not exists_in_scan:
                    status = STATUS_FILE_NOT_FOUND
                elif url.strip() or attribution.strip():
                    status = STATUS_FILLED
                else:
                    status = STATUS_MISSING

                records.append(
                    AssetRecord(
                        path=path,
                        genre=genre,
                        category=category,
                        url=url,
                        attribution=attribution,
                        status=status,
                    )
                )

        records = sorted(records, key=lambda record: record.path)
        return SyncResult(records=tuple(records), diff=self.extract_diff(records))

    def extract_diff(self, records: list[AssetRecord] | tuple[AssetRecord, ...]) -> SyncDiff:
        """同期レコードをステータスごとの差分へ分解する。

        Args:
            records: 同期レコード列。

        Returns:
            ステータス別差分。
        """
        missing: list[AssetRecord] = []
        filled: list[AssetRecord] = []
        file_not_found: list[AssetRecord] = []

        for record in records:
            if record.status == STATUS_MISSING:
                missing.append(record)
            elif record.status == STATUS_FILLED:
                filled.append(record)
            elif record.status == STATUS_FILE_NOT_FOUND:
                file_not_found.append(record)

        return SyncDiff(
            missing=tuple(missing),
            filled=tuple(filled),
            file_not_found=tuple(file_not_found),
        )

    def save_records(self, records: list[AssetRecord] | tuple[AssetRecord, ...]) -> None:
        """レコード一覧をジャンル別JSONへ保存する。

        Args:
            records: 保存対象レコード。
        """
        grouped: dict[str, dict[str, dict[str, str]]] = {genre: {} for genre in ASSET_JSON_FILES}
        for record in records:
            if record.genre not in grouped:
                raise ValueError(f"未知のジャンルです: {record.genre}")
            grouped[record.genre][record.path] = {
                "url": record.url,
                "attribution": record.attribution,
                "category": record.category,
            }

        for genre, data in grouped.items():
            self.save_genre_json(genre, data)

    def _get_json_path(self, genre: str) -> Path:
        """ジャンルに対応するJSONファイルパスを返す。"""
        if genre not in ASSET_JSON_FILES:
            raise ValueError(f"未知のジャンルです: {genre}")
        return self.root_dir / ASSET_JSON_FILES[genre]

    def _normalize_relative_path(self, path: Path) -> str:
        """素材ルートからの正規化相対パスを返す。"""
        return path.relative_to(self.root_dir).as_posix()

    def _derive_category_from_path(self, relative_path: str) -> str:
        """相対パスから category 値を導出する。"""
        path = Path(relative_path)
        parent = path.parent.as_posix()
        return "" if parent == "." else parent

    @staticmethod
    def _as_str(value: Any) -> str:
        """任意値を文字列へ正規化する。"""
        return value if isinstance(value, str) else ""
