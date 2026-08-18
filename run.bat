@echo off
REM Convenience wrapper so you can double-click to launch instead of
REM opening PowerShell yourself. -ExecutionPolicy Bypass here only affects
REM this one launched process, not your system's PowerShell policy -- it
REM does not change any permanent setting.
REM
REM All the actual logic lives in run.ps1, kept in one place rather than
REM duplicated in batch syntax where the two could drift out of sync.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
