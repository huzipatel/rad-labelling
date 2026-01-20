# Deployment Guide

This guide covers deploying the UK Advertising Labelling Application to production.

## Quick Start Options

### Option 1: Railway (Recommended - Easiest)

Railway provides simple container hosting with managed PostgreSQL.

1. **Create Railway Account**: Go to [railway.app](https://railway.app) and sign up

2. **Create New Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Connect your GitHub account and select this repository

3. **Add PostgreSQL Database**:
   - In your project, click "New Service" → "Database" → "PostgreSQL"
   - Railway will automatically set `DATABASE_URL`

4. **Add Redis**:
   - Click "New Service" → "Database" → "Redis"
   - Railway will automatically set `REDIS_URL`

5. **Configure Environment Variables**:
   In the backend service settings, add:
   ```
   JWT_SECRET_KEY=<generate-secure-key>
   GSV_API_KEY=<your-google-street-view-api-key>
   GCS_BUCKET_NAME=<your-gcs-bucket>
   GOOGLE_CLIENT_ID=<your-oauth-client-id>
   GOOGLE_CLIENT_SECRET=<your-oauth-client-secret>
   ```

6. **Deploy**: Railway will automatically deploy on every push to main

---

### Option 2: Google Cloud Run + Cloud SQL

Best if you're already using Google Cloud for GCS.

1. **Set up Cloud SQL (PostgreSQL with PostGIS)**:
   ```bash
   # Create instance
   gcloud sql instances create labelling-db \
     --database-version=POSTGRES_15 \
     --tier=db-f1-micro \
     --region=europe-west2

   # Create database
   gcloud sql databases create labelling_db --instance=labelling-db

   # Create user
   gcloud sql users create labelling_user \
     --instance=labelling-db \
     --password=YOUR_PASSWORD
   ```

2. **Build and Push Images**:
   ```bash
   # Configure Docker for GCP
   gcloud auth configure-docker

   # Build and push backend
   docker build -t gcr.io/YOUR_PROJECT/labelling-backend ./backend
   docker push gcr.io/YOUR_PROJECT/labelling-backend

   # Build and push frontend
   docker build -t gcr.io/YOUR_PROJECT/labelling-frontend ./frontend
   docker push gcr.io/YOUR_PROJECT/labelling-frontend
   ```

3. **Deploy to Cloud Run**:
   ```bash
   # Deploy backend
   gcloud run deploy labelling-backend \
     --image gcr.io/YOUR_PROJECT/labelling-backend \
     --platform managed \
     --region europe-west2 \
     --allow-unauthenticated \
     --add-cloudsql-instances YOUR_PROJECT:europe-west2:labelling-db \
     --set-env-vars "DATABASE_URL=postgresql://labelling_user:PASSWORD@/labelling_db?host=/cloudsql/YOUR_PROJECT:europe-west2:labelling-db"

   # Deploy frontend
   gcloud run deploy labelling-frontend \
     --image gcr.io/YOUR_PROJECT/labelling-frontend \
     --platform managed \
     --region europe-west2 \
     --allow-unauthenticated
   ```

---

### Option 3: DigitalOcean App Platform

1. Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
2. Create new app from GitHub
3. Add managed PostgreSQL database
4. Configure environment variables
5. Deploy

---

## CI/CD with GitHub Actions

The repository includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that:
- Builds Docker images on every push to main
- Pushes images to GitHub Container Registry
- Deploys to Railway or Google Cloud Run

### Setup GitHub Actions:

1. **Enable GitHub Packages**: Go to repo Settings → Actions → General → Enable "Read and write permissions"

2. **Add Secrets** (Settings → Secrets and variables → Actions):
   - For Railway: `RAILWAY_TOKEN`
   - For GCP: `GCP_SA_KEY` (service account JSON)
   - Add all environment variables as secrets

3. **Add Variables** (Settings → Secrets and variables → Actions → Variables):
   - `DEPLOY_TARGET`: Set to `railway` or `gcp`
   - `GCP_REGION`: (optional) defaults to `europe-west2`

---

## Database Migrations

Run migrations after deployment:

```bash
# Railway
railway run alembic upgrade head

# Cloud Run (connect via Cloud SQL Proxy)
./cloud_sql_proxy -instances=PROJECT:REGION:INSTANCE=tcp:5432 &
DATABASE_URL=postgresql://user:pass@localhost:5432/db alembic upgrade head
```

---

## Data Persistence

- **Database**: Use managed PostgreSQL (Railway, Cloud SQL, or similar)
- **Images/Files**: Store in Google Cloud Storage (already configured)
- **Redis**: Use managed Redis for task queue

Your data will persist across deployments as long as you use managed services.

---

## Monitoring

- **Railway**: Built-in logs and metrics
- **Cloud Run**: Use Cloud Logging and Cloud Monitoring
- **Custom**: Add Sentry for error tracking

---

## Costs Estimate

| Service | Railway | GCP |
|---------|---------|-----|
| Backend | $5-20/mo | $0-50/mo (pay per use) |
| Frontend | $5-20/mo | $0-50/mo |
| Database | $5-15/mo | $10-50/mo |
| Redis | $5/mo | $10/mo |
| **Total** | **~$20-60/mo** | **~$20-160/mo** |

Railway is simpler and more predictable pricing. GCP can be cheaper for low traffic but more complex.





