# Building Generation Two

This document explains how to build Generation Two for different platforms.

## Prerequisites

### All Platforms
- Python 3.8 or higher
- pip
- setuptools, wheel

### Windows (for EXE)
- PyInstaller: `pip install pyinstaller`

### Linux (for DEB)
- stdeb: `pip install stdeb`
- dpkg-deb (usually pre-installed on Debian/Ubuntu)

### macOS (for DMG)
- PyInstaller: `pip install pyinstaller`
- create-dmg: `brew install create-dmg`

## Building

### Quick Build (Auto-detect platform)
```bash
cd generation_two
python build.py
```

### Build Specific Formats

#### Windows EXE
```bash
python build.py --exe
```

#### Linux DEB
```bash
python build.py --deb
```

#### macOS DMG
```bash
python build.py --dmg
```

#### Build All Formats
```bash
python build.py --all
```

## Output

All built packages will be in the `dist/` directory:
- `generation-two.exe` (Windows)
- `generation-two_*.deb` (Linux)
- `generation-two.dmg` (macOS)

## Notes

1. **Credentials**: The built executables will NOT include any credentials. Users must provide their own `credential.txt` file.

2. **Dependencies**: All Python dependencies are bundled with the executable.

3. **Icons**: To add custom icons, modify the `build.py` script and add icon paths.

4. **Cross-platform building**: 
   - Windows EXE can be built on Windows
   - Linux DEB can be built on Linux
   - macOS DMG can be built on macOS
   - For cross-platform builds, use Docker or CI/CD

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Build

on: [push, release]

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: cd generation_two && python build.py --exe
  
  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: cd generation_two && python build.py --deb
  
  build-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: cd generation_two && python build.py --dmg
```
