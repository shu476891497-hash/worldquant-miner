# Release Checklist

## Pre-Release Security Check

### ✅ Credentials & Secrets
- [ ] Verify `.gitignore` includes all credential files:
  - `credential.txt`
  - `credentials.txt`
  - `credential.json`
  - `credentials.json`
  - `*.pem`
  - `*.key`
  - `.env`
- [ ] Check for hardcoded credentials in code (grep for: password=, api_key=, token=)
- [ ] Verify no credentials are in version control history
- [ ] Ensure `credential.example.txt` exists as template (without real credentials)

### ✅ Code Quality
- [ ] All tests pass
- [ ] No syntax errors
- [ ] Code follows style guidelines
- [ ] Documentation is up to date

### ✅ Dependencies
- [ ] `requirements.txt` is up to date
- [ ] All dependencies are pinned to specific versions
- [ ] No development dependencies in production build

### ✅ Build Configuration
- [ ] `setup.py` is configured correctly
- [ ] `pyproject.toml` is configured correctly
- [ ] `build.py` works on target platforms
- [ ] Build scripts don't include credentials

## Building Releases

### Windows (EXE)
```bash
cd generation_two
python build.py --exe
```
Output: `dist/generation-two.exe`

### Linux (DEB)
```bash
cd generation_two
python build.py --deb
```
Output: `dist/generation-two_*.deb`

### macOS (DMG)
```bash
cd generation_two
python build.py --dmg
```
Output: `dist/generation-two.dmg`

## Post-Build Verification

- [ ] Test executable on clean system (no Python installed)
- [ ] Verify GUI launches correctly
- [ ] Verify authentication works (prompts for credentials)
- [ ] Verify no credentials are bundled
- [ ] Test core functionality (template generation, simulation)

## Release Notes

Create `RELEASE_NOTES.md` with:
- Version number
- New features
- Bug fixes
- Breaking changes
- Installation instructions
- Known issues

## GitHub Release

1. Create git tag: `git tag -a v1.0.0 -m "Release v1.0.0"`
2. Push tag: `git push origin v1.0.0`
3. Create GitHub release:
   - Upload all three build artifacts (exe, deb, dmg)
   - Include release notes
   - Mark as latest release
