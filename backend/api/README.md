# Hospital Booking API (FastAPI + PostgreSQL)

## Setup

1. Create env file:
   - copy `.env.example` to `.env`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run server:
   - `uvicorn app.main:app --reload`

## Create admin user

Run:

`python -m app.scripts.create_admin`

Default admin credentials:
- email: `admin@example.com`
- password: `admin123`

## Key endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/services`
- `POST /api/v1/services` (admin only)
- `POST /api/v1/appointments`
- `GET /api/v1/appointments/me`
- `PATCH /api/v1/appointments/{id}/cancel`
