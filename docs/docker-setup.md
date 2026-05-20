# Running Terminal Monitor with Docker

No Python setup needed. Docker handles everything.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac or Windows)
- Or Docker Engine + Compose plugin (Linux)
- Ollama running on your machine (optional — needed for AI chat)

## Quick Start

```bash
git clone https://github.com/annointedfrom/terminal-monitor
cd terminal-monitor
touch config.yaml
mkdir -p data
docker-compose up -d
```

Open `http://localhost:8084` — the setup wizard appears automatically on first run.

Fill in your preferences and click **SAVE CONFIG**. You'll be redirected to the dashboard.

## Ollama / AI Chat

The AI chat tab connects to Ollama running on your host machine. docker-compose is
pre-configured to reach it at `host.docker.internal:11434`. Just make sure Ollama is
running before starting the container:

```bash
ollama serve           # starts Ollama if not already running
ollama pull llama3.2:3b
docker-compose up -d
```

To use a different Ollama URL:

```bash
OLLAMA_URL=http://my-server:11434 docker-compose up -d
```

## Stopping and Restarting

```bash
docker-compose down   # stop
docker-compose up -d  # start again
```

Your `config.yaml` and `data/` history survive restarts — they're mounted from the host.

## Updating

```bash
docker-compose down
git pull
docker-compose up -d --build
```

## Ports

| Port | Service |
|------|---------|
| 8084 | Terminal Monitor dashboard |

## Data locations (on your host machine)

| Path | Contents |
|------|----------|
| `./config.yaml` | Your personal settings (gitignored) |
| `./data/` | Scan + resource history (gitignored) |
