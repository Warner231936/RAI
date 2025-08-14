#!/bin/sh
set -e
python3 -m venv venv
. venv/bin/activate
pip install requests
printf '\nClient setup complete. Run with: venv/bin/python ticket_gui.py\n'
