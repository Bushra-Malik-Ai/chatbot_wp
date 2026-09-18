# Directory — Admin Chatbot (FastAPI)

An admin chatbot that lets an administrator add, remove, and update user
records through natural-language chat commands. Built with FastAPI,
SQLAlchemy, and vanilla JS.

## Features

- **Auto-login**: signs you in automatically if your email already exists
  in the user directory — no password required.
- **Natural-language commands** for user management:
  - `add the user "jane@xyz.com" with phone number "+123"`
  - `remove the user "jane@xyz.com"`
  - `update janes city to Lahore`
- **Audit log**: every command is recorded with who ran it, what they
  typed, and whether it succeeded.
- **Live directory view**: see all users update in real time as commands
  run.

## Tech stack

- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Command parsing**: rule-based regex matching (deterministic, no
  external API calls or cost)
- **Frontend**: vanilla HTML/JS chat interface, no framework
- **Auth**: JWT session tokens issued on successful auto-login

## Project structure
