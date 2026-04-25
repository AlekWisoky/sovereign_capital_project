# x∆v Mobile ↔ Backend Sync Guide

This export ships the upgraded backend and the web-first Expo mobile app together.

## Backend on VPS
- Run the backend behind HTTPS on your VPS.
- Set `VICTOR_CORS_ALLOW_ORIGINS` to the exact Netlify/web app origin(s).
- Keep `VICTOR_ADMIN_KEY` configured for operator mutations.

Example backend origin:
- `https://api.yourdomain.com`

## Mobile / Web frontend
Set these in `mobile/.env` for local dev or in Netlify environment variables:

- `EXPO_PUBLIC_DEFAULT_BACKEND_URL=https://api.yourdomain.com`
- `EXPO_PUBLIC_DEFAULT_CHAIN=ethereum`
- `EXPO_PUBLIC_APP_ENV=production`
- `EXPO_PUBLIC_APP_URL=https://your-netlify-site.netlify.app`

## Realtime
The mobile/web app derives websocket URLs from the backend base URL automatically:
- `https://api.yourdomain.com` → `wss://api.yourdomain.com/ws`
- `https://api.yourdomain.com` → `wss://api.yourdomain.com/ws/summary?...`

## Operator auth
- Web/mobile operator mutations send `X-Admin-Key`.
- Web uses a browser-safe storage fallback.
- Native uses secure storage where available.
