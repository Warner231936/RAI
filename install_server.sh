#!/bin/sh
set -e
python3 -m venv venv
. venv/bin/activate
pip install flask
printf '\nServer setup complete. Run with: venv/bin/python sync_server.py\n'
