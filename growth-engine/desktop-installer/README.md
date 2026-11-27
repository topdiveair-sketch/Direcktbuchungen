# Growth Cockpit Desktop Installer

Windows one-click launcher for the deployed Growth Cockpit.

## Installation

1. Download this folder or the release ZIP.
2. Double-click `INSTALL_GROWTH_COCKPIT.cmd`.
3. The installer creates `Growth Cockpit` shortcuts on the Desktop and in the Start menu and launches the cockpit in browser app mode.
4. Enter the existing `ADMIN_TOKEN` in the cockpit when requested.

The installer contains no ADMIN_TOKEN, API token, partner data, or other credentials.

## Uninstall

Run `%LOCALAPPDATA%\GrowthCockpit\Uninstall.ps1` with PowerShell.

## Requirements

Windows 10/11 with PowerShell. Microsoft Edge is preferred for app mode; Chrome is used as fallback; otherwise the default browser opens the cockpit.
