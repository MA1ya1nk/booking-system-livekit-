# Hospital Booking API (FastAPI + PostgreSQL)

## Setup

1. Create env file:
   - copy `.env.example` to `.env`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run server:
   - `uvicorn app.main:app --reload`

## Email (payment link, booking, cancellation)

Configure **Resend** for production (e.g. on Render): set `RESEND_API_KEY` and `RESEND_FROM_EMAIL`, and **do not** set SMTP variables on the server. Optional fallbacks: SendGrid, then SMTP (see `.env.example`).

## Create admin user

Run:


## Key endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/services`
- `POST /api/v1/services` (admin only)
- `POST /api/v1/payments/create-order` + `POST /api/v1/payments/verify-and-book` (Razorpay Checkout; dashboard)
- `POST /api/v1/payments/send-payment-link-email` (Razorpay Payment Link + email; booking via webhook)
- `POST /api/v1/payments/webhook` (Razorpay; `payment_link.paid` → create booking)
- `GET /api/v1/appointments/me`
- `PATCH /api/v1/appointments/{id}/cancel`
