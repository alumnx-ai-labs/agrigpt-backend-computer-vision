#!/bin/bash
cd /home/ubuntu/agrigpt/agrigpt-backend-computer-vision
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8009
