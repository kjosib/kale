@echo off
rem This is a simple helper script for Windows to make it easier to run the
rem examples from the command line.

rem For example, try typing "demo intro".

setlocal
set PYTHONPATH=%PYTHONPATH%;.\src
echo Press Control-Break to Quit the (localhost-only) server.
start py -m examples.%1
