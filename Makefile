.PHONY: help setup

help:
    @echo "Available targets: help, setup"

setup:
    @echo "Setup: initialize data directories and permissions"
    @chmod +x scripts/init_data.sh || true
    @bash scripts/init_data.sh
    @echo "Setup complete. If running under Docker, ensure host ownership: sudo chown -R 1000:1000 data"
