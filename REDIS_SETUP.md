# Redis Setup for Case Intel

Redis is required for:

1. **Celery task queue** - Background job processing (court case fetching)
2. **Django caching** - Caching fetched court data

## Quick Setup

### Windows

**Option 1: Direct Download (Recommended)**

1. Download Redis for Windows: https://github.com/microsoftarchive/redis/releases
2. Extract to `C:\Program Files\Redis`
3. Run `redis-server.exe`

**Option 2: Chocolatey**

```bash
choco install redis-64
redis-server
```

### macOS

```bash
brew install redis
redis-server
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
```

## Verify Redis is Running

```bash
redis-cli ping
# Should return: PONG
```

## Configuration

Redis uses **different database numbers** for different purposes:

| Database | Purpose           | Configuration                                |
| -------- | ----------------- | -------------------------------------------- |
| DB 0     | Celery task queue | `CELERY_BROKER_URL=redis://localhost:6379/0` |
| DB 1     | Django caching    | `REDIS_URL=redis://127.0.0.1:6379/1`         |

**Important:** These are **NOT separate Redis instances**. They're different databases within the **same Redis server**.

## Default Settings

- **Host:** localhost / 127.0.0.1
- **Port:** 6379
- **No password** (for local development)

## Troubleshooting

### Redis not starting

```bash
# Check if port 6379 is in use
netstat -ano | findstr :6379

# Kill process if needed (Windows)
taskkill /PID <PID> /F
```

### Connection refused

```bash
# Make sure Redis is running
redis-server

# Test connection
redis-cli ping
```

### Memory usage

Redis is lightweight:

- **Idle:** ~10-20 MB
- **Active:** ~50-100 MB
- **Very light on resources**

## Development Workflow

### Start Redis (once)

```bash
redis-server
```

### Use the startup script

We've created `start_dev.bat` that automatically:

1. Checks if Redis is running
2. Starts Django backend
3. Starts Celery worker
4. Starts frontend

Just run:

```bash
start_dev.bat
```

## Production Notes

For production deployment:

- Use Redis with password authentication
- Consider Redis Sentinel for high availability
- Use Redis persistence (RDB or AOF)
- Monitor memory usage

AWS ElastiCache (Redis) is recommended for production.

## Need Help?

See `documentations/QUICKSTART.md` for full setup instructions.
