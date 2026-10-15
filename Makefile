# AXK capstone: one command per task. Run `make help`.
SHELL := /bin/bash
export PATH := /opt/homebrew/opt/rustup/bin:$(HOME)/.cargo/bin:$(HOME)/.venvs/bench/bin:/opt/homebrew/opt/python@3.11/bin:/opt/homebrew/opt/mariadb@10.11/bin:/opt/homebrew/bin:$(PATH)

BENCH ?= $(HOME)/Documents/axk-bench
SITE  ?= axk.localhost
SEED  ?= $(CURDIR)/axk_seed/data

.PHONY: help toolchain test test-contracts test-python build demo run run-frappe seed seed-purge install-app contracts-config zip

help:            ## list tasks
	@grep -E "^[a-z-]+:.*## " $(MAKEFILE_LIST) | sed -E "s/:.*## /\t/" | column -t -s "$$(printf "\t")"

toolchain:       ## install Rust, the wasm target and stellar-cli (macOS, Homebrew)
	brew install rustup stellar-cli
	rustup default stable
	rustup target add wasm32v1-none

test:            ## run both contract tests (65) and python integration tests (7)
	cd contracts && cargo test
	python3 scripts/test_trade.py

test-contracts:  ## run all 65 smart contract unit tests
	cd contracts && cargo test

test-python:     ## run end-to-end integration and failure-mode test suite
	python3 scripts/test_trade.py

build:           ## build the four contracts to wasm
	cd contracts && stellar contract build

demo:            ## deploy fresh contracts and run one verified trade on Stellar testnet
	./scripts/demo.sh

contracts-config: ## point the Frappe site at the contracts from the last demo run
	@source scripts/.demo-state.env && cd $(BENCH) && bench --site $(SITE) set-config --parse axk_stellar \
	  "{\"network\":\"testnet\",\"registry\":\"$$REGISTRY\",\"escrow\":\"$$ESCROW\",\"splitter\":\"$$SPLITTER\",\"attestation\":\"$$ATTEST\",\"token\":\"$$TOKEN\",\"stellar_bin\":\"$$(command -v stellar)\"}"

install-app:     ## link the axk_capstone Frappe app into the bench and install it on the site
	ln -sfn $(CURDIR)/frappe_app/axk_capstone $(BENCH)/apps/axk_capstone
	$(BENCH)/env/bin/pip install -q -e $(BENCH)/apps/axk_capstone
	grep -qx axk_capstone $(BENCH)/sites/apps.txt || echo axk_capstone >> $(BENCH)/sites/apps.txt
	cd $(BENCH) && bench --site $(SITE) install-app axk_capstone && bench build --app axk_capstone

seed:            ## import the synthetic five-year dataset into the site
	cp axk_seed/import_to_axk_network.py $(BENCH)/apps/axk_network/axk_network/capstone_seed.py
	cd $(BENCH) && bench --site $(SITE) execute axk_network.capstone_seed.run --kwargs "{'path': '$(SEED)'}"

seed-purge:      ## remove only the synthetic seed rows
	cd $(BENCH) && bench --site $(SITE) execute axk_network.capstone_seed.run --kwargs "{'path': '$(SEED)', 'purge': True}"

run:             ## offline UI simulation, no blockchain (Python only, http://localhost:8000)
	python3 scripts/server.py

run-frappe:      ## full stack on Stellar testnet (http://localhost:8000)
	./scripts/run-frappe.sh

record-demo:     ## generate the full 1080p narrated walkthrough demo video
	python3 scripts/record_demo.py

zip:             ## package the repository for submission (tracked files only)
	git archive --format=zip --prefix=axk-capstone/ -o axk-capstone-submission.zip HEAD
	@ls -lh axk-capstone-submission.zip
