"""Notification tool: Windows toast notification via PowerShell."""

from __future__ import annotations

import subprocess


def register(mcp, *, get_display_manager, get_confinement):
    """Register the Notification tool."""

    @mcp.tool(
        name="Notification",
        description="Show a Windows toast notification with a title and message.",
    )
    def notification(title: str, message: str) -> str:
        # Escape single quotes for use inside PowerShell string
        safe_title = title.replace("'", "\\'")
        safe_message = message.replace("'", "\\'")

        ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$APP_ID = 'Microsoft.Windows.Explorer'
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02
)
$template.SelectSingleNode('//text[@id=1]').InnerText = '{safe_title}'
$template.SelectSingleNode('//text[@id=2]').InnerText = '{safe_message}'
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($APP_ID).Show($toast)
"""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0 and result.stderr:
                return f"Notification sent (with warning): {result.stderr.strip()[:200]}"
            return f"Notification sent: '{title}'"
        except subprocess.TimeoutExpired:
            return "Error: notification timed out."
        except Exception as e:
            return f"Error: {e}"
