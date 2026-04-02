# 🚀 Quick Setup - Case Intel

## First Time Setup (One-Time Only)

### Step 1: Install Redis

**Option A: Automatic Installation (Easiest)**

Right-click PowerShell and select **"Run as Administrator"**, then:

```powershell
cd C:\Users\Bhagath\OneDrive\Desktop\CASE_INTEL
Set-ExecutionPolicy Bypass -Scope Process -Force
.\setup_redis.ps1
```

This will automatically install Chocolatey and Redis.

**Option B: Manual Installation**

Download Redis for Windows:

- Link: https://github.com/tporadowski/redis/releases
- Get: `Redis-x64-5.0.14.1.msi`
- Install and check "Add to PATH"

---

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

### Step 3: Install Node.js Dependencies

```bash
cd frontend-next
npm install
```

---

## Running the Project

### Easy Way (Recommended)

Just double-click or run:

```bash
start_dev.bat
```

This will automatically:

- ✅ Check if Redis is running (start it if not)
- ✅ Start Django backend (port 8000)
- ✅ Start Celery worker (background tasks)
- ✅ Start Next.js frontend (port 3000)

All in separate terminal windows!

---

### Manual Way (If you prefer control)

**Terminal 1: Redis**

```bash
redis-server
```

**Terminal 2: Django**

```bash
python manage.py runserver 8000
```

**Terminal 3: Celery**

```bash
celery -A case_intel_project worker --loglevel=info --pool=solo
```

**Terminal 4: Next.js**

```bash
cd frontend-next
npm run dev
```

---

## Open Your Browser

Navigate to: **http://localhost:3000**

---

## Troubleshooting

### "Redis not installed"

Run `setup_redis.ps1` as administrator (see Step 1)

### "Chocolatey not found"

Install manually: https://chocolatey.org/install

### "Module not found: celery"

```bash
pip install -r requirements.txt
```

### "Port already in use"

Kill the process:

```bash
# Find process using port 8000
netstat -ano | findstr :8000

# Kill it (replace <PID> with actual number)
taskkill /PID <PID> /F
```

---

## What Each Service Does

| Service     | Port | Purpose                  |
| ----------- | ---- | ------------------------ |
| **Redis**   | 6379 | Message queue + caching  |
| **Django**  | 8000 | REST API backend         |
| **Celery**  | -    | Background job processor |
| **Next.js** | 3000 | React frontend           |

---

## Project Structure

```
CASE_INTEL/
├── core/                    # Django app (models, views, services)
├── case_intel_project/      # Django settings + Celery config
├── frontend-next/           # Next.js React app
├── documentations/          # All documentation
├── start_dev.bat           # Auto-start all services
├── setup_redis.ps1         # One-time Redis setup
└── requirements.txt        # Python dependencies
```

---

## Need More Help?

- **Full guide**: See `documentations/QUICKSTART.md`
- **Redis setup**: See `REDIS_SETUP.md`
- **API docs**: See `documentations/API_CONTRACTS.md`
- **System design**: See `documentations/SYSTEM_DESIGN.md`

---

Happy coding! 🎉
