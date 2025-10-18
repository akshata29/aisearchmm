import dotenv from 'dotenv';
import { z } from 'zod';

const rawEnv = (() => {
  dotenv.config();
  return {
    BOT_ID: process.env['BOT_ID'],
    BOT_PASSWORD: process.env['BOT_PASSWORD'],
    RAG_API_BASE_URL: process.env['RAG_API_BASE_URL'],
    ALLOWED_ORIGINS: process.env['ALLOWED_ORIGINS'],
    TAB_BASE_URL: process.env['TAB_BASE_URL'],
    TEAMS_APP_ID: process.env['TEAMS_APP_ID'],
    HTTP_PROXY: process.env['HTTP_PROXY'],
    HTTPS_PROXY: process.env['HTTPS_PROXY'],
    REQUEST_TIMEOUT_MS: process.env['REQUEST_TIMEOUT_MS'],
    REQUEST_RETRY_COUNT: process.env['REQUEST_RETRY_COUNT']
  };
})();

const envSchema = z.object({
  BOT_ID: z
    .string()
    .uuid('BOT_ID must be a valid GUID')
    .optional()
    .or(z.literal('')),
  BOT_PASSWORD: z
    .string()
    .min(1, 'BOT_PASSWORD is required when BOT_ID is set')
    .optional()
    .or(z.literal('')),
  RAG_API_BASE_URL: z
    .string()
    .url('RAG_API_BASE_URL must be a valid URL')
    .default('http://localhost:5000'),
  ALLOWED_ORIGINS: z
    .string()
    .optional()
    .transform((value: string | undefined) =>
      value
        ?.split(',')
        .map((origin: string) => origin.trim())
        .filter((origin: string) => origin.length > 0) ?? []
    ),
  TAB_BASE_URL: z.string().url().optional(),
  TEAMS_APP_ID: z.string().uuid('TEAMS_APP_ID must be a valid GUID').optional().or(z.literal('')),
  HTTP_PROXY: z.string().url().optional(),
  HTTPS_PROXY: z.string().url().optional(),
  REQUEST_TIMEOUT_MS: z
    .string()
    .transform((value: string | undefined) => (value ? Number.parseInt(value, 10) : undefined))
    .optional()
    .refine((value: number | undefined) => value === undefined || Number.isInteger(value), {
      message: 'REQUEST_TIMEOUT_MS must be an integer'
    }),
  REQUEST_RETRY_COUNT: z
    .string()
    .transform((value: string | undefined) => (value ? Number.parseInt(value, 10) : undefined))
    .optional()
    .refine((value: number | undefined) => value === undefined || Number.isInteger(value), {
      message: 'REQUEST_RETRY_COUNT must be an integer'
    })
});

const parsedEnv = envSchema.parse(rawEnv);

export interface AppConfig {
  botId?: string;
  botPassword?: string;
  ragApiBaseUrl: string;
  allowedOrigins: string[];
  tabBaseUrl?: string;
  teamsAppId?: string;
  httpProxy?: string;
  httpsProxy?: string;
  requestTimeoutMs: number;
  requestRetryCount: number;
}

export const appConfig: AppConfig = {
  botId: parsedEnv.BOT_ID,
  botPassword: parsedEnv.BOT_PASSWORD,
  ragApiBaseUrl: parsedEnv.RAG_API_BASE_URL,
  allowedOrigins: parsedEnv.ALLOWED_ORIGINS,
  tabBaseUrl: parsedEnv.TAB_BASE_URL,
  teamsAppId: parsedEnv.TEAMS_APP_ID,
  httpProxy: parsedEnv.HTTP_PROXY,
  httpsProxy: parsedEnv.HTTPS_PROXY,
  requestTimeoutMs: parsedEnv.REQUEST_TIMEOUT_MS ?? 20000,
  requestRetryCount: parsedEnv.REQUEST_RETRY_COUNT ?? 2
};

export function requireBotCredentials(): { botId: string; botPassword: string } {
  if (!appConfig.botId || !appConfig.botPassword) {
    throw new Error('BOT_ID and BOT_PASSWORD must be configured before starting the bot.');
  }

  return { botId: appConfig.botId, botPassword: appConfig.botPassword };
}
