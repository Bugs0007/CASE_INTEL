# 📘 Case Intel – Court Data Fetching System (Design Document)

**Version:** 1.0  
**Last Updated:** April 2026  
**Status:** Design Phase

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Goal](#2-goal)
3. [Constraints](#3-constraints)
4. [Solution Overview](#4-solution-overview)
5. [System Architecture](#5-system-architecture)
6. [Database Schema Extensions](#6-database-schema-extensions)
7. [API Design](#7-api-design)
8. [Backend Flow](#8-backend-flow)
9. [Frontend UX Flow](#9-frontend-ux-flow)
10. [Error Handling](#10-error-handling)
11. [Performance Strategy](#11-performance-strategy)
12. [Legal & Safety Considerations](#12-legal--safety-considerations)
13. [Future Enhancements](#13-future-enhancements)
14. [Architecture Summary](#14-architecture-summary)

---

## 1. 🧠 Problem Statement

Legal professionals currently face significant challenges with court case tracking:

### Current Manual Process:

- Manually check court websites
- Track hearing dates manually
- Repeatedly log in to multiple court portals
- Copy-paste information into their own systems

### ❌ Problems:

- **Time-consuming**: Hours spent checking updates across multiple cases
- **Error-prone**: Manual data entry leads to mistakes
- **No centralized tracking**: Data scattered across different court websites
- **No automation**: No way to automatically sync case updates

---

## 2. 🎯 Goal

Build a system where:

```text
User enters case number + court
↓
System automatically fetches case details
↓
Stores structured data (hearings, status, parties, etc.)
↓
User views everything in one centralized dashboard
```

### Success Criteria:

- ✅ Fetch case details in < 15 seconds
- ✅ Store data in our existing database schema
- ✅ Provide real-time progress feedback to users
- ✅ Handle common errors gracefully (CAPTCHA, site down, etc.)

---

## 3. 🚧 Constraints (VERY IMPORTANT)

### Technical Constraints:

- ❌ **No unified API for Indian courts**: Each court has its own website
- ❌ **Websites are not developer-friendly**: Designed for human interaction only
- ⚠️ **CAPTCHA may appear**: Some courts use CAPTCHA to prevent automation
- ⚠️ **Scraping is slow**: Typical fetch time is 3–10 seconds
- ⚠️ **Inconsistent data formats**: Each court presents data differently
- ⚠️ **Site reliability**: Court websites may be slow or temporarily down

### Legal Constraints:

- Must respect robots.txt (where applicable)
- Rate limiting to avoid overloading court servers
- No bypassing of security measures
- Compliance with IT Act guidelines

---

## 4. 💡 Solution Overview

We introduce a **Court Fetching System** with the following approach:

```text
Frontend → API → Background Job → Scraper → Parser → DB → Response
```

### Key Design Decisions:

1. **Asynchronous Processing**: Never block the user interface
2. **Job-based Architecture**: Track fetch status independently
3. **Pluggable Scrapers**: Different scraper implementations per court
4. **Existing Schema Integration**: Minimal changes to current database
5. **Progressive Enhancement**: Start with basic features, add complexity later

---

## 5. 🏗️ System Architecture

### High-level Flow:

```text
┌─────────────┐
│   User      │
│  (Frontend) │
└──────┬──────┘
       │
       │ POST /api/cases/fetch/
       │
       ▼
┌─────────────────┐
│   API Layer     │ ← Creates FetchJob
└──────┬──────────┘
       │
       │ Trigger background task
       │
       ▼
┌─────────────────┐
│ Background      │
│ Worker (Celery) │
└──────┬──────────┘
       │
       │ Select appropriate scraper
       │
       ▼
┌─────────────────┐
│   Scraper       │ ← Selenium + BeautifulSoup
│   (Court Site)  │
└──────┬──────────┘
       │
       │ Raw HTML
       │
       ▼
┌─────────────────┐
│    Parser       │ ← Extract structured data
└──────┬──────────┘
       │
       │ Structured data
       │
       ▼
┌─────────────────┐
│   Database      │ ← Save to Case + Hearing + Documents
└──────┬──────────┘
       │
       │ Job complete
       │
       ▼
┌─────────────────┐
│   Frontend      │ ← Polls for status
│   (Displays)    │
└─────────────────┘
```

### Component Breakdown:

#### 1. **API Layer** (Django REST Framework)

- Accepts fetch requests
- Creates FetchJob records
- Returns job ID immediately
- Provides status endpoint for polling

#### 2. **Background Worker** (Celery)

- Picks up jobs from queue
- Manages scraper execution
- Updates job status
- Handles retries and failures

#### 3. **Scraper Layer** (Selenium)

- Navigates to court website
- Fills out search forms
- Waits for results to load
- Captures page HTML

#### 4. **Parser Layer** (BeautifulSoup)

- Extracts case details
- Parses hearing dates
- Identifies parties and judges
- Structures data for database

#### 5. **Database Layer** (PostgreSQL)

- Stores fetch jobs
- Saves case information
- Records hearings
- Logs activities

---

## 6. 🧩 Database Schema Extensions

### Integration with Existing Schema

From your current schema (as defined in `DB_SCHEMA.md`), you already have:

- `Case`
- `Hearing`
- `ActivityLog`
- `Document`
- `Party`

### ✅ New Table Required: `FetchJob`

```sql
CREATE TABLE fetch_job (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(100) NOT NULL,
    court_name VARCHAR(200) NOT NULL,
    court_type VARCHAR(50) NOT NULL,  -- 'district', 'high', 'supreme'

    -- Job status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- Values: 'pending', 'running', 'success', 'failed', 'cancelled'

    -- Results
    result_json JSONB,  -- Raw scraped data for debugging
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Relationship
    case_id INTEGER REFERENCES case(id) ON DELETE SET NULL,

    -- Metadata
    retry_count INTEGER DEFAULT 0,
    user_id INTEGER REFERENCES auth_user(id)
);

CREATE INDEX idx_fetch_job_status ON fetch_job(status);
CREATE INDEX idx_fetch_job_case_number ON fetch_job(case_number);
CREATE INDEX idx_fetch_job_created_at ON fetch_job(created_at DESC);
```

### ✅ Minor Changes to Existing `Case` Table

Add the following columns to support fetched data:

```sql
ALTER TABLE case ADD COLUMN court_name VARCHAR(200);
ALTER TABLE case ADD COLUMN court_type VARCHAR(50);
ALTER TABLE case ADD COLUMN cnr_number VARCHAR(100);  -- Central National Registration number
ALTER TABLE case ADD COLUMN last_fetched_at TIMESTAMP;
ALTER TABLE case ADD COLUMN auto_fetch_enabled BOOLEAN DEFAULT FALSE;

CREATE INDEX idx_case_court_name ON case(court_name);
CREATE INDEX idx_case_cnr_number ON case(cnr_number);
```

### Data Flow Example:

```text
1. User submits: "CRL.P.No.1234/2023" + "Telangana High Court"
   ↓
2. FetchJob created (status: 'pending')
   ↓
3. Worker picks job (status: 'running')
   ↓
4. Scraper fetches data
   ↓
5. Parser creates/updates Case record
   ↓
6. Parser creates Hearing records
   ↓
7. FetchJob updated (status: 'success', case_id set)
   ↓
8. Frontend displays case details
```

---

## 7. 🔌 API Design (EXTENDING your current APIs)

### Existing API Structure:

You already have `/api/cases/` for CRUD operations.

### New Endpoints:

---

### 7.1 **POST** `/api/cases/fetch/`

**Purpose**: Initiate a new case fetch operation

#### Request:

```json
{
  "case_number": "CRL.P.No.1234/2023",
  "court_name": "Telangana High Court",
  "court_type": "high"
}
```

**Field Validation:**

- `case_number`: Required, max 100 chars
- `court_name`: Required, must be in supported courts list
- `court_type`: Required, enum: ['district', 'high', 'supreme']

#### Response (Immediate - 202 Accepted):

```json
{
  "job_id": 123,
  "status": "pending",
  "message": "Case fetch started",
  "estimated_time_seconds": 10
}
```

#### Error Responses:

```json
// 400 Bad Request - Invalid input
{
  "error": "validation_error",
  "details": {
    "case_number": ["This field is required"]
  }
}

// 429 Too Many Requests - Rate limited
{
  "error": "rate_limit_exceeded",
  "message": "Maximum 10 fetch requests per hour",
  "retry_after_seconds": 1800
}
```

---

### 7.2 **GET** `/api/cases/fetch/{job_id}/`

**Purpose**: Check status of a fetch job

#### Response (Success):

```json
{
  "job_id": 123,
  "status": "success",
  "case_id": 45,
  "case_number": "CRL.P.No.1234/2023",
  "created_at": "2026-04-02T10:00:00Z",
  "completed_at": "2026-04-02T10:00:08Z",
  "duration_seconds": 8
}
```

#### Response (Running):

```json
{
  "job_id": 123,
  "status": "running",
  "message": "Fetching case details from court website...",
  "progress_percentage": 45,
  "created_at": "2026-04-02T10:00:00Z"
}
```

#### Response (Failed):

```json
{
  "job_id": 123,
  "status": "failed",
  "error": "case_not_found",
  "error_message": "Case number not found on court website",
  "created_at": "2026-04-02T10:00:00Z",
  "completed_at": "2026-04-02T10:00:07Z"
}
```

---

### 7.3 **POST** `/api/cases/fetch/{job_id}/retry/`

**Purpose**: Retry a failed fetch job

#### Response:

```json
{
  "job_id": 124, // New job ID
  "status": "pending",
  "message": "Retry initiated",
  "original_job_id": 123
}
```

---

### 7.4 **GET** `/api/cases/fetch/`

**Purpose**: List recent fetch jobs (for admin/debugging)

#### Query Parameters:

- `status`: Filter by status
- `limit`: Number of results (default: 20)
- `offset`: Pagination offset

#### Response:

```json
{
  "count": 45,
  "next": "/api/cases/fetch/?offset=20",
  "previous": null,
  "results": [
    {
      "job_id": 123,
      "case_number": "CRL.P.No.1234/2023",
      "court_name": "Telangana High Court",
      "status": "success",
      "created_at": "2026-04-02T10:00:00Z"
    }
  ]
}
```

---

## 8. ⚙️ Backend Flow (Step-by-step)

### Step 1: API Receives Request

**File**: `core/views/fetch_views.py`

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from core.models import FetchJob
from core.tasks import process_fetch_job

@api_view(['POST'])
def fetch_case(request):
    """
    Initiate case fetch from court website
    """
    # Validate input
    serializer = FetchJobSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    # Create fetch job
    job = FetchJob.objects.create(
        case_number=serializer.validated_data['case_number'],
        court_name=serializer.validated_data['court_name'],
        court_type=serializer.validated_data['court_type'],
        status='pending',
        user_id=request.user.id if request.user.is_authenticated else None
    )

    # Trigger background task
    process_fetch_job.delay(job.id)

    # Return immediate response
    return Response({
        'job_id': job.id,
        'status': 'pending',
        'message': 'Case fetch started',
        'estimated_time_seconds': 10
    }, status=status.HTTP_202_ACCEPTED)
```

---

### Step 2: Background Worker Starts

**File**: `core/tasks.py`

```python
from celery import shared_task
from core.models import FetchJob
from core.scrapers import get_scraper
from core.parsers import parse_case_data
from django.utils import timezone

@shared_task(bind=True, max_retries=3)
def process_fetch_job(self, job_id):
    """
    Background task to fetch case details from court website
    """
    try:
        # Get job
        job = FetchJob.objects.get(id=job_id)

        # Update status
        job.status = 'running'
        job.started_at = timezone.now()
        job.save()

        # Get appropriate scraper
        scraper = get_scraper(job.court_type, job.court_name)

        # Fetch data
        raw_data = scraper.fetch_case(job.case_number)

        # Store raw data
        job.result_json = raw_data
        job.save()

        # Parse and save to database
        case = parse_case_data(raw_data, job)

        # Update job status
        job.status = 'success'
        job.case_id = case.id
        job.completed_at = timezone.now()
        job.save()

    except CaseNotFoundException as e:
        job.status = 'failed'
        job.error_message = 'Case not found on court website'
        job.completed_at = timezone.now()
        job.save()

    except CaptchaRequiredException as e:
        job.status = 'failed'
        job.error_message = 'CAPTCHA verification required'
        job.completed_at = timezone.now()
        job.save()

    except Exception as e:
        job.retry_count += 1
        job.save()

        # Retry if not exceeded max retries
        if job.retry_count < 3:
            raise self.retry(exc=e, countdown=60 * job.retry_count)
        else:
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save()
```

---

### Step 3: Scraper Selection

**File**: `core/scrapers/__init__.py`

```python
from .ecourt_scraper import ECourtScraper
from .telangana_high_court_scraper import TelanganaHighCourtScraper
from .supreme_court_scraper import SupremeCourtScraper

def get_scraper(court_type, court_name):
    """
    Factory function to get appropriate scraper based on court
    """
    if court_type == "district":
        return ECourtScraper()

    elif court_type == "high":
        if "Telangana" in court_name:
            return TelanganaHighCourtScraper()
        elif "Delhi" in court_name:
            return DelhiHighCourtScraper()
        # Add more high courts as needed

    elif court_type == "supreme":
        return SupremeCourtScraper()

    raise ValueError(f"Unsupported court: {court_type} - {court_name}")
```

---

### Step 4: Scraping Logic (Selenium)

**File**: `core/scrapers/base_scraper.py`

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time

class BaseScraper:
    """
    Base class for all court scrapers
    """

    def __init__(self):
        # Configure Chrome in headless mode
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)

    def fetch_case(self, case_number):
        """
        To be implemented by subclasses
        """
        raise NotImplementedError

    def cleanup(self):
        """
        Close browser
        """
        if self.driver:
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
```

**File**: `core/scrapers/ecourt_scraper.py`

```python
from .base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

class ECourtScraper(BaseScraper):
    """
    Scraper for eCourts (District Courts)
    """

    BASE_URL = "https://services.ecourts.gov.in/ecourtindia_v6/"

    def fetch_case(self, case_number):
        try:
            # Navigate to the site
            self.driver.get(self.BASE_URL)

            # Wait for and click on "Case Status" link
            case_status_link = self.wait.until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Case Status"))
            )
            case_status_link.click()

            # Fill case number
            case_number_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "case_no"))
            )
            case_number_input.send_keys(case_number)

            # Click search button
            search_button = self.driver.find_element(By.ID, "search_button")
            search_button.click()

            # Wait for results to load
            time.sleep(3)

            # Check for "No records found"
            page_source = self.driver.page_source
            if "No Record Found" in page_source:
                raise CaseNotFoundException(f"Case {case_number} not found")

            # Get the HTML
            html = self.driver.page_source

            return {
                'html': html,
                'source': 'ecourts',
                'case_number': case_number
            }

        finally:
            self.cleanup()
```

---

### Step 5: Parsing

**File**: `core/parsers/ecourt_parser.py`

```python
from bs4 import BeautifulSoup
from datetime import datetime

def parse_ecourt_data(raw_html):
    """
    Parse eCourts HTML to extract structured data
    """
    soup = BeautifulSoup(raw_html, 'html.parser')

    # Extract case details
    case_data = {}

    # Title / Case Type
    case_type_elem = soup.find('td', text='Case Type')
    if case_type_elem:
        case_data['case_type'] = case_type_elem.find_next_sibling('td').text.strip()

    # Filing Date
    filing_date_elem = soup.find('td', text='Filing Date')
    if filing_date_elem:
        date_str = filing_date_elem.find_next_sibling('td').text.strip()
        case_data['filing_date'] = parse_date(date_str)

    # Status
    status_elem = soup.find('td', text='Case Status')
    if status_elem:
        case_data['status'] = status_elem.find_next_sibling('td').text.strip()

    # Extract hearings
    hearings = []
    hearing_table = soup.find('table', {'id': 'hearings_table'})
    if hearing_table:
        rows = hearing_table.find_all('tr')[1:]  # Skip header
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 3:
                hearings.append({
                    'hearing_date': parse_date(cols[0].text.strip()),
                    'purpose': cols[1].text.strip(),
                    'judge': cols[2].text.strip()
                })

    case_data['hearings'] = hearings

    return case_data

def parse_date(date_str):
    """
    Parse various date formats
    """
    formats = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None
```

---

### Step 6: Save into Database

**File**: `core/services/case_service.py`

```python
from core.models import Case, Hearing, Party, ActivityLog
from django.db import transaction

@transaction.atomic
def save_fetched_case(parsed_data, fetch_job):
    """
    Save parsed case data to database
    """
    # Check if case already exists
    case = Case.objects.filter(
        case_number=fetch_job.case_number
    ).first()

    if not case:
        # Create new case
        case = Case.objects.create(
            case_number=fetch_job.case_number,
            title=parsed_data.get('case_type', 'Unknown'),
            case_type=parsed_data.get('case_type'),
            status=parsed_data.get('status', 'Active'),
            filing_date=parsed_data.get('filing_date'),
            court_name=fetch_job.court_name,
            court_type=fetch_job.court_type,
            last_fetched_at=timezone.now()
        )
    else:
        # Update existing case
        case.status = parsed_data.get('status', case.status)
        case.last_fetched_at = timezone.now()
        case.save()

    # Save hearings
    for hearing_data in parsed_data.get('hearings', []):
        Hearing.objects.update_or_create(
            case=case,
            hearing_date=hearing_data['hearing_date'],
            defaults={
                'purpose': hearing_data.get('purpose', ''),
                'judge': hearing_data.get('judge', ''),
                'status': 'scheduled'
            }
        )

    # Log activity
    ActivityLog.objects.create(
        case=case,
        activity_type='case_fetched',
        description=f'Case details fetched from {fetch_job.court_name}',
        timestamp=timezone.now()
    )

    return case
```

---

### Step 7: Update Job Status

This happens in the Celery task (Step 2) after successful parsing.

---

## 9. 🎨 Frontend UX Flow

### Step 1: User Input Form

**Component**: `FetchCaseForm.tsx`

```typescript
import { useState } from 'react';

export function FetchCaseForm() {
  const [caseNumber, setCaseNumber] = useState('');
  const [courtName, setCourtName] = useState('');
  const [courtType, setCourtType] = useState('high');

  const handleSubmit = async (e) => {
    e.preventDefault();

    const response = await fetch('/api/cases/fetch/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        case_number: caseNumber,
        court_name: courtName,
        court_type: courtType
      })
    });

    const data = await response.json();
    // Start polling for status
    pollJobStatus(data.job_id);
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        placeholder="Case Number (e.g., CRL.P.No.1234/2023)"
        value={caseNumber}
        onChange={(e) => setCaseNumber(e.target.value)}
      />

      <select value={courtType} onChange={(e) => setCourtType(e.target.value)}>
        <option value="district">District Court</option>
        <option value="high">High Court</option>
        <option value="supreme">Supreme Court</option>
      </select>

      <input
        placeholder="Court Name (e.g., Telangana High Court)"
        value={courtName}
        onChange={(e) => setCourtName(e.target.value)}
      />

      <button type="submit">Fetch Case</button>
    </form>
  );
}
```

---

### Step 2: Loading State

**Component**: `FetchStatusIndicator.tsx`

```typescript
export function FetchStatusIndicator({ jobId }) {
  const { status, progress } = useFetchJobStatus(jobId);

  if (status === 'pending' || status === 'running') {
    return (
      <div className="loading-state">
        <Spinner />
        <p>🔍 Fetching case details from court website...</p>
        {progress && <ProgressBar value={progress} />}
        <p className="subtext">This may take 5-15 seconds</p>
      </div>
    );
  }

  if (status === 'success') {
    return <SuccessMessage />;
  }

  if (status === 'failed') {
    return <ErrorMessage />;
  }

  return null;
}
```

---

### Step 3: Poll API for Status

**Hook**: `useFetchJobStatus.ts`

```typescript
import { useState, useEffect } from "react";

export function useFetchJobStatus(jobId: number) {
  const [status, setStatus] = useState<string>("pending");
  const [caseId, setCaseId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`/api/cases/fetch/${jobId}/`);
        const data = await response.json();

        setStatus(data.status);

        if (data.status === "success") {
          setCaseId(data.case_id);
          clearInterval(pollInterval);
        } else if (data.status === "failed") {
          setError(data.error_message);
          clearInterval(pollInterval);
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(pollInterval);
  }, [jobId]);

  return { status, caseId, error };
}
```

---

### Step 4: Show Results

**Component**: `CaseFetchSuccess.tsx`

```typescript
export function CaseFetchSuccess({ caseId }) {
  const { data: caseData } = useCaseDetails(caseId);

  if (!caseData) return <LoadingSpinner />;

  return (
    <div className="success-card">
      <h2>✅ Case Found</h2>

      <div className="case-summary">
        <h3>{caseData.case_number}</h3>
        <p><strong>Type:</strong> {caseData.case_type}</p>
        <p><strong>Status:</strong> {caseData.status}</p>
        <p><strong>Court:</strong> {caseData.court_name}</p>
      </div>

      <div className="next-hearing">
        <h4>Next Hearing</h4>
        <p className="date">{caseData.next_hearing_date}</p>
        <p className="judge">Before: {caseData.next_hearing_judge}</p>
      </div>

      <button onClick={() => navigateTo(`/cases/${caseId}`)}>
        View Full Case Details
      </button>
    </div>
  );
}
```

---

## 10. 🚨 Error Handling

### Error Types & Responses

#### 1. Case Not Found

```json
{
  "status": "failed",
  "error": "case_not_found",
  "error_message": "Case number not found on court website. Please verify the case number.",
  "suggestions": [
    "Check if case number format is correct",
    "Verify you selected the right court",
    "Try searching on the court website manually"
  ]
}
```

**Frontend Display:**

```
❌ Case Not Found
The case number could not be found on the court website.
Please check:
• Case number format is correct
• You selected the right court
[Try Again] [Manual Search]
```

---

#### 2. CAPTCHA Required

```json
{
  "status": "failed",
  "error": "captcha_required",
  "error_message": "CAPTCHA verification required by court website",
  "manual_url": "https://services.ecourts.gov.in/..."
}
```

**Frontend Display:**

```
🤖 Human Verification Needed
The court website requires CAPTCHA verification.
[Open Court Website] to search manually
```

---

#### 3. Court Website Down

```json
{
  "status": "failed",
  "error": "site_unavailable",
  "error_message": "Court website is currently unavailable",
  "retry_suggested": true
}
```

**Frontend Display:**

```
⚠️ Court Website Unavailable
The court website is temporarily down.
[Retry] [Try Again Later]
```

---

#### 4. Timeout

```json
{
  "status": "failed",
  "error": "timeout",
  "error_message": "Request timed out after 30 seconds"
}
```

---

#### 5. Invalid Input

```json
{
  "status": "error",
  "error": "validation_error",
  "details": {
    "case_number": ["Case number format is invalid"],
    "court_name": ["This field is required"]
  }
}
```

---

### Retry Strategy

```python
# In Celery task
@shared_task(bind=True, max_retries=3)
def process_fetch_job(self, job_id):
    try:
        # ... fetch logic
        pass
    except (SiteUnavailableException, TimeoutException) as e:
        # Retry with exponential backoff
        raise self.retry(
            exc=e,
            countdown=60 * (2 ** self.request.retries)  # 1min, 2min, 4min
        )
    except (CaseNotFoundException, CaptchaRequiredException) as e:
        # Don't retry these - they won't succeed
        job.status = 'failed'
        job.save()
```

---

## 11. ⚡ Performance Strategy

### Problem:

Scraping is inherently slow (3–10 seconds per request)

### Solutions:

---

### 1. Cache Results

```python
from django.core.cache import cache
from datetime import timedelta

def fetch_case_with_cache(case_number, court_name):
    """
    Check cache before fetching
    """
    cache_key = f"case:{court_name}:{case_number}"

    # Check cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    # Fetch fresh data
    data = scraper.fetch_case(case_number)

    # Cache for 6 hours
    cache.set(cache_key, data, timeout=6*60*60)

    return data
```

**Strategy:**

- Cache successful fetches for 6 hours
- Show "Last updated: X hours ago" to users
- Allow "Refresh" button to bypass cache

---

### 2. Async Jobs (CRITICAL)

```python
# ❌ DON'T: Block the API
def fetch_case(request):
    scraper = get_scraper()
    data = scraper.fetch(case_number)  # Takes 10 seconds!
    return Response(data)

# ✅ DO: Use background jobs
def fetch_case(request):
    job = FetchJob.objects.create(...)
    process_fetch_job.delay(job.id)  # Returns immediately
    return Response({'job_id': job.id})
```

---

### 3. Retry Logic with Backoff

```python
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_fetch_job(self, job_id):
    try:
        # Fetch logic
        pass
    except TemporaryError as exc:
        # Exponential backoff: 60s, 120s, 240s
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries)
        )
```

---

### 4. Rate Limiting

```python
from rest_framework.throttling import UserRateThrottle

class FetchCaseThrottle(UserRateThrottle):
    rate = '10/hour'  # Max 10 fetch requests per hour per user

class FetchCaseView(APIView):
    throttle_classes = [FetchCaseThrottle]
```

**Why?**

- Prevent abuse
- Avoid overloading court servers
- Respect legal/ethical boundaries

---

### 5. Database Indexing

```sql
-- Essential indexes for fetch operations
CREATE INDEX idx_case_number_court ON case(case_number, court_name);
CREATE INDEX idx_fetch_job_status ON fetch_job(status, created_at);
CREATE INDEX idx_case_last_fetched ON case(last_fetched_at);
```

---

### 6. Parallel Scraping (Advanced)

For batch operations (e.g., refresh 100 cases):

```python
from celery import group

def refresh_all_cases(case_ids):
    """
    Refresh multiple cases in parallel
    """
    job = group(
        process_fetch_job.s(case_id)
        for case_id in case_ids
    )
    result = job.apply_async()
    return result
```

---

## 12. 🔐 Legal & Safety Considerations

### 1. Respect robots.txt

```python
from urllib.robotparser import RobotFileParser

def can_scrape(url):
    rp = RobotFileParser()
    rp.set_url(f"{url}/robots.txt")
    rp.read()
    return rp.can_fetch("*", url)
```

**Note:** Most court websites don't have robots.txt, but check anyway.

---

### 2. Rate Limiting

```python
import time
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, max_requests=5, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []

    def wait_if_needed(self):
        now = datetime.now()
        # Remove old requests
        self.requests = [
            req for req in self.requests
            if now - req < timedelta(seconds=self.time_window)
        ]

        if len(self.requests) >= self.max_requests:
            sleep_time = (self.requests[0] + timedelta(seconds=self.time_window) - now).total_seconds()
            time.sleep(sleep_time)

        self.requests.append(now)
```

**Usage:**

```python
rate_limiter = RateLimiter(max_requests=5, time_window=60)

def fetch_case(case_number):
    rate_limiter.wait_if_needed()  # Wait if we've exceeded limit
    # ... proceed with scraping
```

---

### 3. User-Agent & Headers

```python
options = webdriver.ChromeOptions()
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
```

**Why?** Some sites block requests without proper User-Agent.

---

### 4. Don't Bypass CAPTCHA Programmatically

```python
# ❌ DON'T
if captcha_detected:
    solve_with_third_party_service()  # Illegal in many jurisdictions

# ✅ DO
if captcha_detected:
    return {
        'error': 'captcha_required',
        'manual_url': court_url
    }
```

---

### 5. Terms of Service Compliance

- Read court website terms
- Avoid aggressive scraping
- Don't claim data ownership
- Attribute source properly

---

### 6. Data Privacy

```python
# Don't log sensitive data
logger.info(f"Fetching case {case_number[:4]}****")  # Redact

# Encrypt stored data if needed
from cryptography.fernet import Fernet
```

---

## 13. 📈 Future Enhancements

### Phase 2: Auto-Refresh

```python
@periodic_task(run_every=timedelta(hours=24))
def auto_refresh_cases():
    """
    Automatically refresh all active cases
    """
    active_cases = Case.objects.filter(
        status='Active',
        auto_fetch_enabled=True
    )

    for case in active_cases:
        process_fetch_job.delay(case.id)
```

**Benefits:**

- Users always see latest data
- No manual refresh needed

---

### Phase 3: Change Notifications

```python
def check_for_changes(old_case, new_case):
    """
    Detect and notify changes
    """
    if old_case.next_hearing != new_case.next_hearing:
        send_notification(
            user=case.owner,
            message=f"Hearing date changed to {new_case.next_hearing}"
        )
```

**Notification Channels:**

- Email
- SMS (using AWS SNS)
- Push notifications
- In-app alerts

---

### Phase 4: Multi-Court Support

Add scrapers for:

- All 25 High Courts
- District courts across India
- Tribunals (NCLAT, NGT, etc.)

---

### Phase 5: Paid API Integration

When available, integrate with official APIs:

```python
if court_has_official_api(court_name):
    use_official_api()
else:
    use_scraper()
```

---

### Phase 6: Machine Learning Enhancements

- Predict hearing outcomes
- Suggest relevant case laws
- Auto-categorize cases

---

### Phase 7: Analytics Dashboard

```text
📊 Your Cases Dashboard
━━━━━━━━━━━━━━━━━━━━
Total Cases: 45
Active: 32
Upcoming Hearings (7 days): 5
Average Case Age: 2.3 years
```

---

## 14. 🎯 Architecture Summary

### Final Data Flow:

```text
┌──────────────────────────────────────────────────────────┐
│                      USER INTERFACE                       │
│  (Next.js Frontend - Fetch Case Form + Status Display)   │
└────────────┬─────────────────────────────────────────────┘
             │
             │ POST /api/cases/fetch/
             │ { case_number, court_name, court_type }
             ▼
┌──────────────────────────────────────────────────────────┐
│                    API LAYER (Django)                     │
│  - Validate input                                         │
│  - Create FetchJob (status: pending)                      │
│  - Return job_id immediately (202 Accepted)               │
└────────────┬─────────────────────────────────────────────┘
             │
             │ Trigger Celery task
             ▼
┌──────────────────────────────────────────────────────────┐
│              BACKGROUND WORKER (Celery)                   │
│  - Update job status: running                             │
│  - Select appropriate scraper                             │
│  - Execute scraping task                                  │
└────────────┬─────────────────────────────────────────────┘
             │
             │ Fetch case details
             ▼
┌──────────────────────────────────────────────────────────┐
│                  SCRAPER LAYER (Selenium)                 │
│  - Navigate to court website                              │
│  - Fill search form                                       │
│  - Submit and wait for results                            │
│  - Capture HTML                                           │
└────────────┬─────────────────────────────────────────────┘
             │
             │ Raw HTML
             ▼
┌──────────────────────────────────────────────────────────┐
│               PARSER LAYER (BeautifulSoup)                │
│  - Extract case details                                   │
│  - Parse hearing dates                                    │
│  - Identify parties, judges, status                       │
│  - Structure data                                         │
└────────────┬─────────────────────────────────────────────┘
             │
             │ Structured data
             ▼
┌──────────────────────────────────────────────────────────┐
│                DATABASE (PostgreSQL)                      │
│  - Create/Update Case record                              │
│  - Create Hearing records                                 │
│  - Create ActivityLog entry                               │
│  - Update FetchJob (status: success, case_id set)         │
└────────────┬─────────────────────────────────────────────┘
             │
             │ Job complete
             ▼
┌──────────────────────────────────────────────────────────┐
│                 FRONTEND POLLING                          │
│  GET /api/cases/fetch/{job_id}/ every 2 seconds           │
│  - Check job status                                       │
│  - If success: Display case details                       │
│  - If failed: Show error message                          │
└──────────────────────────────────────────────────────────┘
```

---

### Technology Stack:

| Layer               | Technology              | Purpose                      |
| ------------------- | ----------------------- | ---------------------------- |
| **Frontend**        | Next.js + React         | User interface, polling      |
| **API**             | Django REST Framework   | Request handling, validation |
| **Background Jobs** | Celery + Redis          | Async task processing        |
| **Scraping**        | Selenium + ChromeDriver | Browser automation           |
| **Parsing**         | BeautifulSoup4          | HTML parsing                 |
| **Database**        | PostgreSQL              | Data persistence             |
| **Cache**           | Redis                   | Cache fetch results          |
| **Queue**           | Redis                   | Celery broker                |

---

### Key Design Principles:

1. **Never Block the User**: All scraping is async
2. **Fail Gracefully**: Clear error messages, retry logic
3. **Respect the Source**: Rate limiting, robots.txt
4. **Cache Aggressively**: Reduce load on court servers
5. **Monitor Everything**: Log all fetch attempts
6. **Security First**: Don't bypass CAPTCHAs, respect ToS

---

## 💡 Final Thoughts

### What Makes This System Different?

👉 **You're NOT:**

- Fetching from an API
- Getting structured data directly
- Working with developer-friendly tools

👉 **You ARE:**

- Building your own API layer on top of the web
- Simulating human interaction with court websites
- Structuring unstructured data
- Creating value where none existed before

---

### Success Metrics:

- ✅ **Performance**: 90% of fetches complete in < 15 seconds
- ✅ **Reliability**: 85% success rate (accounting for site issues)
- ✅ **User Experience**: Real-time progress feedback
- ✅ **Data Quality**: Accurate parsing of case details
- ✅ **Legal Compliance**: Zero legal issues with scraping

---

### Next Steps:

1. **Implement MVP**: Start with one court (e.g., Telangana High Court)
2. **Test Thoroughly**: Handle all error cases
3. **Deploy to Staging**: Test with real users
4. **Add Monitoring**: Track success rates, errors
5. **Expand Coverage**: Add more courts iteratively

---

## 📚 Related Documentation

- [DB Schema](./DB_SCHEMA.md) - Database structure
- [API Contracts](./API_CONTRACTS.md) - API specifications
- [Architecture](./ARCHITECTURE.md) - Overall system architecture
- [Project Overview](./PROJECT_OVERVIEW.md) - High-level project info

---

**Document Version:** 1.0  
**Last Updated:** April 2026  
**Authors:** Case Intel Team  
**Status:** Design Phase - Ready for Implementation
