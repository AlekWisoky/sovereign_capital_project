# x∆v Web Deployment

## Local development

```bash
npm install
npm run dev:web
```

## Static export

```bash
npm install
npm run build:web
```

The static output is generated into `dist/`.

## Netlify

Build command:

```bash
npm ci && npm run build:web
```

Publish directory:

```bash
dist
```

Required environment variables:

- `EXPO_PUBLIC_DEFAULT_BACKEND_URL`
- `EXPO_PUBLIC_DEFAULT_CHAIN`
- `EXPO_PUBLIC_APP_ENV`
- `EXPO_PUBLIC_APP_URL`
- `EXPO_PUBLIC_WALLETCONNECT_PROJECT_ID` (optional)

SPA routing is handled by both `netlify.toml` and `public/_redirects`.
