# UK Advertising Location Labelling Application

A full-stack application for labelling advertising locations across the UK, built with FastAPI, React, PostgreSQL/PostGIS, and Google Street View integration.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  React Frontend │────▶│  FastAPI Backend│────▶│ PostgreSQL/     │
│  (Gov.UK Design)│     │                 │     │ PostGIS         │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Google   │   │ Google   │   │ Twilio   │
        │ Cloud    │   │ Street   │   │ WhatsApp │
        │ Storage  │   │ View API │   │ API      │
        └──────────┘   └──────────┘   └──────────┘
```

## Features

### User Roles
- **Labeller**: View and complete assigned labelling tasks
- **Labelling Manager**: Upload data, assign tasks, view performance reports
- **Admin**: Full system access including user management

### Core Functionality
- Upload spreadsheets of advertising locations (bus stops, phone boxes, street hubs, advertising hoardings)
- Enhance data with council boundaries, road classifications, and combined authorities using Ordnance Survey shapefiles
- Download Google Street View images (4 headings per location)
- Interactive labelling interface with GSV embed and snapshot capability
- Performance tracking with RAG status indicators
- Export labelling results to CSV and images to ZIP
- WhatsApp notifications on task completion

## Prerequisites

- Docker and Docker Compose
- Google Cloud Platform account with:
  - Street View Static API enabled
  - Street View JavaScript API enabled
  - Cloud Storage bucket
  - Service account credentials
- Twilio account (for WhatsApp notifications)
- Ordnance Survey shapefiles for:
  - Council boundaries
  - Road classifications
  - Combined authorities

## Quick Start

### 1. Clone and Configure

```bash
# Copy environment template (Windows)
copy backend\env.example.txt backend\.env

# Or on Linux/Mac
cp backend/env.example.txt backend/.env

# Edit backend/.env with your credentials
```

### 2. Start Services

```bash
# Start all services with Docker Compose
docker-compose up -d

# Run database migrations
docker-compose exec backend alembic upgrade head
```

### 3. Load Spatial Data

Load your Ordnance Survey shapefiles into the PostGIS database:

```bash
# Connect to database
docker-compose exec db psql -U postgres -d labelling_db

# Load shapefiles using shp2pgsql or ogr2ogr
```

### 4. Access the Application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Development

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

### Celery Worker (for background tasks)

```bash
cd backend
celery -A app.tasks.celery_tasks worker --loglevel=info
```

## Environment Variables

### Backend (.env)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GSV_API_KEY` | Google Street View API key |
| `GCS_BUCKET_NAME` | Google Cloud Storage bucket name |
| `GCS_CREDENTIALS_PATH` | Path to GCS service account JSON |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp number |
| `REDIS_URL` | Redis connection URL |
| `JWT_SECRET_KEY` | Secret key for JWT tokens |

### Frontend (.env)

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend API URL |
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `VITE_GSV_API_KEY` | Google Street View API key |

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login with email/password
- `GET /api/v1/auth/google` - Google OAuth login
- `GET /api/v1/auth/me` - Get current user

### Tasks
- `GET /api/v1/tasks` - List all tasks (manager)
- `GET /api/v1/tasks/my-tasks` - List assigned tasks
- `POST /api/v1/tasks/{id}/assign` - Assign task to labeller
- `POST /api/v1/tasks/bulk-assign` - Bulk assign tasks
- `POST /api/v1/tasks/generate` - Generate tasks from data

### Labelling
- `GET /api/v1/labelling/task/{id}/location/{index}` - Get location for labelling
- `POST /api/v1/labelling/task/{id}/location/{loc_id}/label` - Save label
- `POST /api/v1/labelling/task/{id}/location/{loc_id}/snapshot` - Save snapshot

### Exports
- `GET /api/v1/exports/csv/{type_id}` - Export labels to CSV
- `GET /api/v1/exports/images/{type_id}` - Export images to ZIP

### Admin
- `GET /api/v1/admin/performance` - Get labeller performance report
- `GET /api/v1/admin/stats` - Get system statistics

## Database Schema

Key tables:
- `users` - User accounts and roles
- `location_types` - Types of advertising locations
- `locations` - Individual advertising locations
- `tasks` - Labelling tasks (by type and council)
- `labels` - Labelling results
- `gsv_images` - Street View images
- `council_boundaries` - Council boundary polygons (PostGIS)
- `combined_authorities` - Combined authority polygons
- `road_classifications` - Road classification lines

## Labelling Workflow

1. **Manager uploads spreadsheet** with location data
2. **System enhances data** with council/road information
3. **Manager generates tasks** (one per council)
4. **Manager assigns tasks** to labellers
5. **System downloads GSV images** for assigned tasks
6. **Labeller completes labelling** using images and GSV embed
7. **Manager exports results** as CSV/ZIP
8. **WhatsApp notification** sent on task completion

## License

Proprietary - All rights reserved

