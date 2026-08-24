.PHONY: demo test

demo:
	PYTHONPATH=src python3 -m personal_ai_os demo

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
