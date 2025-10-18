# Teams Integration Hackathon - Quick Reference

## 🚀 Quick Start Commands

```powershell
# 1. Start all services
.\start-teams-app.ps1

# 2. Test integration
.\test-teams-integration.ps1

# 3. Create Teams app package
cd src\teams-app
npm run package
```

## 📱 Test URLs
- **Backend Health**: http://localhost:5000/health
- **Main Frontend**: http://localhost:5173
- **Teams DevTools**: http://localhost:3979/devtools
- **Teams Personal Tab**: https://localhost:5300

## 🤖 Bot Commands to Test
- `/help` - Show help and popular questions
- `/popular` - Show all popular questions
- `/reset` - Clear conversation history
- `hello`, `start`, `welcome` - Welcome card
- Ask any financial question for RAG response

## 📦 Teams App Package Location
```
src\teams-app\appPackage\dist\teams-rag-app-[timestamp].zip
```

## ⚡ Common Issues & Fixes

| Issue | Quick Fix |
|-------|-----------|
| Backend connection failed | Check `RAG_API_BASE_URL=http://localhost:5000` in `.env` |
| Icons validation error | Run: `powershell .\create-icons-fixed.ps1` then `npm run package` |
| Teams SDK not detected | Must use HTTPS for Teams tab (use ngrok for local) |
| Upload fails with auth error | Use Microsoft 365 Developer tenant |

## 🎯 Demo Flow
1. Show bot in DevTools → test commands
2. Show standalone frontend → popular questions  
3. Show Teams integration status
4. Upload to Teams → test full integration

## 📋 Success Checklist
- [ ] All 3 services running (backend, frontend, teams bot)
- [ ] Bot responds with adaptive cards
- [ ] Popular questions same as frontend
- [ ] Teams context detected in integration tab
- [ ] App package uploads without errors
- [ ] Tab loads properly in Teams client

---
**Need Help?** Check `Developer_Guide.md` for detailed instructions.