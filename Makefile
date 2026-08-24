.PHONY: demo test test-python test-workbench workbench

demo:
	PYTHONPATH=src python3 -m personal_ai_os demo

test: test-python test-workbench

test-python:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v

test-workbench:
	node --test tests/*workbench*_test.js

workbench:
	python3 -m http.server 8787 --directory workbench
