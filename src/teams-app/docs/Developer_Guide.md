# Teams Integration Developer Guide
## Multimodal RAG Application with Microsoft Teams

### 📋 Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Local Development Setup](#local-development-setup)
5. [Testing Locally](#testing-locally)
6. [Teams App Deployment](#teams-app-deployment)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Configuration](#advanced-configuration)

---

## 📖 Overview

This guide walks you through integrating a Multimodal RAG (Retrieval-Augmented Generation) application with Microsoft Teams, providing:

- **Teams Bot**: Conversational AI bot with adaptive cards and popular questions
- **Message Extensions**: Search and ask capabilities from Teams compose box
- **Tab Integration**: Native embedding of React frontend with Teams context (SSO, user info, theme)
- **DevTools**: Professional testing interface for bot development

### 🏗️ Architecture Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Teams Bot     │    │   Backend       │
│   (React)       │◄──►│   (Node.js)     │◄──►│   (Python)      │
│   Port: 5173    │    │   Port: 3979    │    │   Port: 5000    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐             │
         └─────────────►│  Microsoft      │◄────────────┘
                        │  Teams Client   │
                        └─────────────────┘
```

---

## ✅ Prerequisites

### 🔧 Development Environment

1. **Node.js** (v18.20+ required)
   ```bash
   node --version  # Should be 18.20 or higher
   npm --version
   ```

2. **Python** (v3.8+ recommended)
   ```bash
   python --version  # Should be 3.8 or higher
   pip --version
   ```

3. **Git** (for version control)
   ```bash
   git --version
   ```

### 🏢 Microsoft Teams Setup

1. **Microsoft 365 Developer Tenant** (Recommended)
   - Sign up at: https://developer.microsoft.com/microsoft-365/dev-program
   - Or use existing corporate tenant with developer permissions

2. **Microsoft Teams Desktop App**
   - Download from: https://www.microsoft.com/microsoft-teams/download-app
   - Web version also works but desktop is preferred for development

3. **Teams Developer Permissions**
   - Ability to upload custom apps (sideloading)
   - Developer mode enabled in Teams settings

### 🛠️ Development Tools

1. **Visual Studio Code** (Recommended)
   - Extensions: Teams Toolkit, Python, TypeScript
   
2. **PowerShell** (Windows) or **Bash** (macOS/Linux)

3. **Browser** (Chrome/Edge recommended for debugging)

---

## 🚀 Local Development Setup

### 📁 Project Structure
```
aisearchmm/
├── src/
│   ├── backend/          # Python RAG service
│   │   ├── app.py       # Main Flask application
│   │   └── ...
│   ├── frontend/         # React application
│   │   ├── src/
│   │   │   ├── hooks/useTeamsContext.ts  # Teams SDK integration
│   │   │   └── components/TeamsIntegrationTest.tsx
│   │   └── package.json
│   └── teams-app/        # Teams bot application
│       ├── src/index.ts  # Teams AI v2 bot
│       ├── appPackage/   # Teams app manifest & icons
│       └── .env         # Configuration
├── start-teams-app.ps1   # Startup script
└── test-teams-integration.ps1  # Testing script
```

### 🔧 Step 1: Clone and Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd aisearchmm

# Install backend dependencies
cd src/backend
pip install -r requirements.txt

# Install frontend dependencies
cd ../frontend
npm install

# Install Teams app dependencies
cd ../teams-app
npm install

# Return to root
cd ../../
```

### ⚙️ Step 2: Configure Environment Variables

1. **Backend Configuration** (`src/backend/.env` - if exists)
   ```bash
   # Azure search and OpenAI configurations
   # Usually configured through environment or config files
   ```

2. **Teams App Configuration** (`src/teams-app/.env`)
   ```bash
   # Microsoft Bot registration (optional for local dev)
   #BOT_ID=
   #BOT_PASSWORD=

   # Backend RAG service endpoint
   RAG_API_BASE_URL=http://localhost:5000

   # Frontend URL for tab integration
   TAB_BASE_URL=http://localhost:5173

   # CORS origins
   ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3979

   # Server configuration
   PORT=3978
   REQUEST_TIMEOUT_MS=20000
   REQUEST_RETRY_COUNT=2
   ```

3. **Frontend Teams Integration** (Already configured)
   - Teams SDK integration in `src/frontend/src/hooks/useTeamsContext.ts`
   - Teams test component in `src/frontend/src/components/TeamsIntegrationTest.tsx`

---

## 🧪 Testing Locally

### 🚀 Quick Start with Startup Script

```powershell
# Run the automated startup script (Windows)
.\start-teams-app.ps1
```

This script automatically starts:
- Python backend (port 5000)
- React frontend (port 5173) 
- Teams bot with DevTools (port 3979)

### 🔍 Manual Startup (Step by Step)

1. **Start Backend Service**
   ```bash
   cd src/backend
   python app.py
   ```
   ✅ **Verify**: http://localhost:5000/health should return success

2. **Start Frontend Application**
   ```bash
   cd src/frontend
   npm run dev
   ```
   ✅ **Verify**: http://localhost:5173 should load the RAG interface

3. **Start Teams Bot with DevTools**
   ```bash
   cd src/teams-app
   npm run dev
   ```
   ✅ **Verify**: http://localhost:3979/devtools should load Teams DevTools

### 🎯 Testing Components

#### 1. **Backend API Testing**
```bash
# Test health endpoint
curl http://localhost:5000/health

# Test RAG query (if authenticated)
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Test question"}'
```

#### 2. **Frontend Testing**
- Navigate to http://localhost:5173
- Test the "Teams Integration" tab
- Verify popular questions load from `src/frontend/src/content/samples.json`

#### 3. **Teams Bot Testing**
- Open http://localhost:3979/devtools
- Test bot commands:
  - `/help` - Show help and popular questions
  - `/popular` - Show all popular questions  
  - `/reset` - Clear conversation history
  - `hello`, `start`, `welcome` - Show welcome card
- Test RAG queries by typing financial questions

#### 4. **Integration Testing**
```powershell
# Run comprehensive test suite
.\test-teams-integration.ps1
```

---

## 📦 Teams App Deployment

### 🏗️ Step 1: Create App Package

```bash
cd src/teams-app
npm run package
```

This creates: `src/teams-app/appPackage/dist/teams-rag-app-[timestamp].zip`

### 📋 Step 2: Verify App Manifest

The app includes:
- **Bot capabilities** with commands (`/help`, `/popular`, `/reset`)
- **Message extensions** (`askRag`, `searchRag`)
- **Personal tab** pointing to your frontend
 - **Personal tab** serving the embedded Teams experience
- **Proper icons** (192x192 color, 32x32 transparent outline)

Key manifest configuration:
```json
{
  "staticTabs": [
    {
      "entityId": "ragTab",
      "name": "RAG Assistant", 
   "contentUrl": "https://localhost:5300",
   "websiteUrl": "https://localhost:5300",
      "scopes": ["personal"]
    }
  ]
}
```

### 🚀 Step 3: Upload to Teams

#### Method A: Teams Developer Portal (Recommended)
1. Go to https://dev.teams.microsoft.com/
2. Sign in with Microsoft 365 account
3. Click **"Apps"** → **"Import app"**
4. Upload the generated zip file
5. Follow validation and publish steps

#### Method B: Teams Client Direct Upload
1. Open Microsoft Teams desktop app
2. Go to **Apps** (left sidebar)
3. Click **"Manage your apps"** or **"Upload a custom app"**
4. Select **"Upload a custom app"**
5. Choose the zip file from `appPackage/dist/`

#### Method C: Teams Toolkit (VS Code)
1. Install Teams Toolkit extension
2. Open project in VS Code
3. Use Teams Toolkit commands to package and upload

### 🔍 Step 4: Test Deployed App

Once uploaded successfully:

1. **Find Your App**
   - Go to Teams Apps section
   - Search for "RAG Assistant"
   - Click to install/open

2. **Test Bot Functionality**
   - Start a chat with the bot
   - Try commands: `/help`, `/popular`
   - Ask financial questions
   - Verify adaptive cards work

3. **Test Message Extensions**
   - In any chat, type `@RAG Assistant` 
   - Use `askRag` and `searchRag` commands
   - Verify results are inserted into conversation

4. **Test Tab Integration**
   - Click on "RAG Assistant" tab
   - Confirm the Teams-specific search UI loads (port 5300 in dev)
   - Ask a sample question and verify citations render
   - Use the "Pop out" action to open the tab in a browser window
     - User information displayed
     - Team/Channel info (if in team context)
     - Theme integration working

---

## 🐛 Troubleshooting

### Common Issues and Solutions

#### 🔧 Backend Connection Issues
**Symptom**: Bot responds with "Failed to contact RAG service"
```bash
# Check backend is running
curl http://localhost:5000/health

# Verify port in teams-app/.env
RAG_API_BASE_URL=http://localhost:5000
```

#### 🔧 Frontend Not Loading in Teams Tab
**Symptom**: Tab shows error or blank page
```json
// Check manifest.json
"contentUrl": "https://localhost:5173"  // Must be HTTPS for Teams
```
**Solution**: Use ngrok or configure HTTPS for local development

#### 🔧 Teams App Upload Errors
**Symptom**: "Color Icon is not as per the required dimension"
```bash
# Recreate icons with correct dimensions
powershell -ExecutionPolicy Bypass -File "create-icons-fixed.ps1"
npm run package
```

#### 🔧 Teams SDK Not Detected
**Symptom**: Frontend shows "Standalone Mode" even in Teams
- Ensure `@microsoft/teams-js` is installed
- Check browser console for Teams SDK errors
- Verify HTTPS is used (Teams requires secure contexts)

#### 🔧 Authentication Issues
**Symptom**: AADSTS errors when uploading
- Ensure you have Teams developer permissions
- Try using Microsoft 365 Developer tenant
- Enable Teams developer preview in Teams settings

### 🔍 Debug Information

#### Enable Detailed Logging
```bash
# In teams-app/.env
NODE_ENV=development

# Check console logs in DevTools
# Check Teams app logs in Teams client
```

#### Network Debugging
```bash
# Test all endpoints
curl http://localhost:5000/health     # Backend
curl http://localhost:5173/          # Frontend  
curl http://localhost:3979/          # Teams bot
```

---

## ⚙️ Advanced Configuration

### 🔒 Production Deployment

#### Backend Deployment
```bash
# Deploy to Azure App Service, AWS, or other cloud provider
# Update RAG_API_BASE_URL in teams-app/.env to production URL
RAG_API_BASE_URL=https://your-backend.azurewebsites.net
```

#### Frontend Deployment  
```bash
# Deploy to static hosting (Azure Static Web Apps, Vercel, etc.)
# Update TAB_BASE_URL and manifest.json contentUrl
TAB_BASE_URL=https://your-frontend.azurestaticapps.net
```

#### Teams Bot Registration
```bash
# Register bot in Azure Bot Service
# Update BOT_ID and BOT_PASSWORD in .env
BOT_ID=your-bot-app-id
BOT_PASSWORD=your-bot-secret
```

### 🎨 Customization

#### Adding New Bot Commands
```typescript
// In src/teams-app/src/index.ts
if (text.toLowerCase() === '/yourcmd') {
  // Your custom logic
  await client.send('Your response');
  return;
}
```

#### Adding Popular Questions
```json
// Update src/frontend/src/content/samples.json
{
  "queries": [
    "Your new question here",
    // ... existing questions
  ]
}
```

#### Custom Teams Theme Integration
```typescript
// In src/frontend/src/hooks/useTeamsContext.ts
// Customize theme detection and application
```

### 📊 Monitoring and Analytics

#### Bot Analytics
- Monitor bot usage through Teams admin center
- Add custom telemetry in bot handlers
- Track popular commands and queries

#### Frontend Analytics
- Add Teams-specific analytics
- Track tab usage and user interactions
- Monitor performance in Teams context

---

## 🎓 Hackathon Tips

### 🏆 Success Criteria
- [ ] Bot responds to commands and questions
- [ ] Frontend loads properly as Teams tab
- [ ] Teams context (user, theme) is detected
- [ ] Message extensions work from compose box
- [ ] Popular questions match frontend samples
- [ ] Proper error handling and user feedback

### ⚡ Quick Demo Script
1. **Show DevTools**: http://localhost:3979/devtools
2. **Demo bot commands**: `/help`, `/popular`, actual questions
3. **Show standalone frontend**: http://localhost:5173
4. **Demonstrate Teams integration tab**
5. **Test message extensions** (if deployed to Teams)

### 🚀 Extension Ideas
- Add more message extension types
- Implement deep linking between bot and tab
- Add Teams notifications for important updates  
- Create team-scoped installations
- Add SSO authentication flow
- Implement file sharing capabilities

---

## 📚 Resources

- **Teams Platform Documentation**: https://docs.microsoft.com/microsoftteams/platform/
- **Teams AI Library**: https://github.com/microsoft/teams-ai
- **Teams App Samples**: https://github.com/OfficeDev/Microsoft-Teams-Samples
- **Teams SDK Reference**: https://docs.microsoft.com/javascript/api/@microsoft/teams-js/
- **Adaptive Cards Designer**: https://adaptivecards.io/designer/

---

*This guide covers the complete Teams integration workflow. For specific issues or advanced scenarios, refer to the troubleshooting section or Microsoft Teams documentation.*