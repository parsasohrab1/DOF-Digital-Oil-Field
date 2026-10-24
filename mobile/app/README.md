# OGIM Mobile (Expo)

Mobile client with:

- **Login** — JWT auth via `auth-service`
- **Push notifications** — Expo tokens registered after login
- **Offline mode** — cached alerts and wells data
- **Offline action queue** — acknowledge alerts when connection restores
- **Tabs** — Alerts and Wells summary

## Run

```bash
cd mobile/app
npm install
npm start
```

Set API URL in `app.json` (`expo.extra.apiBaseUrl`), for example:

- Android emulator: `http://10.0.2.2:8000`
- iOS simulator: `http://localhost:8000`
- Real device: `http://<your-lan-ip>:8000`

Default credentials: `operator1` / `operator123`

## Backend endpoints used

- `POST /api/auth/token`
- `POST /api/alert/notifications/devices/register`
- `GET /api/alert/alerts`
- `POST /api/alert/alerts/{alert_id}/acknowledge`
- `GET /api/digital-twin/wells`
- `GET /api/digital-twin/well/{well_name}/3d`
