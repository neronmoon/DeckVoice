DECK_HOST ?= 192.168.1.216
DECK_USER ?= deck
DECK_PLUGIN ?= /home/deck/homebrew/plugins/DeckVoice
PYTHON ?= $(CURDIR)/.venv/bin/python

.PHONY: test deploy logs restart frontend bin artifact venv

venv:
	test -x $(PYTHON) || python3 -m venv .venv
	$(PYTHON) -m pip install -q pytest

test: venv
	$(PYTHON) -m pytest tests/ -q

frontend:
	npm run build

bin:
	docker build --platform=linux/amd64 -t deckvoice-backend ./backend
	mkdir -p bin
	docker run --rm --platform=linux/amd64 \
		-v "$(CURDIR)/backend:/backend" \
		-v "$(CURDIR)/bin:/backend/out" \
		deckvoice-backend
	chmod +x bin/whisper-server bin/ydotool bin/ydotoold

artifact:
	rm -rf /tmp/deckvoice-ci
	mkdir -p /tmp/deckvoice-ci
	gh run download --name DeckVoice --dir /tmp/deckvoice-ci
	unzip -l /tmp/deckvoice-ci/*.zip

deploy: test
	ssh $(DECK_USER)@$(DECK_HOST) 'sudo mkdir -p $(DECK_PLUGIN) && sudo chown -R $(DECK_USER):$(DECK_USER) $(DECK_PLUGIN)'
	rsync -rlvz --delete \
		--exclude node_modules \
		--exclude .git \
		--exclude .venv \
		--exclude __pycache__ \
		--exclude .pytest_cache \
		--exclude models \
		./ $(DECK_USER)@$(DECK_HOST):$(DECK_PLUGIN)/
	ssh $(DECK_USER)@$(DECK_HOST) 'sudo systemctl restart plugin_loader'

restart:
	ssh $(DECK_USER)@$(DECK_HOST) 'sudo systemctl restart plugin_loader'

logs:
	ssh $(DECK_USER)@$(DECK_HOST) 'tail -f /tmp/deckvoice.log ~/homebrew/logs/DeckVoice/* 2>/dev/null'
