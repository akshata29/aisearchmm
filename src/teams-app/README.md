# Microsoft Teams RAG Assistant

This project adds a Microsoft Teams app that connects your existing multimodal RAG backend to bot conversations, message extensions, and a personal tab. The bot is built with **@microsoft/teams-ai v2**, serves through **Express**, and reuses the Python `/chat` endpoint from this repository for all answers.

## Features

- **Conversational bot**: Streams grounded answers from the Python RAG service, returning Adaptive Cards with citations.
- **Slash commands**: `/help` shows capabilities; `/reset` clears per-conversation memory.
- **Message extension**: Action command *Ask RAG* opens a task module form, and search command *Search RAG* provides live suggestions from the RAG service.
- **Personal tab**: React + Vite experience hosted inside this project, built with Fluent UI and deep linking back to the bot.
- **Production essentials**: Strict TypeScript, ESLint/Prettier, structured logging, retry/timeout protection, deployment-ready Azure Bicep, and app packaging scripts.

## Prerequisites

- Node.js **18.20** or newer
- npm **9+**
- Existing Python backend from this repository running locally or deployed
- Azure Bot registration (Microsoft App ID/Password)
- (Optional) Azure resources created via the Bicep template in `infra/`

## Repository layout

```
teams-app/
  README.md
  package.json
  .env.example
  tsconfig.json
  infra/
  src/
    bot/                # Express entry point, Teams AI bot, commands
    me/                 # Message extension handlers
  tab/                # Vite + React tab implementation
    common/             # Shared configuration, models, helpers
  appPackage/           # Teams manifest, icons, packaging artifacts
  scripts/
    package.ts          # Zips manifest + icons for sideload
```

## Environment configuration

1. Copy `.env.example` to `.env` and populate:
   - `BOT_ID` / `BOT_PASSWORD`: From your Azure Bot registration
   - `RAG_API_BASE_URL`: Base URL of the Python backend (e.g. `https://your-api.azurewebsites.net` or `http://localhost:5000`)
   - `ALLOWED_ORIGINS`: Origins allowed for CORS (include tab origin and dev URLs)
  - `TAB_BASE_URL`: Base URL serving the React tab (typically `https://localhost:5300` in dev)
  - `TEAMS_APP_ID`: (Optional) Used to generate Teams deep links for the tab action button
2. Ensure the backend is reachable from the bot (configure firewall or tunnels as required).

## Local development

```bash
cd teams-app
npm install
npm run dev:all
```

- `npm run dev` starts the bot only with live reload via `tsx`
- `npm run tab:dev` launches the HTTPS Vite dev server for the personal tab on port 5300
- `npm run dev:all` runs both bot and tab concurrently for an end-to-end experience

Use the Bot Framework Emulator or Teams Developer Portal to chat locally. Ensure the messaging endpoint is `https://<public-ngrok-domain>/api/messages` when tunnelling.

### Debugging in VS Code

Launch configs live in `.vscode/launch.json`. Set breakpoints in `src/bot/**/*.ts`, run `npm run dev:bot`, then start the **Debug Bot (ts-node)** configuration.

## Quality gates

- `npm run lint` – static analysis (ESLint + Prettier)
- `npm run format` – format all files
- `npm run build` – type-check and produce production bot bundle in `dist/`
- `npm run tab:build` – produce static tab assets in `dist/tab`

## Packaging the Teams app

1. Update the placeholders in `appPackage/manifest.json` (bot ID, URLs, tab domains).
2. Run `npm run package` to create `appPackage/teams-rag-app.zip`.
3. Sideload the ZIP via the Teams Developer Portal or the Microsoft 365 Agents Toolkit.

## Azure deployment

1. Provision infrastructure using Bicep:
   ```bash
   az deployment sub create \
     --location <region> \
     --template-file infra/main.bicep \
     --parameters \
       botAppId=<BOT_ID> \
       botAppPassword=<BOT_PASSWORD> \
       ragApiBaseUrl=<RAG_API_BASE_URL>
   ```
2. Deploy the Node service to Azure App Service (for example with GitHub Actions or `az webapp up`).
3. Update the Teams manifest with the deployed endpoint (`https://<app-name>.azurewebsites.net/api/messages`) and tab domains.

## Integration with the Python RAG API

- Chat: POST `/chat` with `{ query, chatThread, config }` – parsed as Server Sent Events for answers and citations.
- Message Extension: Reuses the same endpoint for live previews and action submissions.
- Tab: Uses the same backend for interactive queries and reuses the rendered cards.

The shared logic lives in `src/common/http` and `src/bot/services/ragClient.ts`, which centralises retries, sanitisation, and SSE parsing. Conversation history is capped and stored in-memory but can be replaced with Redis by implementing `ConversationStore`.

## Next steps

- Replace icon placeholders in `appPackage/icons/`
- Configure CI/CD (GitHub Actions, Azure DevOps) to run lint/build/package
- Connect Azure Application Insights for production telemetry via `APPINSIGHTS_CONNECTION_STRING`
- Implement authentication for the tab and secured backend routes if required
