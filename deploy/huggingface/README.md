---
title: Aegis-Bio AstroDoc API
emoji: 🩺
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: Backend and AstroDoc AI for the Aegis-Bio crew health app
---

# Aegis-Bio backend + AstroDoc AI

FastAPI backend of Aegis-Bio (NASA Space Apps, Team Sigmoid) with the AstroDoc AI flight-surgeon
chatbot: open-source LLMs on Groq, Whisper voice input, photo reading of device displays, and a
NASA HRP knowledge base.

- API docs: `/docs`
- AstroDoc status: `/api/astrodoc/assistant/status`

This Space is deployed from the team's GitHub repository with `deploy/huggingface/deploy_space.py`;
do not edit files here directly.
