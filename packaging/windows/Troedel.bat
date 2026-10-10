@echo off
rem Starts Troedel with its small window. The window says where to open it,
rem shows the setup code of the first start and how to reach it from a phone.
rem The data lives in the user's folder (Troedel), not next to this file, so
rem a newer version can be unpacked anywhere without moving anything.
cd /d "%~dp0"
start "" "%~dp0python\pythonw.exe" -I -m troedel window %*
