@echo off
title Mythic 3.0 Quiz Server

cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"