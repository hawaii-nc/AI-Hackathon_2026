# AWS Deployment Guide for Kōkua

This guide deploys the `frontend-ui/` static site to S3 + CloudFront and the `backend/` FastAPI app to Elastic Beanstalk.

## 1. Frontend: S3 Static Hosting

1. Build or upload the static files from `frontend-ui/` as-is.
2. Create an S3 bucket for the site, for example `kokua-frontend-prod`.
3. Upload these files to the bucket root:
   - `index.html`
   - `console.html`
   - `support.js`
   - any assets in `screenshots/` or `uploads/` if you need them available publicly
4. In the bucket settings, enable static website hosting if you want the S3 endpoint directly for testing.
5. Set the index document to `index.html`.

Recommended bucket settings:
- Block public access for the production bucket if CloudFront will be the only public entry point.
- Use an Origin Access Control or Origin Access Identity with CloudFront.

## 2. Frontend: CloudFront

1. Create a CloudFront distribution.
2. Set the origin to the S3 bucket.
3. Prefer the S3 REST endpoint with Origin Access Control rather than the public website endpoint.
4. Set the default root object to `index.html`.
5. Add `index.html` and `console.html` to the behavior cache keys only if you have a special caching policy; otherwise use a standard static site cache policy.
6. Attach an ACM certificate if you want a custom domain.
7. Point your domain to the CloudFront distribution with Route 53 or your DNS provider.

If your site is served from CloudFront, set the backend CORS allowlist to include the CloudFront domain, for example:

```bash
FRONTEND_ORIGINS=https://d123example.cloudfront.net
```

## 3. Backend: Elastic Beanstalk

1. Create a new Elastic Beanstalk application.
2. Choose the Python platform.
3. Deploy the contents of `backend/`.
4. Elastic Beanstalk will use the `Procfile` at the repository root of the backend to start the app.
5. Ensure the application listens on port `8000` and host `0.0.0.0`.

The included Procfile is:

```procfile
web: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 4. Environment Variables in AWS Parameter Store

Store secrets in Systems Manager Parameter Store and inject them into Elastic Beanstalk as environment variables.

Recommended parameters:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_PROJECT_ID`
- `FRONTEND_ORIGINS`

Example values:

```text
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=your-openai-key
GOOGLE_PROJECT_ID=your-gcp-project-id
FRONTEND_ORIGINS=https://d123example.cloudfront.net
```

For Elastic Beanstalk, set them in the environment configuration or wire them in with a deployment hook that reads from Parameter Store.

## 5. CORS

The backend reads `FRONTEND_ORIGINS` as a comma-separated allowlist.

Examples:

```text
FRONTEND_ORIGINS=http://localhost:5500,https://d123example.cloudfront.net
```

During local development, keep localhost entries in the list. In production, keep only the CloudFront and any approved custom domains.

## 6. Deployment Checklist

1. Upload `frontend-ui/` to S3.
2. Point CloudFront to the S3 bucket.
3. Deploy `backend/` to Elastic Beanstalk.
4. Set all environment variables in Parameter Store or Elastic Beanstalk environment settings.
5. Update `API_BASE` in the frontend to your Elastic Beanstalk or API domain.
6. Verify CORS by loading the CloudFront site and testing `POST /api/upload-notes`, `POST /api/match`, and `POST /api/referral`.
