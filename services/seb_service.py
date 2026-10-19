"""Service for Safe Exam Browser (SEB) configuration generation and verification."""
import hashlib
from typing import Optional
from xml.sax.saxutils import escape

from flask import current_app, request


# Runtime in-memory toggle override (takes precedence if explicitly set by admin)
_RUNTIME_SEB_ENFORCED: Optional[bool] = None


def is_seb_user_agent(user_agent: str) -> bool:
    """Check if the User-Agent header string indicates Safe Exam Browser."""
    if not user_agent:
        return False
    ua_upper = user_agent.upper()
    return "SEB" in ua_upper or "SAFEEXAMBROWSER" in ua_upper


def is_seb_request(req=None) -> bool:
    """Determine whether the incoming request originates from Safe Exam Browser."""
    if req is None:
        req = request
    ua = req.headers.get("User-Agent", "")
    if is_seb_user_agent(ua):
        return True
    # Safe Exam Browser can also pass specific header keys
    if req.headers.get("X-SafeExamBrowser-RequestHash") or req.headers.get("X-SafeExamBrowser-ConfigKeyHash"):
        return True
    return False


def is_seb_enforced() -> bool:
    """Check if Safe Exam Browser is currently strictly enforced for participants."""
    global _RUNTIME_SEB_ENFORCED
    if _RUNTIME_SEB_ENFORCED is not None:
        return _RUNTIME_SEB_ENFORCED
    try:
        return bool(current_app.config.get("SEB_ENFORCED", False))
    except RuntimeError:
        return False


def set_seb_enforced(enforced: bool) -> None:
    """Set the runtime enforcement state for Safe Exam Browser."""
    global _RUNTIME_SEB_ENFORCED
    _RUNTIME_SEB_ENFORCED = bool(enforced)


def reset_seb_runtime_toggle() -> None:
    """Reset the runtime toggle back to the config default."""
    global _RUNTIME_SEB_ENFORCED
    _RUNTIME_SEB_ENFORCED = None


def build_seb_plist(
    start_url: str,
    quit_url: Optional[str] = None,
    quit_password: Optional[str] = None,
    allow_reload: bool = True,
) -> str:
    """
    Generate an unencrypted XML Property List (.seb configuration file)
    tailored for locking down student workstations during online exams.
    """
    safe_start_url = escape(start_url.strip())
    safe_quit_url = escape((quit_url or start_url).strip())

    quit_password_xml = ""
    if quit_password:
        hashed_quit = hashlib.sha256(quit_password.encode("utf-8")).hexdigest()
        quit_password_xml = f"""    <key>hashedQuitPassword</key>
    <string>{hashed_quit}</string>"""

    reload_str = "<true/>" if allow_reload else "<false/>"

    plist_content = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>originatorVersion</key>
    <string>SEB_Win_3.4.0</string>
    <key>startURL</key>
    <string>{safe_start_url}</string>
    <key>allowQuit</key>
    <true/>
    <key>quitURL</key>
    <string>{safe_quit_url}</string>
    <key>quitURLConfirm</key>
    <true/>
{quit_password_xml}
    <key>allowPreferencesWindow</key>
    <false/>
    <key>browserWindowAllowReload</key>
    {reload_str}
    <key>showTaskBar</key>
    <true/>
    <key>showReloadButton</key>
    {reload_str}
    <key>showTime</key>
    <true/>
    <key>showInputLanguage</key>
    <false/>
    <key>allowWlan</key>
    <false/>
    <key>allowSpellCheck</key>
    <false/>
    <key>enableAltEsc</key>
    <false/>
    <key>enableAltF4</key>
    <false/>
    <key>enableAltTab</key>
    <false/>
    <key>enableCtrlEsc</key>
    <false/>
    <key>enableEsc</key>
    <false/>
    <key>enableStartMenu</key>
    <false/>
    <key>enableRightMouse</key>
    <false/>
    <key>enablePrintScreen</key>
    <false/>
    <key>browserViewMode</key>
    <integer>0</integer>
    <key>browserWindowWidth</key>
    <string>100%</string>
    <key>browserWindowHeight</key>
    <string>100%</string>
    <key>mainBrowserWindowWidth</key>
    <string>100%</string>
    <key>mainBrowserWindowHeight</key>
    <string>100%</string>
    <key>mainBrowserWindowPositioning</key>
    <integer>1</integer>
    <key>enableDeveloperConsole</key>
    <false/>
    <key>allowFlashFullscreen</key>
    <false/>
    <key>openUrlInNewWindow</key>
    <integer>0</integer>
    <key>hookKeys</key>
    <true/>
    <key>allowVirtualMachine</key>
    <true/>
    <key>kioskMode</key>
    <integer>1</integer>
</dict>
</plist>
"""
    return plist_content
