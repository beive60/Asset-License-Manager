# build.ps1
uv run pyinstaller --noconfirm --onedir --windowed --icon="assets\icon\icon.ico" --add-data="assets\icon\icon.ico;assets\icon" --name "AssetLicenseManager" "src\asset_license_manager\main.py"
