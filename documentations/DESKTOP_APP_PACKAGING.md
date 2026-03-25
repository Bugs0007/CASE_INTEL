# Packaging Case Intel as a Desktop Application

## 🎯 Overview

Transform Case Intel into a **one-click installable Windows desktop application** that bundles all dependencies and runs entirely locally.

**User Experience:**

1. Download `CaseIntel-Setup.exe` (single file)
2. Double-click to install
3. Application starts automatically
4. System tray icon shows status
5. Click icon → opens web interface in browser

---

## 📦 Architecture Options

### **Recommended: Electron + Embedded Services**

```
CaseIntel Desktop App
├── Electron Shell (UI + Launcher)
├── Embedded Python (Django backend)
├── Portable PostgreSQL
├── Bundled Ollama
└── System Tray Manager
```

**Why this approach:**

- ✅ Native Windows application feel
- ✅ Auto-updates capability
- ✅ System tray integration
- ✅ Professional installer
- ✅ No manual configuration needed

---

## 🏗️ Complete Implementation Strategy

### **Option A: Electron Wrapper (Recommended for Production)**

**Best for:** Distributing to multiple lawyers, professional appearance

**Components:**

1. **Electron Shell** - Manages services and provides UI
2. **Embedded Python** - Portable Python with Django
3. **Portable PostgreSQL** - No installation required
4. **Bundled Ollama** - Pre-configured
5. **NSIS Installer** - Windows installer generator

**Pros:** Professional, auto-updates, native feel
**Cons:** Larger download size (~2-3 GB initial download)

---

### **Option B: Python Desktop App with PyInstaller (Simpler)**

**Best for:** Quick MVP, single user (your dad)

**Components:**

1. **PyInstaller** - Bundle Python + dependencies
2. **Portable PostgreSQL** - Include in package
3. **Ollama** - Separate install or bundled
4. **Batch Scripts** - Simple launcher

**Pros:** Simpler to build, smaller learning curve
**Cons:** Less polished, manual updates

---

## 🚀 Implementation Guide: Electron Approach

### Phase 1: Project Structure

```
case-intel-desktop/
├── electron/                      # Electron app
│   ├── main.js                   # Main process
│   ├── preload.js                # Preload script
│   ├── renderer/                 # UI (optional - can just open browser)
│   ├── services/                 # Service management
│   │   ├── django-manager.js
│   │   ├── postgres-manager.js
│   │   └── ollama-manager.js
│   └── package.json
│
├── backend/                       # Your existing Django app
│   ├── case_intel_project/
│   ├── core/
│   ├── manage.py
│   └── requirements.txt
│
├── resources/                     # Bundled dependencies
│   ├── python-embed/             # Embedded Python 3.11
│   ├── postgresql-portable/      # Portable PostgreSQL
│   ├── ollama/                   # Ollama binaries
│   └── models/                   # Pre-downloaded Ollama models
│
├── installer/                     # Installer configuration
│   ├── build.js                  # Build script
│   └── installer.nsi             # NSIS installer script
│
└── package.json                   # Root package.json
```

### Phase 2: Core Components

**1. Service Manager (Electron Main Process)**

Creates a system tray app that manages all backend services.

**Key responsibilities:**

- Start/stop PostgreSQL
- Start/stop Django
- Start/stop Ollama
- Monitor service health
- Open browser to app
- Show status in system tray

**2. Embedded Python Setup**

Use Windows embeddable Python distribution (no system installation needed).

**Structure:**

```
resources/python-embed/
├── python.exe
├── python311.dll
├── Lib/
└── site-packages/    # All pip packages pre-installed
```

**3. Portable PostgreSQL**

Use PostgreSQL portable version that runs without installation.

**Configuration:**

- Data directory in user's AppData
- Port: 5432 (or auto-detect free port)
- Pre-configured with case_intel database

**4. Bundled Ollama**

Include Ollama executable and pre-downloaded models.

**Structure:**

```
resources/ollama/
├── ollama.exe
└── models/
    ├── llama3.1-8b/
    └── nomic-embed-text/
```

### Phase 3: Electron Application Code

**File: `electron/main.js`** (Core logic)

```javascript
// Main responsibilities:
// 1. Start all services on app launch
// 2. Create system tray icon
// 3. Handle app lifecycle
// 4. Manage service processes

const { app, Tray, Menu } = require("electron");
const path = require("path");
const PostgresManager = require("./services/postgres-manager");
const DjangoManager = require("./services/django-manager");
const OllamaManager = require("./services/ollama-manager");

class CaseIntelApp {
  constructor() {
    this.tray = null;
    this.services = {
      postgres: new PostgresManager(),
      ollama: new OllamaManager(),
      django: new DjangoManager(),
    };
  }

  async start() {
    // 1. Start PostgreSQL
    // 2. Wait for DB ready
    // 3. Run Django migrations
    // 4. Start Ollama
    // 5. Start Django server
    // 6. Create system tray
    // 7. Open browser
  }

  createTray() {
    // System tray with menu:
    // - Open Case Intel
    // - Service Status
    // - Settings
    // - Restart Services
    // - Quit
  }

  async stop() {
    // Stop all services gracefully
  }
}
```

**File: `electron/services/postgres-manager.js`**

Manages PostgreSQL lifecycle.

**Responsibilities:**

- Extract portable PostgreSQL on first run
- Initialize data directory
- Start postgres.exe with custom config
- Monitor process health
- Stop gracefully

**File: `electron/services/django-manager.js`**

Manages Django backend.

**Responsibilities:**

- Set environment variables
- Run migrations on first launch
- Start Django with embedded Python
- Monitor port availability
- Auto-restart on crashes

**File: `electron/services/ollama-manager.js`**

Manages Ollama service.

**Responsibilities:**

- Start Ollama server
- Verify models are present
- Pull models on first run if needed
- Monitor service health

### Phase 4: Building and Packaging

**File: `package.json`** (Root)

```json
{
  "name": "case-intel",
  "version": "1.0.0",
  "main": "electron/main.js",
  "scripts": {
    "start": "electron .",
    "build": "electron-builder",
    "build:win": "electron-builder --win"
  },
  "build": {
    "appId": "com.caseintel.app",
    "productName": "Case Intel",
    "directories": {
      "output": "dist"
    },
    "files": ["electron/**/*", "backend/**/*", "resources/**/*"],
    "win": {
      "target": "nsis",
      "icon": "assets/icon.ico"
    },
    "nsis": {
      "oneClick": false,
      "allowToChangeInstallationDirectory": true,
      "createDesktopShortcut": true,
      "createStartMenuShortcut": true,
      "shortcutName": "Case Intel"
    }
  },
  "dependencies": {
    "electron": "^28.0.0"
  },
  "devDependencies": {
    "electron-builder": "^24.0.0"
  }
}
```

**Build Process:**

```bash
# 1. Prepare embedded Python
python -m pip download -r requirements.txt -d resources/python-embed/packages
# Install into resources/python-embed/site-packages

# 2. Download portable PostgreSQL
# Extract to resources/postgresql-portable/

# 3. Bundle Ollama
# Copy ollama.exe to resources/ollama/

# 4. Download models
ollama pull llama3.1:8b
ollama pull nomic-embed-text
# Copy from C:\Users\{user}\.ollama\models to resources/ollama/models/

# 5. Build Electron app
npm run build:win
```

**Output:**

- `dist/Case Intel Setup 1.0.0.exe` (~2-3 GB installer)

---

## 🔧 Implementation Details

### 1. First-Run Setup

**On first launch, the app should:**

1. **Extract resources** to user directory:
   - Windows: `C:\Users\{username}\AppData\Local\CaseIntel\`
   - PostgreSQL data: `AppData\Local\CaseIntel\data\postgres\`
   - Django media: `AppData\Local\CaseIntel\data\documents\`
   - Logs: `AppData\Local\CaseIntel\logs\`

2. **Initialize PostgreSQL:**
   - Run `initdb` to create database cluster
   - Create `case_intel` database
   - Create default user

3. **Run Django migrations:**
   - Execute `python manage.py migrate`
   - Create default data if needed

4. **Verify Ollama models:**
   - Check if models are present
   - Copy from bundled resources if needed

5. **Start services:**
   - PostgreSQL → Django → Ollama
   - Wait for health checks

6. **Open browser:**
   - Navigate to `http://localhost:8000`

### 2. Service Health Monitoring

**Implement health checks:**

```javascript
// Check every 30 seconds
setInterval(() => {
  checkPostgresHealth(); // Query on port 5432
  checkDjangoHealth(); // HTTP GET /api/health
  checkOllamaHealth(); // HTTP GET http://localhost:11434/
}, 30000);

// Update tray icon based on status
updateTrayIcon(allServicesHealthy ? "active" : "error");
```

### 3. Auto-Updates

**Use electron-updater:**

```javascript
const { autoUpdater } = require("electron-updater");

autoUpdater.checkForUpdatesAndNotify();

// User sees notification in system tray
// Click to download and install update
```

### 4. Configuration UI

**Settings accessible from tray menu:**

- Database location
- Server port
- Ollama model selection
- Log level
- Auto-start on Windows boot

### 5. Logs and Debugging

**Log locations:**

- PostgreSQL: `logs/postgres.log`
- Django: `logs/django.log`
- Ollama: `logs/ollama.log`
- Electron: `logs/electron.log`

**Accessible via tray menu:** "View Logs" → Opens folder

---

## 🎨 Alternative: Simpler Python-Only Approach

### Using PyInstaller + Batch Scripts

**For MVP or single-user deployment:**

**Structure:**

```
CaseIntel/
├── CaseIntel.exe              # PyInstaller bundled Django
├── data/
│   ├── postgresql/
│   └── documents/
├── ollama/
│   ├── ollama.exe
│   └── models/
├── start.bat                  # Launcher script
└── settings.json              # User config
```

**File: `start.bat`**

```batch
@echo off
echo Starting Case Intel...

REM Start PostgreSQL
start /B data\postgresql\bin\pg_ctl.exe -D data\postgresql\data start

REM Wait for DB
timeout /t 3

REM Start Ollama
start /B ollama\ollama.exe serve

REM Start Django
CaseIntel.exe runserver

REM Open browser
start http://localhost:8000
```

**Build Process:**

```bash
# 1. Bundle Django with PyInstaller
pyinstaller --onefile manage.py --name CaseIntel

# 2. Copy portable PostgreSQL to dist/data/postgresql/
# 3. Copy Ollama to dist/ollama/
# 4. Create start.bat in dist/
# 5. Zip entire dist/ folder
# 6. Distribute CaseIntel.zip
```

**Pros:**

- Much simpler to build
- Smaller download (~1 GB)
- Easy to debug

**Cons:**

- Manual start (double-click batch file)
- No system tray
- No auto-updates
- Less polished

---

## 📦 Distribution Strategy

### Option 1: Direct Download

**Host installer on:**

- Your personal website
- Google Drive
- GitHub Releases (if open source)

**User flow:**

1. Visit download page
2. Download `CaseIntel-Setup.exe`
3. Run installer
4. App starts automatically

### Option 2: Microsoft Store (Future)

**Requires:**

- Microsoft Developer account ($19)
- MSIX packaging
- Certification process

**Benefits:**

- Automatic updates via Store
- Trusted installation source
- Easy discovery

### Option 3: GitHub Releases (Free)

**Perfect for beta testing:**

- Upload releases to GitHub
- Users download from Releases page
- Free hosting
- Version tracking built-in

---

## 🔐 Security Considerations

### 1. Code Signing

**Windows SmartScreen will block unsigned executables.**

**Solution:**

- Get code signing certificate (~$100-400/year)
- Sign the installer with `signtool.exe`
- Users won't see scary warnings

**Without signing:**

- Users see "Unknown Publisher" warning
- Must click "More Info" → "Run Anyway"
- Acceptable for limited distribution

### 2. Data Encryption

**Since legal documents are sensitive:**

- Encrypt SQLite database at rest (SQLCipher)
- Encrypt document files on disk
- User sets master password on first run

### 3. Auto-Backup

**Include automatic backup feature:**

- Daily backup to OneDrive/Google Drive
- Local backup to external drive
- Export all data as ZIP

---

## 📊 Size Comparison

| Component           | Size        | Notes                  |
| ------------------- | ----------- | ---------------------- |
| Embedded Python     | ~50 MB      | Including all packages |
| Portable PostgreSQL | ~100 MB     | Binaries only          |
| Ollama executable   | ~200 MB     |                        |
| Llama 3.1 8B model  | ~4.7 GB     | Pre-downloaded         |
| Nomic Embed model   | ~274 MB     | Pre-downloaded         |
| Electron framework  | ~150 MB     |                        |
| Django app          | ~10 MB      |                        |
| **Total Download**  | **~5.5 GB** | First-time install     |

**Optimizations:**

- Download models on first run (reduces to ~500 MB)
- Offer "lite" version without pre-bundled models
- Compress installer (~3 GB compressed)

---

## 🎯 Recommended Path

### For Your Dad (Single User):

**Use the Simpler Approach:**

1. **Create portable package:**
   - Embedded Python + Django
   - Portable PostgreSQL
   - Ollama (separate installer)
   - Simple launcher script

2. **Manual setup:**
   - Help him install Ollama once
   - Copy portable folder to Documents
   - Create desktop shortcut to launcher

3. **Updates:**
   - Replace Django exe when needed
   - Models stay in place

**Effort:** 2-3 days to package and test

### For Multiple Lawyers (Distribution):

**Build Electron App:**

1. Professional installer
2. System tray integration
3. Auto-updates
4. Signed executable

**Effort:** 1-2 weeks initial build

---

## 🚀 Quick Start Implementation

### Step 1: Download Dependencies

```bash
# Download portable PostgreSQL
# URL: https://get.enterprisedb.com/postgresql/postgresql-16.2-1-windows-x64-binaries.zip

# Download embeddable Python
# URL: https://www.python.org/ftp/python/3.11.8/python-3.11.8-embed-amd64.zip

# Install packages into embedded Python
python -m pip install -r requirements.txt --target=python-embed/Lib/site-packages
```

### Step 2: Create Launcher

```javascript
// Simple Node.js script (can run without Electron for testing)
const { spawn } = require("child_process");
const path = require("path");

// Start PostgreSQL
const postgres = spawn("resources/postgresql/bin/postgres", [
  "-D",
  "data/postgres",
]);

// Start Django
const django = spawn("resources/python-embed/python", [
  "backend/manage.py",
  "runserver",
]);

// Start Ollama
const ollama = spawn("resources/ollama/ollama", ["serve"]);

// Open browser after 3 seconds
setTimeout(() => {
  require("child_process").exec("start http://localhost:8000");
}, 3000);
```

### Step 3: Test Locally

```bash
node launcher.js
# Verify all services start
# Test application works
```

### Step 4: Package

```bash
# Use electron-builder or NSIS
npm run build:win
```

---

## ✅ Final Recommendation

**For MVP (your dad):**

1. Use PyInstaller to bundle Django
2. Include portable PostgreSQL
3. User installs Ollama separately (one-time setup)
4. Create simple `start.bat` launcher
5. Package as ZIP file

**Time:** 2-3 days
**Size:** ~500 MB download (models downloaded separately)

**For production (multiple users):**

1. Build Electron wrapper
2. Bundle all dependencies
3. Create professional installer
4. Implement auto-updates

**Time:** 1-2 weeks
**Size:** ~3 GB installer

**Either way, you achieve the goal: One download, zero cloud deployment, complete local operation!** 🎉
