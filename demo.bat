@echo off
SETLOCAL

IF "%1"=="-" (
	set PYTHONPATH=%PYTHONPATH%;.\src
	echo Press Control-Break to Quit the ^(localhost-only^) server.
	py -m examples.%2
) ELSE IF "%1"=="" (
	echo This is a simple helper script for Windows to make it easier to run the
	echo examples from the command line. Known examples are:
	echo.
	dir /B examples\*.py
	echo.
	echo For example, try typing "demo intro". And then read the example source
	echo to learn the ropes.
) ELSE (
	demo - %1 < nul
)


