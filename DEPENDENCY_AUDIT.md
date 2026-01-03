# Dependency Audit Report
**Date:** 2026-01-03
**Project:** MyEntergy-HA Data Collector

## Executive Summary

✅ **Security Status:** No known vulnerabilities detected
✅ **Version Status:** All dependencies are up-to-date
⚠️ **Recommendations:** Add version pinning for reproducibility

---

## Current Dependencies

### Direct Dependencies (requirements.txt)

| Package | Current Version | Status | Purpose |
|---------|----------------|--------|---------|
| DrissionPage | 4.1.1.2 | ✅ Latest | Browser automation for MyEntergy login |
| pydub | 0.25.1 | ✅ Latest | Audio processing for reCAPTCHA solving |
| SpeechRecognition | 3.14.5 | ✅ Latest | Speech-to-text for reCAPTCHA audio |
| requests | 2.32.5 | ✅ Latest | HTTP API calls to MyEntergy |
| python-dotenv | 1.2.1 | ✅ Latest | Environment variable management |
| PyVirtualDisplay | 3.0 | ✅ Latest | Xvfb virtual display for headless mode |
| ha-mqtt-discoverable | 0.23.0 | ✅ Latest | Home Assistant MQTT integration |

### Key Transitive Dependencies

**DrissionPage** pulls in:
- `DownloadKit==2.0.7` - File download utilities
- `DataRecorder==3.6.2` - Data recording (brings openpyxl)
- `click==8.3.1` - CLI framework
- `cssselect==1.3.0` - CSS selector parsing
- `lxml==6.0.2` - HTML/XML parsing
- `psutil==7.2.1` - Process/system utilities
- `tldextract==5.3.1` - TLD extraction
- `websocket-client==1.9.0` - WebSocket support

**ha-mqtt-discoverable** pulls in:
- `paho-mqtt==2.1.0` - MQTT client
- `pydantic==2.12.4` - Data validation (note: 2.12.5 available)

---

## Security Audit

**Tool Used:** pip-audit v2.10.0

**Result:** ✅ **No known vulnerabilities found**

All dependencies have been scanned against the Python Advisory Database with no security issues detected.

---

## Analysis

### 1. Dependency Justification

All dependencies are **necessary and justified**:

- **Browser Automation:** DrissionPage is required for automated login to MyEntergy portal
- **reCAPTCHA Solving:** pydub + SpeechRecognition handle audio CAPTCHA challenges
- **API Communication:** requests handles data fetching from MyEntergy API
- **Configuration:** python-dotenv manages credentials securely
- **Headless Operation:** PyVirtualDisplay enables Xvfb (better than --headless for bot detection)
- **MQTT Publishing:** ha-mqtt-discoverable provides Home Assistant integration

### 2. Version Status

All direct dependencies are at their latest stable versions as of 2026-01-03.

Minor update available:
- pydantic: 2.12.4 → 2.12.5 (transitive dependency via ha-mqtt-discoverable)

### 3. Bloat Analysis

**Total Installed Size:** Moderate (~50MB for Python packages)

**Largest Dependencies:**
- `lxml` - Necessary for HTML parsing in DrissionPage
- `openpyxl` - Pulled by DataRecorder (part of DrissionPage dependency chain)
  - **Potential optimization:** openpyxl is only needed if DrissionPage uses Excel features
  - Not directly used by this project, but removing would require forking DrissionPage

**Verdict:** No significant bloat. All dependencies serve the project's automation needs.

### 4. Missing Best Practices

⚠️ **Version Pinning:** requirements.txt uses unpinned dependencies
- Current: `DrissionPage` (installs any version)
- Recommended: `DrissionPage==4.1.1.2` (reproducible builds)

---

## Recommendations

### 1. Pin All Dependency Versions (HIGH PRIORITY)

**Why:** Ensure reproducible builds and prevent unexpected breakage

**Action:** Replace requirements.txt with pinned versions:

```txt
DrissionPage==4.1.1.2
pydub==0.25.1
SpeechRecognition==3.14.5
requests==2.32.5
python-dotenv==1.2.1
PyVirtualDisplay==3.0
ha-mqtt-discoverable==0.23.0
```

**Benefit:** Eliminates "works on my machine" issues and improves security posture

### 2. Add requirements-dev.txt (MEDIUM PRIORITY)

**Why:** Separate development tools from production dependencies

**Suggested content:**
```txt
pip-audit>=2.10.0  # Security scanning
pytest>=7.4.0      # Testing framework (if adding tests)
ruff>=0.1.0        # Fast Python linter
```

### 3. Set Up Dependabot/Renovate (MEDIUM PRIORITY)

**Why:** Automated dependency updates and security alerts

**Action:** Add `.github/dependabot.yml`:
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

### 4. Document Python Version (LOW PRIORITY)

**Why:** README mentions Python 3.9+ but Dockerfile uses 3.11

**Action:** Add `.python-version` file or update README to specify 3.11

### 5. Consider Dependency Review Workflow (LOW PRIORITY)

**Why:** Catch vulnerable dependencies in PRs

**Action:** Add GitHub Action for automated security checks

---

## Version Update Strategy

### When to Update

**Immediate:**
- Security vulnerabilities (monitor via pip-audit or GitHub Security Alerts)

**Regular (Monthly):**
- Minor/patch version bumps (e.g., 4.1.1 → 4.1.2)
- Review changelogs for bug fixes and improvements

**Cautious (Quarterly):**
- Major version bumps (e.g., 4.x → 5.x)
- Test thoroughly due to potential breaking changes

### Update Process

1. Update single dependency in test environment
2. Run full test suite (consider adding automated tests)
3. Test Docker build
4. Test authentication flow and data collection
5. Update requirements.txt
6. Commit with descriptive message

---

## Docker Considerations

### Current Dockerfile Analysis

**Base Image:** `python:3.11-slim` ✅ Good choice (minimal size)

**System Dependencies:**
- chrome, xvfb, ffmpeg - All necessary for functionality
- wget, gnupg, unzip, curl - Build tools (could be removed in multi-stage build)

**Optimization Opportunity:** Multi-stage build to reduce final image size

**Current layers:**
1. System packages (~200MB)
2. Python dependencies (~50MB)
3. Application code (<1MB)

**Recommendation:** Consider multi-stage build to exclude build tools from final image

---

## Alternative Dependency Considerations

### Could We Replace Any Dependencies?

**DrissionPage:**
- Alternatives: Selenium, Playwright, Puppeteer
- Verdict: ✅ Keep - DrissionPage is lighter and has good CDP support

**pydub + SpeechRecognition:**
- Alternatives: Direct use of speech_recognition with subprocess
- Verdict: ✅ Keep - Current solution is clean and maintainable

**PyVirtualDisplay:**
- Alternatives: --headless flag, playwright's built-in headless
- Verdict: ✅ Keep - Virtual display helps avoid bot detection

**ha-mqtt-discoverable:**
- Alternatives: Direct paho-mqtt usage
- Verdict: ✅ Keep - Home Assistant auto-discovery is valuable

---

## Risk Assessment

| Risk Category | Level | Mitigation |
|--------------|-------|------------|
| Security Vulnerabilities | 🟢 Low | No current issues; enable Dependabot |
| Breaking Changes | 🟡 Medium | Pin versions; test before updating |
| Supply Chain Attack | 🟡 Medium | Use pip hash checking; verify checksums |
| Dependency Abandonment | 🟢 Low | All packages actively maintained |
| License Compliance | 🟢 Low | All dependencies use permissive licenses |

---

## Compliance Check

All dependencies use compatible licenses:
- MIT License: DrissionPage, pydub, python-dotenv, ha-mqtt-discoverable
- BSD License: SpeechRecognition, requests, lxml
- EPL/EDLA: PyVirtualDisplay

✅ **No license conflicts** for private or commercial use

---

## Action Items

- [ ] Pin all dependency versions in requirements.txt
- [ ] Add requirements-dev.txt with development tools
- [ ] Set up Dependabot for automated dependency updates
- [ ] Document Python version requirement (3.11)
- [ ] Consider adding integration tests for dependency functionality
- [ ] Evaluate multi-stage Docker build for smaller images
- [ ] Set up automated security scanning in CI/CD

---

## Monitoring Strategy

**Weekly:**
- Check GitHub Security Advisories

**Monthly:**
- Run `pip-audit` to scan for vulnerabilities
- Review dependency changelogs for updates

**Quarterly:**
- Full dependency review and update cycle
- Re-evaluate dependency choices
- Check for deprecated packages

---

## Conclusion

The MyEntergy-HA project has a **healthy dependency profile**:

✅ All dependencies are necessary and actively maintained
✅ No security vulnerabilities detected
✅ All packages are at latest stable versions
✅ Reasonable total package size

**Main Improvement:** Add version pinning for production stability and reproducibility.

**Overall Grade:** B+ (would be A with version pinning)
