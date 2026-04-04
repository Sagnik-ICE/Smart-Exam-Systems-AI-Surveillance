# Smart Exam Systems and AI Surveillance

End-to-end AI proctored examination platform with role-based governance, behavior telemetry, eye-tracking analysis, dynamic risk scoring, analytics exports, and report generation.

## Product Snapshot

- Backend: FastAPI + SQLAlchemy + PostgreSQL/SQLite
- Frontend: React 18 + Vite + Axios
- Vision stack: YOLO + MediaPipe FaceLandmarker
- Auth model: JWT bearer token with role guards
- Roles: authority, teacher, student
- Reporting: CSV + PDF exports for analytics and result sheets

## Table of Contents

1. Vision and Scope
2. Feature Matrix by Role
3. Architecture
4. Repository Layout
5. Tech Stack and Versions
6. Runtime Prerequisites
7. Quick Start
8. Manual Local Setup
9. Environment Configuration
10. Authentication and Authorization
11. Exam Lifecycle
12. Behavior and Vision Monitoring
13. Scoring Engine Details
14. API Reference
15. Request and Response Contracts
16. Data Model
17. Testing Strategy
18. Operations Runbook
19. Troubleshooting
20. Security and Privacy
21. Performance Notes
22. Deployment Guidance
23. Limitations
24. Roadmap Suggestions

## Vision and Scope

This project provides a production-style exam proctoring workflow where:

1. Authority users govern account approval and access state.
2. Teachers create rooms, publish papers, monitor risk, and evaluate outcomes.
3. Students complete one controlled attempt while telemetry and vision alerts are captured.

The platform is designed for academic integrity workflows, not punitive auto-conviction. Risk outputs are intended as decision support for human reviewers.

## Feature Matrix by Role

### Authority

- Review pending users.
- Approve or reject users.
- Enable or disable access.
- Reset user passwords.
- Manage users (including deletion cascades).
- Export student report PDF.

### Teacher

- Create rooms and exam papers.
- View own rooms and resolve room IDs.
- Monitor student submissions and event replay.
- Export CSV/PDF analytics.
- Mark submissions and set pass/fail/pending.
- Download result sheet and detail reports.

### Student

- Log in with institution user code.
- Join assigned room.
- Start one submission per exam.
- Send event batches during exam.
- Send webcam frames for vision analysis.
- Submit answers with final risk output.

## Architecture

### Logical Flow

```mermaid
flowchart LR
	A[Student Browser] -->|Login + JWT| B[FastAPI Auth]
	A -->|Events batch| C[Events Router]
	A -->|Frame upload| D[Vision Router]
	D --> E[Eye Tracking Service]
	C --> F[(DB)]
	E --> F
	A -->|Submit answers| G[Submissions Router]
	G --> H[Scoring + AI/Similarity]
	H --> F
	I[Teacher Browser] --> J[Analytics Router]
	J --> F
	K[Authority Browser] --> L[Management Router]
	L --> F
```

### Runtime Components

- Frontend: http://localhost:5173 (fallback often http://localhost:5174)
- Backend: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs
- Database (recommended): PostgreSQL 16 container on 5432

## Repository Layout

```text
AI Project/
	backend/
		app/
			main.py
			models.py
			schemas.py
			settings.py
			middleware.py
			routers/
			services/
		requirements.txt
		requirements-dev.txt
		tests/
	frontend/
		src/
			components/
			lib/
			styles.css
		package.json
		vite.config.js
	docker-compose.postgres.yml
	run_project.py
	start-demo.ps1
	stop-demo.ps1
	health-check.ps1
	README.md
```

## Tech Stack and Versions

### Backend dependencies

- fastapi==0.115.0
- uvicorn[standard]==0.30.6
- sqlalchemy==2.0.35
- pydantic==2.9.2
- python-multipart==0.0.9
- scikit-learn==1.5.2
- numpy==2.1.1
- PyJWT==2.9.0
- reportlab==4.2.2
- psycopg2-binary==2.9.9
- opencv-python==4.8.1.78
- mediapipe==0.10.5
- ultralytics==8.3.5

### Backend dev dependencies

- pytest==8.3.3
- httpx==0.27.2

### Frontend dependencies

- react==18.3.1
- react-dom==18.3.1
- axios==1.7.7
- vite==5.4.8
- vitest==2.1.3
- @testing-library/react==16.0.1
- @testing-library/jest-dom==6.6.3
- jsdom==25.0.1

## Runtime Prerequisites

- Windows 10/11 with PowerShell 5.1+
- Python 3.11+
- Node.js 18+
- npm 9+
- Docker Desktop

## Quick Start

Single command launcher:

```powershell
python run_project.py
```

Launcher behavior:

1. Starts PostgreSQL service from compose file.
2. Waits for DB health.
3. Seeds demo data if user table is empty.
4. Ensures default ADMIN account exists.
5. Starts backend Uvicorn on 8000.
6. Starts frontend Vite server.
7. Executes health-check script.

## Manual Local Setup

### 1) Prepare environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
pip install -r backend\requirements-dev.txt
```

### 2) Install frontend packages

```powershell
cd frontend
npm install
cd ..
```

### 3) Configure backend env file

Copy backend/.env.example to backend/.env and update values.

### 4) Start PostgreSQL

```powershell
docker compose -f docker-compose.postgres.yml up -d
```

### 5) Seed demo records (optional)

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.seed_demo
..\.venv\Scripts\python.exe -m app.ensure_default_admin
cd ..
```

### 6) Start backend

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### 7) Start frontend

In a second terminal:

```powershell
cd frontend
npm run dev
```

### 8) Run health check

```powershell
powershell -ExecutionPolicy Bypass -File .\health-check.ps1
```

## Environment Configuration

Important variables in backend/.env:

| Variable | Description | Example |
| --- | --- | --- |
| DATABASE_URL | SQLAlchemy connection URL | postgresql+psycopg2://exam_user:exam_pass@127.0.0.1:5432/exam_system |
| JWT_SECRET_KEY | JWT signing key | change-this-secret-before-production |
| CORS_ALLOWED_ORIGINS | Comma-separated CORS allow list | http://localhost:5173,http://127.0.0.1:5173 |
| RATE_LIMIT_WINDOW_SECONDS | Rate-limit window size | 60 |
| RATE_LIMIT_MAX_REQUESTS | Max requests per client/path/window | 180 |
| MAX_REQUEST_BODY_BYTES | Max request payload size | 1048576 |
| REPORT_BRAND_NAME | Brand label in generated reports | AI Smart Exam System |
| AI_CLASSIFIER_URL | Optional external classifier endpoint | (empty by default) |
| AI_CLASSIFIER_TIMEOUT_SECONDS | External classifier timeout | 3 |

## Authentication and Authorization

### Auth model

- JWT bearer token in Authorization header.
- Token issuance from /auth/login-id and /auth/login.
- Token includes user id and role claims.

### Access checks

- Role gate helper enforces route-level role constraints.
- User profile approval and active state are validated on protected calls.
- Authority has governance-level access; teacher and student scopes are restricted.

### Password storage

- PBKDF2-HMAC-SHA256 with per-password random salt.
- Password hash format: salt$hash.

## Exam Lifecycle

1. Teacher creates room and exam paper.
2. Student resolves room and starts submission.
3. Student telemetry and vision frames are ingested while status is in_progress.
4. Student submits answers.
5. Backend computes behavior risk and answer-analysis risk.
6. Final score and risk band are persisted.
7. Teacher reviews analytics and grading panels.

One-attempt policy:

- If an earlier submission for the same student+exam is submitted, a new start is blocked.
- If status is in_progress, same submission can be resumed.

## Behavior and Vision Monitoring

### Behavior telemetry

- Events arrive through /events/batch with strict validation.
- Each event captures event_type, timestamp_ms, metadata.
- Event ingestion is denied after submission closes.

### Vision service

- Endpoint: /vision/process-frame
- Input: base64 webcam frame and submission_id
- Runtime: YOLO person detection + MediaPipe landmark analysis
- Output: face/gaze detections + alert list

Alert examples:

- looking_left
- looking_right
- looking_up
- looking_down
- no_face_detected
- multiple_people
- no_person

The frontend transforms these alerts into warning UI and persists eye_movement_alert events.

## Scoring Engine Details

### Behavior score

Behavior score is computed from weighted components including:

- tab/focus events
- paste behavior
- typing pattern
- answer-change velocity
- fullscreen compliance
- rapid completion ratio
- webcam anomalies
- eye movement signal

### Dynamic thresholds

Base thresholds:

- suspicious: 20.0
- high risk: 50.0

Adjustments:

- question_count >= 8: suspicious +3, high +5
- duration >= 90 minutes: suspicious +2, high +4
- duration <= 20 minutes: suspicious -1

Band mapping:

- score <= suspicious threshold => Safe
- score <= high threshold => Suspicious
- otherwise => High Risk

### Final merged score

Final score blend at submission:

- 0.65 * behavior risk
- 0.20 * answer similarity risk
- 0.15 * AI-style risk

Final band thresholds:

- <= 30 => Safe
- <= 60 => Suspicious
- > 60 => High Risk

## API Reference

Base URL: http://127.0.0.1:8000

### Health

- GET /health

### Auth

- POST /auth/signup
- POST /auth/login-id
- POST /auth/login
- GET /auth/teachers
- GET /auth/me
- PATCH /auth/me
- POST /auth/change-password

### Rooms

- POST /rooms
- GET /rooms/mine
- GET /rooms/resolve/{room_id}
- DELETE /rooms/{room_id}
- GET /rooms/{room_id}/paper
- PUT /rooms/{room_id}/paper

### Exams

- POST /exams
- GET /exams/{exam_id}

### Submissions

- POST /submissions/start
- POST /submissions/{submission_id}/submit

### Events

- POST /events/batch

### Analytics

- GET /analytics/teacher/exams
- GET /analytics/exam/{exam_id}
- GET /analytics/exam/{exam_id}/answers
- POST /analytics/submission/{submission_id}/mark
- GET /analytics/exam/{exam_id}/export.csv
- GET /analytics/exam/{exam_id}/export.pdf
- GET /analytics/exam/{exam_id}/result-sheet.pdf
- GET /analytics/submission/{submission_id}/detail.pdf

### Management

- GET /management/pending
- POST /management/approve/{user_id}
- GET /management/users
- POST /management/access/{user_id}
- POST /management/reset-password/{user_id}
- DELETE /management/users/{user_id}
- GET /management/users/{user_id}/student-report.pdf
- POST /management/create-user

### Vision

- POST /vision/process-frame
- POST /vision/reset-tracker
- GET /vision/health

Swagger and ReDoc:

- /docs
- /redoc

## Request and Response Contracts

### Login with institution ID

Request:

```json
{
	"user_code": "TCH-DEMO-001",
	"password": "Teacher@123"
}
```

Response (shape):

```json
{
	"access_token": "jwt-token",
	"token_type": "bearer",
	"user": {
		"id": 1,
		"name": "Teacher Demo",
		"email": "teacher.demo@local",
		"role": "teacher",
		"profile": {
			"user_id": 1,
			"department": "CSE",
			"user_code": "TCH-DEMO-001",
			"contact_number": "1111111111",
			"approval_status": "approved",
			"is_active": true,
			"assigned_teacher_id": null
		}
	}
}
```

### Start submission

```json
{
	"exam_id": 35
}
```

### Batch event ingestion

```json
{
	"submission_id": 108,
	"events": [
		{
			"event_type": "paste",
			"timestamp_ms": 32901,
			"metadata": {
				"char_count": 120
			}
		}
	]
}
```

### Submit exam

```json
{
	"answers": {
		"q1": "Answer text..."
	},
	"time_taken_seconds": 1090
}
```

### Vision frame processing

```json
{
	"submission_id": 108,
	"frame_base64": "<base64-jpeg-or-png>"
}
```

## Data Model

Core tables:

- users
- user_profiles
- exams
- exam_rooms
- submissions
- behavior_events
- submission_reviews
- submission_question_marks
- audit_logs

Highlights:

- Exam questions are stored as JSON payload in exams.questions_json.
- Answer payload is stored in submissions.answers_json.
- Behavior events are append-only event stream rows.
- Audit logs store actor/action/entity trail.

## Testing Strategy

### Frontend tests

```powershell
cd frontend
npm run test
```

### Frontend build validation

```powershell
cd frontend
npm run build
```

### Backend tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests -q
```

Current backend test modules include:

- tests/test_auth_and_permissions.py
- tests/test_management_rooms.py
- tests/test_submission_flow.py

## Operations Runbook

### Start full demo stack

```powershell
python run_project.py
```

### Health check

```powershell
powershell -ExecutionPolicy Bypass -File .\health-check.ps1
```

### Stop app processes only

```powershell
powershell -ExecutionPolicy Bypass -File .\stop-demo.ps1
```

### Stop app plus PostgreSQL container

```powershell
powershell -ExecutionPolicy Bypass -File .\stop-demo.ps1 -IncludeDatabase
```

## Troubleshooting

### Repeated 404 on /analytics/exam/{id}

Likely causes:

- exam does not exist
- exam exists but belongs to another teacher
- exam has zero submissions and dashboard endpoint returns not-found state

### Frontend unavailable after startup

- Check if Node is in PATH.
- Confirm frontend/node_modules exists.
- Verify no firewall/process blocks on 5173/5174.

### Backend unavailable on 8000

- Confirm virtual environment and dependencies are installed.
- Check for stale process already occupying 8000.
- Confirm DB connectivity if PostgreSQL mode is enabled.

### Vision endpoint failing

- Verify opencv-python, mediapipe, ultralytics installed.
- Verify webcam permission in browser.
- Ensure first-time model download can reach external network.

### CORS rejection

- Add actual frontend origin to CORS_ALLOWED_ORIGINS.

### 429 responses

- RateLimitMiddleware may block burst traffic by client+path.
- Tune RATE_LIMIT_WINDOW_SECONDS and RATE_LIMIT_MAX_REQUESTS only if required.

## Security and Privacy

- JWT-based authentication with role checks.
- PBKDF2 password hashing with per-secret salt.
- Request size cap and rate limiting middleware.
- Access and approval state checks before protected route execution.
- Audit logs for sensitive actions (login, approvals, password reset, submissions).

Privacy expectations:

- Vision processing is frame analysis driven.
- No continuous server-side video recording pipeline is implemented in current code.
- Alerts and metadata are used for behavior analytics and review.

## Performance Notes

- Vision processing is CPU/GPU intensive relative to standard API operations.
- Lower-end systems may need reduced frame frequency from frontend.
- PostgreSQL is recommended for realistic concurrent usage.
- SQLite is intended for quick local fallback.

## Deployment Guidance

Minimum production recommendations:

1. Set strong JWT secret and rotate periodically.
2. Replace default demo/admin credentials immediately.
3. Serve backend behind HTTPS reverse proxy.
4. Restrict CORS to known domains.
5. Add centralized logs and uptime monitoring.
6. Add backup and restore procedures for database.
7. Add CI gates for tests and builds before deploy.

## Limitations

- Eye/gaze confidence can vary by camera quality, light, and angle.
- Dynamic risk score is probabilistic and not a direct proof of cheating.
- No migration framework configured yet.
- Some behavior quality depends on browser support and user hardware.

## Roadmap Suggestions

1. Add Alembic migrations and versioned schema rollout.
2. Add CI workflow for backend tests, frontend tests, and build checks.
3. Add role-based end-to-end test suite.
4. Add observability dashboards for API and vision metrics.
5. Add staged environment configuration profiles.

---

For demos: use python run_project.py, wait for READY FOR DEMO from health-check.ps1, then sign in with seeded credentials.