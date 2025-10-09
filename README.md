## Bould Size Recommender (Backend)

FastAPI orchestrator that calls two local services:
- Garment Measurement API (HRNet) → size scale per XS–XXL
- Body Measurements API → body dimensions from a user image and height

Features: JWT token endpoint, API key guard, rate limiting, in-memory cache, structured logging, versioned routes, graceful failure, Docker/Compose, tests.

### Environment
- API_KEY (default: change-me)
- OPENAI_API_KEY (optional)
- GARMENTS_API_BASE (default: http://garments_api:8000/v1 in compose)
- BODY_API_BASE (default: http://body_api:8000/api/v1 in compose)
- JWT_SECRET (default: dev-secret)
- RATE_LIMIT_PER_MIN (default: 60)
- RATE_LIMIT_BURST (default: 30)
- CACHE_TTL_SECONDS (default: 600)
- NANO_API_BASE (default: https://api.kie.ai)
- NANO_API_KEY (required for nanobanana)
- NANO_MODEL (default: google/nano-banana-edit)

### Run locally
```bash
cd bould-size-recommender
docker compose up --build
```

### Auth
- Get JWT: `POST /v1/auth/token`
- Use `x-api-key` or `Authorization: Bearer <API_KEY>` to access orchestrator endpoints.

### Recommend
`POST /v1/recommend` with x-api-key header. See PowerShell example earlier.

### Try-on (Mock)
`POST /v1/try-on` with two files and x-api-key header. Returns `/files/...` URL.

### Try-on (Nanobanana createTask)
`POST /v1/try-on/nanobanana/create-task` with JSON body:
```json
{
  "prompt": "turn this photo...",
  "image_urls": ["https://example.com/user.jpg", "https://example.com/garment.jpg"],
  "output_format": "png",
  "image_size": "1:1",
  "callBackUrl": "https://your-domain.com/api/callback"
}
```
Requires `NANO_API_KEY`. Response includes `{ code, message, data: { taskId } }`.

### Tests
```bash
pip install -r requirements.txt
pytest -q
```
