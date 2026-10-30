"""Asset License Manager のアプリケーションエントリポイント。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

if __package__ in (None, ""):
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from asset_license_manager.ui import AssetLicenseMainWindow
else:
    from .ui import AssetLicenseMainWindow


def main() -> int:
    """アプリケーションを起動する。

    Returns:
        終了コード。
    """
    app = QApplication(sys.argv)
    window = AssetLicenseMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())