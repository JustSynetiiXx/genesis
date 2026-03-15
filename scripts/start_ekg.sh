#!/bin/bash
# Startet das EKG-Dashboard
cd /home/user/genesis
PYTHONPATH=/home/user/genesis python3 -m host.ekg.web_dashboard --port 8080
