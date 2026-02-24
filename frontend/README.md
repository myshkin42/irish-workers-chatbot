# Irish Workers' Rights Chatbot - Frontend

Simple Next.js frontend for the Irish employment law chatbot.

## Key UI Features

1. **Persistent Disclaimer Banner** - Always visible at top, loaded from `/metadata` endpoint
2. **Official Sources Sidebar** - Links to WRC, Citizens Info, HSA always visible
3. **Knowledge Base Date** - Shows when documents were last updated
4. **Per-Response Citations** - Sources and official links with each answer
5. **Time Limit Warning** - Prominent reminder about 6-month WRC deadline

## Setup

```bash
# Install dependencies
npm install

# Copy environment file
cp .env.example .env.local

# Start development server
npm run dev
```

## Environment Variables

- `NEXT_PUBLIC_API_URL` - Backend API URL (default: http://localhost:8000)

## Development

The frontend expects the backend to be running at the configured API URL.

```bash
# Terminal 1: Start backend
cd ../backend
uvicorn app.main:app --reload

# Terminal 2: Start frontend  
npm run dev
```

Then open http://localhost:3000

## Production Build

```bash
npm run build
npm start
```

## API Endpoints Used

- `GET /metadata` - Fetch disclaimer, sources, contacts on page load
- `POST /chat` - Send messages, receive answers with sources
