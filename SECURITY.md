# Security Policy

## Supported Versions

AuthorBoard is actively maintained. We provide security updates for the latest stable release. Older versions may not receive patches.

| Version | Supported          |
| ------- | ------------------ |
| 1.2.x   | :white_check_mark: |
| < 1.2.0 | :x:                |

If you are using an unsupported version, please upgrade to the latest release to ensure you have the latest security fixes.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability in AuthorBoard, please report it privately so we can address it before it is publicly disclosed. 

You can report a vulnerability using the **GitHub Private Vulnerability Reporting** feature:
1. Go to the **Security** tab of this repository.
2. Click **Advisories** in the left sidebar.
3. Click **Report a vulnerability**.
4. Fill out the form with the details.

### What to include in your report:
To help us triage the issue quickly, please include:
- A description of the vulnerability.
- Steps to reproduce the issue (Proof of Concept).
- The version of AuthorBoard you are using (found in *Help → About AuthorBoard*).
- Your operating system.
- Any relevant log files or crash dumps (make sure to redact any personal writing data from your notebooks).

### What to expect:
- **Acknowledgment:** We will acknowledge receipt of your vulnerability report within **48 hours**.
- **Assessment:** We will investigate and determine the severity and impact of the vulnerability.
- **Fix:** We will work on a patch and aim to release a security update within **7 to 14 days**, depending on complexity.
- **Credit:** If you wish, we will credit you in the release notes for the patched version.

## Scope

Because AuthorBoard is a **local-first, offline desktop application**, the security scope is specific to how the program interacts with your computer and the internet.

**In Scope:**
- **The Auto-Updater:** Vulnerabilities in the update mechanism (e.g., bypassing SSL/TLS verification, a flaw that allows a malicious actor to execute arbitrary code during an update).
- **File Handling:** Vulnerabilities when opening malicious attachment files or loading a crafted `.json` notebook file that could lead to code execution or path traversal (escaping the `~/.authorboard/` directory).
- **Rich Text / HTML Injection:** Bypasses in the rich-text editor that could lead to script execution (if vulnerable) or unexpected behavior when exporting to HTML.
- **Data Leaks:** Flaws that cause AuthorBoard to unintentionally transmit local notebook data to the internet.

**Out of Scope:**
- Physical access to an unlocked computer.
- Malware already present on the user's system.
- Vulnerabilities in third-party dependencies (e.g., PySide6, pyspellchecker) that do not have a direct, exploitable impact on AuthorBoard specifically. (Please report those to the respective upstream projects).
- Social engineering attacks.

## Security Design Details

For context, here are the security measures AuthorBoard already implements:
- **Update Integrity:** Updates are downloaded over HTTPS (via `curl.exe`). We verify the download completes fully and matches the expected file size. *(Note: Code signing for the Windows executables is planned for a future release).*
- **Local Data:** AuthorBoard does not have a user account system, does not contain telemetry, and does not "phone home." All your writing data is stored locally in `~/.authorboard/`.
- **Links:** The rich-text editor uses a strict allowlist for links (`http`, `https`, `mailto`, `ftp`) to prevent the execution of local files or arbitrary URI schemes.

## Disclosure Policy
We follow a **Coordinated Disclosure** model. We ask that you give us reasonable time to fix the issue before sharing it publicly or with others. We will work with you to agree on a disclosure date once a fix is ready.
