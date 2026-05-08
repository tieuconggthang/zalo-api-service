# 🚀 Zalo API Service (OpenZCA)

Public API service for Zalo messaging automation. Built with FastAPI and OpenZCA CLI.

## ✨ Features

- 🔐 **Web QR Login** - Auto-generate and display QR code in browser
- 📨 **Send Messages** - Send text to users by phone number
- 🔍 **User Lookup** - Find users by phone number
- 👥 **Friend/Group List** - Get all friends and groups
- 🌐 **CORS Support** - Cross-origin requests enabled
- 📊 **Auto Documentation** - Swagger UI at `/docs`

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/tieuconggthang/zalo-auto.git
cd zalo-auto
```

### 2. Create Directories

```bash
mkdir -p data openzca_data
```

### 3. Run with Docker

```bash
# Build and start
docker-compose up -d --build

# Check logs
docker-compose logs -f

# Stop
docker-compose down
```

### 4. Login to Zalo

**Method 1: Web Interface (Recommended)**
- Open: `http://YOUR_SERVER_IP:10000/login/qr/web`
- Wait for QR code to appear (auto-generated)
- Scan with Zalo mobile app
- Page will auto-detect successful login

**Method 2: CLI (Fallback)**
```bash
docker exec -it zalo-api-service openzca auth login
# Scan QR in terminal
```

### 5. Check Status

```bash
curl http://localhost:10000/login/status
```

## 📚 API Documentation

### Base URL

```
http://localhost:10000
```

**Note:** No API key required. Public access.

### Endpoints

#### 🔐 Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI documentation |
| GET | `/login/qr/web` | Web interface for QR login |
| GET | `/qr-code.png` | Get current QR image |
| GET | `/qr-image` | Get QR as base64 JSON |
| POST | `/login/qr/refresh` | Generate new QR |
| GET | `/login/status` | Check login status |
| POST | `/logout` | Logout and clear session |

#### 📨 Messaging

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/send` | Send message to user by phone |
| POST | `/send-group` | Send message to group by name |

#### 👥 Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/friends` | List all friends (with phone & ID) |
| GET | `/groups` | List all groups |

### Request Examples

#### Send Message to User

```bash
curl -X POST http://localhost:10000/send \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "84983802885",
    "message": "Hello from API!"
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Message sent to Thị Hằng Trịnh",
  "data": {
    "user_id": "4434804354228511225",
    "user_name": "Thị Hằng Trịnh"
  },
  "timestamp": "2024-01-15T10:30:00"
}
```

#### Send Message to Group

```bash
curl -X POST http://localhost:10000/send-group \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "Test Group",
    "message": "Hello everyone!"
  }'
```

#### Get Friends List

```bash
curl http://localhost:10000/friends
```

**Response:**
```json
{
  "success": true,
  "count": 637,
  "friends": [
    {
      "id": "4434804354228511225",
      "name": "Thị Hằng Trịnh",
      "phoneNumber": "84983802885"
    }
  ]
}
```

#### Get Groups List

```bash
curl http://localhost:10000/groups
```

#### Get QR as Base64

```bash
curl http://localhost:10000/qr-image
```

**Response:**
```json
{
  "success": true,
  "image_base64": "data:image/png;base64,iVBORw0KGgo...",
  "created_at": 1234567890
}
```

## 🏗️ Architecture

```
┌─────────────────┐
│  External Apps  │
│  (Java/JS/Web)  │
└────────┬────────┘
         │ HTTP/JSON
         ▼
┌─────────────────┐
│   FastAPI App   │
│   (Port 10000)  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────┐
│OpenZCA │ │ Session  │
│  CLI   │ │  Files   │
└───┬────┘ │/root/    │
    │      │.openzca/ │
    ▼      └──────────┘
┌────────┐
│  Zalo  │
│ Server │
└────────┘
```

## 📁 Project Structure

```
zalo-auto/
├── docker-compose.yml      # Docker Compose config
├── Dockerfile              # Ubuntu 24.04 + OpenZCA
├── main.py                 # FastAPI application
├── requirements.txt        # Python dependencies
├── startup.sh              # Container startup script
├── .gitignore             # Git ignore rules
├── data/                  # Runtime data (created at runtime)
├── openzca_data/          # OpenZCA session (MUST persist!)
└── zalo_plugin/           # Legacy zca-js code
```

## 🔧 Configuration

### Docker Compose

```yaml
services:
  zalo-api:
    build: .
    container_name: zalo-api-service
    ports:
      - "10000:10000"
    volumes:
      - ./data:/app/data
      - ./openzca_data:/root/.openzca  # IMPORTANT: Persist session
    restart: unless-stopped
```

**Critical:** The `./openzca_data:/root/.openzca` volume is required to persist Zalo login session across container restarts.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 10000 | Server port |
| `HOST` | 0.0.0.0 | Server host |
| `HERMES_HOME` | /app/data | Data directory |

## 🐛 Troubleshooting

### Error: GLIBC_2.38 not found

**Cause:** Old base image  
**Fix:** Dockerfile uses `ubuntu:24.04` which has glibc 2.39

### Error: "default" has no credentials

**Cause:** Session not persisted  
**Fix:** Ensure volume `./openzca_data:/root/.openzca` is mounted

### Error: spawn xdg-open ENOENT

**Cause:** Container has no GUI (expected)  
**Solution:** QR saved to `/app/qr.png`, use `/qr-image` endpoint

### QR not visible on web

1. Check QR file exists: `docker exec zalo-api-service ls -la /app/qr.png`
2. Use `/qr-image` endpoint for base64 display
3. Web auto-refreshes every 5s to check login status

### Login works but API returns "Not logged in"

**Cause:** Session mismatch between OpenZCA and API check  
**Fix:** Restart container after login

## 🔄 Workflow

### First Time Setup

1. Start container: `docker-compose up -d`
2. Open web: `http://IP:10000/login/qr/web`
3. Wait for QR generation (3-5 seconds)
4. Scan QR with Zalo mobile app
5. Wait for "Logged in" status
6. Test API: `curl http://IP:10000/friends`

### Sending Messages

1. Get friend list: `GET /friends`
2. Find phone number → user ID mapping
3. Send message: `POST /send` with phone
4. Or use user ID directly from friend list

## 🛡️ Security Notes

- No API key required (public access)
- Session stored in container at `/root/.openzca/`
- Must persist `./openzca_data` volume
- QR codes valid for ~2-3 minutes
- Only works with existing Zalo friends

## 📝 OpenZCA Commands

Useful commands for debugging:

```bash
# Check login status
docker exec zalo-api-service openzca auth status

# List friends
docker exec zalo-api-service openzca friend list -j

# Send message directly
docker exec zalo-api-service openzca msg send <user_id> "Hello"

# List groups
docker exec zalo-api-service openzca group list -j
```

## 📄 License

MIT

## 🤝 Contributing

Pull requests welcome!

## 🔗 References

- OpenZCA: https://github.com/darkamenosa/openzca
- FastAPI: https://fastapi.tiangolo.com/
