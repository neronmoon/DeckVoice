DECK_HOST ?= 192.168.1.216
DECK_USER ?= deck
DECK_PLUGIN ?= /home/deck/homebrew/plugins/DeckVoice
PYTHON ?= $(CURDIR)/.venv/bin/python
ARTIFACT_DIR ?= /tmp/deckvoice-ci
STAGING ?= /tmp/deckvoice-plugin

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
		-e HOST_UID=$(shell id -u) \
		-e HOST_GID=$(shell id -g) \
		-v "$(CURDIR)/bin:/backend/out" \
		deckvoice-backend

artifact:
	rm -rf $(ARTIFACT_DIR)
	mkdir -p $(ARTIFACT_DIR)
	gh run download -n DeckVoice -D $(ARTIFACT_DIR)

deploy: test artifact
	rm -rf $(STAGING)
	mkdir -p $(STAGING)
	unzip -qo "$(ARTIFACT_DIR)"/*.zip -d $(STAGING)
	src=$(STAGING); \
	if [ -f $(STAGING)/DeckVoice/plugin.json ]; then src=$(STAGING)/DeckVoice; \
	elif [ ! -f $(STAGING)/plugin.json ]; then echo "no plugin.json in artifact" >&2; exit 1; fi; \
	rsync -a --exclude __pycache__ deckvoice/ "$$src/deckvoice/"; \
	mkdir -p "$$src/dist"; \
	rsync -a dist/ "$$src/dist/"; \
	ssh $(DECK_USER)@$(DECK_HOST) 'sudo mkdir -p $(DECK_PLUGIN)'; \
	rsync -rlvz --delete --rsync-path="sudo rsync" --exclude models \
		"$$src"/ $(DECK_USER)@$(DECK_HOST):$(DECK_PLUGIN)/; \
	ssh $(DECK_USER)@$(DECK_HOST) 'sudo systemctl restart plugin_loader'

restart:
	ssh $(DECK_USER)@$(DECK_HOST) 'sudo systemctl restart plugin_loader'

logs:
	ssh $(DECK_USER)@$(DECK_HOST) 'tail -f /tmp/deckvoice.log ~/homebrew/logs/DeckVoice/* 2>/dev/null'
