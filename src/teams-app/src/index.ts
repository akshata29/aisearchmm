import { App } from '@microsoft/teams.apps';
import { DevtoolsPlugin } from '@microsoft/teams.dev';
import { appConfig } from './common/config/env';
import { childLogger } from './common/logger';
import { ConversationStore } from './bot/state/conversationStore';
import { ragClient } from './bot/services/ragClient';
import { buildAnswerCard } from './common/cards/answerCardFactory';

// Sample questions from frontend (same as samples.json)
const SAMPLE_QUESTIONS = [
  "What is the value of investing globally? Why shouldn't I just invest in the US? What not invest just in the S&P 500?",
  "Why do you invest my money all at once instead of dollar cost averaging?",
  "Why don't you sell a stock when it is down? How much does a stock have to fall for you guys to sell it? Why don't you guys sell stocks that have been down for months?",
  "Does Fisher use AI in the research process? How do you use AI? Does Fisher use AI to make investment decisions?",
  "Are Republicans or Democrats better for stocks?",
  "Are high oil prices bad for stocks? Aren't rising oil prices bad for the market?",
  "How do wars impact markets? If this conflict escalates, will markets fall?",
  "Why doesn't Fisher invest in IPOs?",
  "Does Fisher use ESG to pick stocks?",
  "What are your thoughts on China challenging the US for global supremacy? What is China invades Taiwan?",
  "How did US ranked in ACWI constituent nations as far as returns and how does it compare to Taiwan?"
];

const log = childLogger('teams-app');

// Helper function to create action buttons from sample questions
function createQuestionActions(questions: string[], maxQuestions = 6) {
  return questions.slice(0, maxQuestions).map((question, index) => {
    // Create shorter titles for buttons
    const shortTitles = [
      '🌍 Global Investing',
      '💰 Dollar Cost Averaging', 
      '📉 Stock Selling Strategy',
      '🤖 AI in Research',
      '🏛️ Politics & Stocks',
      '🛢️ Oil Prices & Markets',
      '⚔️ Wars & Markets',
      '🔄 IPO Strategy',
      '🌱 ESG Investing',
      '🇨🇳 China & Global Markets',
      '📊 US vs Taiwan Returns'
    ];
    
    return {
      type: 'Action.Submit',
      title: shortTitles[index] || `Question ${index + 1}`,
      data: { query: question }
    };
  });
}

// Process RAG query
async function processQuery(client: any, query: string, conversationId: string, store: ConversationStore, tabDeepLink?: (query: string) => string, logger = log) {
  // Store user message
  store.append(conversationId, {
    role: 'user',
    content: query,
    timestamp: Date.now()
  });

  // Send typing indicator
  try {
    await client.send({
      type: 'typing'
    });
  } catch (typingError) {
    logger.warn({ error: typingError }, 'Failed to send typing indicator');
  }

  try {
    // Get conversation history
    const history = store
      .getHistory(conversationId)
      .map((entry) => ({ role: entry.role, content: entry.content }));

    // Call RAG service
    logger.info({ query: query.substring(0, 100), conversationId, historyLength: history.length }, 'Calling RAG service...');
    const response = await ragClient.ask(query, {
      conversationId,
      thread: history,
      includeHistory: history.length > 1
    });
    logger.info({ answerLength: response.answer?.length || 0, citationsCount: response.citations?.length || 0 }, 'RAG service response received');

    // Build adaptive card response
    const deepLink = tabDeepLink ? tabDeepLink(query) : undefined;
    const card = buildAnswerCard({
      answer: response.answer,
      citations: response.citations,
      deepLinkUrl: deepLink
    });

    // Send adaptive card
    await client.send({
      type: 'message',
      attachments: [{
        contentType: 'application/vnd.microsoft.card.adaptive',
        content: card
      }]
    });

    // Store bot response
    store.append(conversationId, {
      role: 'assistant',
      content: response.answer,
      timestamp: Date.now()
    });

  } catch (error) {
    logger.error({ error, query, conversationId }, 'Failed to process message');
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    await client.send(`❌ Sorry, something went wrong when contacting the RAG service: ${errorMessage}\n\n🔧 **Troubleshooting:**\n- Make sure backend is running on http://localhost:5000\n- Check that the backend health endpoint responds\n- Try: \`curl http://localhost:5000/health\``);
  }
}

async function main() {
  const { botId, botPassword } = appConfig;

  if (!botId || !botPassword) {
    log.warn('BOT_ID or BOT_PASSWORD missing; starting with anonymous credentials for local development.');
  }

  // Create Teams AI v2 app
  const app = new App({
    clientId: botId ?? '',
    clientSecret: botPassword ?? '',
    plugins: process.env['NODE_ENV'] === 'development' ? [new DevtoolsPlugin()] : [],
  });

  const store = new ConversationStore(10);
  const tabDeepLink = appConfig.tabBaseUrl
    ? (query: string) => `${appConfig.tabBaseUrl}?q=${encodeURIComponent(query)}`
    : undefined;

  // Handle card actions (button clicks)
  app.on('invoke', async (client) => {
    if (client.activity.name === 'adaptiveCard/action') {
      const data = client.activity.value?.action?.data;
      if (data?.['query']) {
        // Treat card action as a message
        const conversationId = client.activity.conversation?.id ?? 'default';
        await processQuery(client, data['query'], conversationId, store, tabDeepLink, log);
      }
    }
  });

  // Handle conversation updates (when bot is added)
  app.on('conversationUpdate', async (client) => {
    const welcomeCard = {
      type: 'AdaptiveCard',
      version: '1.4',
      body: [
        {
          type: 'TextBlock',
          text: '🤖 Welcome to RAG Bot!',
          size: 'Large',
          weight: 'Bolder'
        },
        {
          type: 'TextBlock',
          text: 'I can help you explore your financial knowledge base. Here are some popular questions to get you started:',
          wrap: true,
          spacing: 'Medium'
        }
      ],
      actions: [
        ...createQuestionActions(SAMPLE_QUESTIONS, 4),
        {
          type: 'Action.Submit',
          title: '❓ See all questions (/help)',
          data: { query: '/help' }
        }
      ]
    };

    await client.send({
      type: 'message',
      attachments: [{
        contentType: 'application/vnd.microsoft.card.adaptive',
        content: welcomeCard
      }]
    });
  });

  // Handle messages
  app.on('message', async (client) => {
    const text = client.activity.text?.trim();
    if (!text) return;

    const conversationId = client.activity.conversation?.id ?? 'default';
    
    // Check if this is the first interaction (no conversation history)
    const conversationHistory = store.getHistory(conversationId);
    const isFirstInteraction = !conversationHistory || conversationHistory.length === 0;

    // Handle commands
    if (text.toLowerCase() === '/help' || text.toLowerCase() === '/home') {
      const helpCard = {
        type: 'AdaptiveCard',
        version: '1.4',
        body: [
          {
            type: 'TextBlock',
            text: '🤖 RAG Bot Commands & Popular Questions',
            size: 'Large',
            weight: 'Bolder'
          },
          {
            type: 'TextBlock',
            text: '**Commands:**',
            weight: 'Bolder',
            spacing: 'Medium'
          },
          {
            type: 'TextBlock',
            text: '• Type any question to search the knowledge base\n• `/help` or `/home` - Show this help\n• `/reset` - Clear conversation history\n• `/popular` - Show popular questions',
            wrap: true
          },
          {
            type: 'TextBlock',
            text: '**Popular Questions:**',
            weight: 'Bolder',
            spacing: 'Medium'
          }
        ],
        actions: createQuestionActions(SAMPLE_QUESTIONS, 6)
      };

      await client.send({
        type: 'message',
        attachments: [{
          contentType: 'application/vnd.microsoft.card.adaptive',
          content: helpCard
        }]
      });
      return;
    }

    if (text.toLowerCase() === '/popular') {
      // Create text list of questions for DevTools compatibility
      const questionsList = SAMPLE_QUESTIONS.map((q, i) => `**${i + 1}.** ${q}`).join('\n\n');
      
      const popularCard = {
        type: 'AdaptiveCard',
        version: '1.4',
        body: [
          {
            type: 'TextBlock',
            text: '💡 Popular Questions',
            size: 'Large',
            weight: 'Bolder'
          },
          {
            type: 'TextBlock',
            text: 'Here are the most popular questions (same as frontend). Click buttons or copy/paste a question:',
            wrap: true,
            spacing: 'Medium'
          },
          {
            type: 'TextBlock',
            text: questionsList,
            wrap: true,
            spacing: 'Medium'
          }
        ],
        actions: createQuestionActions(SAMPLE_QUESTIONS, 10)
      };

      await client.send({
        type: 'message',
        attachments: [{
          contentType: 'application/vnd.microsoft.card.adaptive',
          content: popularCard
        }]
      });
      return;
    }

    if (text.toLowerCase() === '/reset') {
      store.clear(conversationId);
      await client.send('✅ Conversation history cleared!');
      return;
    }

    // Show welcome card only for specific trigger words
    if (text.toLowerCase() === 'start' || text.toLowerCase() === 'hello' || text.toLowerCase() === 'welcome') {
      const welcomeCard = {
        type: 'AdaptiveCard',
        version: '1.4',
        body: [
          {
            type: 'TextBlock',
            text: '🤖 Welcome to RAG Bot!',
            size: 'Large',
            weight: 'Bolder'
          },
          {
            type: 'TextBlock',
            text: 'I can help you explore your financial knowledge base. Here are some popular questions to get you started:',
            wrap: true,
            spacing: 'Medium'
          },
          {
            type: 'TextBlock',
            text: '� **Tip:** Try typing `/help` or `/popular` to see all questions, or just ask directly!',
            wrap: true,
            spacing: 'Small',
            isSubtle: true
          }
        ],
        actions: createQuestionActions(SAMPLE_QUESTIONS, 4)
      };

      await client.send({
        type: 'message',
        attachments: [{
          contentType: 'application/vnd.microsoft.card.adaptive',
          content: welcomeCard
        }]
      });
      return; // Don't process as a regular question
    }

    // Process the query using shared function
    await processQuery(client, text, conversationId, store, tabDeepLink);
  });

  // Handle errors
  app.event('error', async (client) => {
    log.error({ error: client.error }, 'App error occurred');
  });

  // Tab UI will use existing frontend with Teams integration

  // Start the app
  await app.start();
  log.info('Teams RAG app started successfully!');
  log.info('💡 Pro tip: Type "hello", "start", "/help", or "/popular" to see the welcome card with sample questions.');
}

void main().catch((error) => {
  log.error('Failed to start Teams app', error);
  process.exit(1);
});
