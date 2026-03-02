---
name: claw-guard
description: System-level watchdog for OpenClaw gateway restarts and sub-agent task PIDs. Monitors registered PIDs and optional log/directory freshness. Auto-reverts config on failed gateway restarts. Requires explicit registration — does NOT auto-discover. Use when running long background tasks or before gateway restarts.
---

# ClawGuard — Task & Gateway Watchdog

A lightweight service that monitors **registered** events:

1. **Sub-agent task PIDs** — if PID dies → notify. If log/dir stale → alert.
2. **Gateway restarts** — if restart fails → revert config backups (newest to oldest) → retry → notify.

**ClawGuard only monitors what is explicitly registered.** It does not auto-discover.

## Install

```bash
cd <skill-dir>
bash scripts/install.sh
```

Installs as:
- **Linux**: systemd user service (`claw-guard.service`)
- **macOS**: launchd agent (`com.openclaw.claw-guard.plist`)

## Usage

### Register a task

```bash
claw-guard register --id "benchmark-q8" --pid 12345 \
  --target "room:!abc:server" \
  --log "/path/to/task.log" --timeout 180 \
  --command "python3 benchmark.py"

# Or watch a directory for new file creation:
claw-guard register --id "export-gguf" --pid 12345 \
  --target "room:!abc:server" \
  --watch-dir "/path/to/output/" --timeout 300 \
  --command "export_gguf.py"
```

- `--pid` (required): process ID to watch
- `--target` (required): notification target (`room:!id:server`, `telegram:chatid`, `discord:#ch`)
- `--log` (optional): log file — checks mtime only, not content
- `--watch-dir` (optional): directory — checks newest file mtime
- `--timeout` (optional, default 180): seconds of inactivity before stale alert
- `--command` (optional): description included in notifications

### Register a gateway restart

```bash
claw-guard register-restart --target "room:!abc:server"
systemctl --user restart openclaw-gateway
```

Snapshots current config before restart. Keeps up to 5 rotating backups.
If gateway fails to start within 30s → tries backups newest-to-oldest → notifies with failure reason.

### Manage

```bash
claw-guard status          # Show tasks, restart watch, config backups
claw-guard remove --id X   # Remove a task
claw-guard clear-done      # Remove completed/gone tasks
```

## Behavior

### Check cycle (every 15s)

1. **Gateway restart**: if registered and gateway not active after 30s → revert + retry + notify
2. **PID check**: if PID gone → notify target
3. **Log/dir freshness**: if mtime exceeds timeout → notify target (PID still alive but possibly stuck)

### Deduplication

After notifying, the registered entry is **removed from the registry**. No dedup tracking needed — once removed, it can't fire again.

### Restart / reboot behavior

On service restart or system reboot:
- **All registered tasks are cleared** — nothing carries over
- **Config backups persist** on disk (only thing that survives)

This is by design: after a reboot, all monitored processes are gone anyway. The agent must re-register any new tasks after the service restarts.

## Notification Targets

Each task and restart watch specifies its own target. Any format `openclaw message send --target` accepts:
- `room:!roomId:server` (Matrix)
- `telegram:chatid`
- `discord:#channel`
- `slack:#channel`

## Agent Integration

Add to your agent's rules:
- **Before gateway restart**: `claw-guard register-restart --target "..."`
- **After spawning long exec**: `claw-guard register --id X --pid $PID --target "..." [--log ...] [--timeout ...]`
- ClawGuard notifies → agent confirms success/failure
