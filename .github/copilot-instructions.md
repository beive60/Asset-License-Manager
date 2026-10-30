---
title: "GitHub Copilot Instructions for Asset License Manager"
date: 2026-10-20
generator: "Gemini"
tags: [gemini-log, GitHub Copilot, Asset License Manager]
related_files: [docs/design/system_specification.md, pyproject.toml]
description: "Asset License ManagerにおけるGitHub Copilotの利用に関する指針。"
---

## 基本原則 (Core Principles)

1. **仕様の絶対遵守**: 本リポジトリの開発においては `docs/design/system_specification.md` を唯一の正本（Single Source of Truth）とする。コードを生成・修正する前に必ずこのファイルを参照し、仕様に定義されていない機能（推測による拡張）を勝手に実装しないこと。
2. **アーキテクチャの分離**: コードは必ず以下の3層に分割して実装し、密結合を避けること。
  - `core.py`: ファイル走査、JSON永続化、差分検出などのビジネスロジック。UIに依存しないこと。
  - `formatter.py`: 文字列のサニタイズ、正規表現抽出、重複排除などのテキスト出力ロジック。
  - `main.py`: PySide6を用いたGUI構築。ロジックは `core.py` と `formatter.py` を呼び出すのみに留めること。
3. **完全オフライン**: いかなる外部API通信やネットワークリクエストも実装しないこと。
4. **Typingの強制**: Python関数には厳密な型ヒント（Type Hints）を記述すること。
5. **Ruff準拠のコーディング**:
  - 1行の長さは最大120文字とする。
  - 文字列には原則としてダブルクォート (`"`) を使用すること。
  - 未使用の `import` は残さないこと（不要になった場合は削除する）。
  - インポート順序は標準ライブラリ、サードパーティ（PySide6等）、ローカルモジュールの順にソートすること。
6. **googleスタイルの遵守**: Pythonコードは原則としてGoogleのPythonスタイルガイドに従うこと。特に関数やクラスのドキュメンテーション文字列（docstring）はGoogleスタイルで記述すること。docstringは必ず関数やクラスの冒頭に記述し、引数や戻り値の型情報も明示すること。日本語で記述すること。
7. **テストの徹底**: GUI表示に関わる部分を除き、生成されたコードや修正されたコードに対しては、ユニットテストを作成し、動作を検証すること。テストは `pytest` を用いて実装し、テストケースは仕様に基づいて網羅的に記述すること。テストコードもGoogleスタイルに従い、docstringを用いてテストの目的や前提条件を明示すること。

## GUI実装の制約 (PySide6)

- 複雑なカスタムウィジェットは避け、標準の `QTableWidget` などをシンプルに構成すること。
- Excelライクな複数セルへのクリップボード・ペースト処理を実装する際は、データのバリデーション（範囲外エラーの防止）を確実に行うこと。
- データ構造の変更を伴う操作は、必ずシグナルとスロットを用いてUIスレッドとロジックを連携させること。
