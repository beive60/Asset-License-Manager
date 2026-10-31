"""Asset License Manager のアプリケーションエントリポイント。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

if __package__ in (None, ""):
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from asset_license_manager.ui import AssetLicenseMainWindow
else:
    from .ui import AssetLicenseMainWindow


def get_resource_path(relative_path: str) -> Path:
    """実行環境（PyInstallerか通常実行か）に応じてリソースの絶対パスを取得する。"""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller実行時（一時フォルダまたは内部ディレクトリ）
        base_path = Path(sys._MEIPASS)
    else:
        # 開発環境実行時（main.py の2階層上がプロジェクトルート）
        base_path = Path(__file__).resolve().parents[2]

    return base_path / relative_path


def main() -> int:
    """アプリケーションを起動する。

    Returns:
        終了コード。
    """
    app = QApplication(sys.argv)

    icon_path = get_resource_path("assets/icon/icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = AssetLicenseMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
