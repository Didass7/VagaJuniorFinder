run:
	python main.py

test:
	python -m pytest tests/ -v

lint:
	ruff check .

format:
	ruff format .
