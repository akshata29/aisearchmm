import { createParser } from 'eventsource-parser';

import { appConfig } from '../../common/config/env';
import { childLogger } from '../../common/logger';
import { sanitizeMarkdown } from '../../common/utils/sanitize';
import type { RagAnswer, RagCitation, RagRequestOptions, RagSearchResult } from '../../types/rag';

const log = childLogger('rag-client');

interface CitationPayload {
  ref_id?: string;
  title?: string;
  url?: string;
  content?: string;
  snippet?: string;
}

export class RagClient {
  private readonly baseUrl: string;

  constructor(
    baseUrl: string,
    private readonly timeoutMs: number,
    private readonly retryCount: number
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async ask(question: string, options: RagRequestOptions): Promise<RagAnswer> {
    return this.requestWithRetry(question, options);
  }

  async search(question: string, options: RagRequestOptions): Promise<RagSearchResult[]> {
    const response = await this.requestWithRetry(question, options);

    if (response.citations.length === 0) {
      return [
        {
          title: 'RAG answer',
          snippet: response.answer.slice(0, 180),
          answer: response.answer,
          citations: response.citations
        }
      ];
    }

    return response.citations.slice(0, 5).map((citation) => ({
      title: citation.title ?? citation.id ?? 'Source',
      snippet: citation.snippet ?? response.answer.slice(0, 180),
      url: citation.url,
      answer: response.answer,
      citations: response.citations
    }));
  }

  private async requestWithRetry(question: string, options: RagRequestOptions): Promise<RagAnswer> {
    let attempt = 0;
    let lastError: unknown;

    while (attempt <= this.retryCount) {
      try {
        return await this.invoke(question, options);
      } catch (error) {
        lastError = error;
        attempt += 1;
        log.warn({ attempt, error }, 'RAG request failed, retrying');
        await new Promise((resolve) => setTimeout(resolve, 300 * attempt));
      }
    }

    log.error({ error: lastError }, 'Failed to receive response from RAG API');
    throw lastError instanceof Error ? lastError : new Error('Unknown RAG API error');
  }

  private async invoke(question: string, options: RagRequestOptions): Promise<RagAnswer> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    const payload = {
      query: options.includeSelection ? `${question}\n${options.includeSelection}` : question,
      chatThread: options.includeHistory ? options.thread : [],
      config: {
        use_streaming: false,
        use_chat_history: options.includeHistory,
        chunk_count: 6,
        cache_max_results: 5,
        cache_similarity_threshold: 0.82,
        custom_system_prompt: options.confidentiality
          ? `Confidentiality level: ${options.confidentiality}. Provide answers respecting this classification.`
          : undefined
      },
      request_id: `${options.conversationId}-${Date.now()}`
    };

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
    } finally {
      clearTimeout(timeout);
    }

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`RAG API responded with ${response.status}: ${text}`);
    }

    const contentType = response.headers.get('content-type') ?? '';

    if (contentType.includes('text/event-stream')) {
      return this.parseSse(response);
    }

    const json = (await response.json()) as { answer?: string; citations?: CitationPayload[] };

    return {
      answer: sanitizeMarkdown(json.answer ?? ''),
      citations: this.mapCitations(json.citations ?? [])
    };
  }

  private async parseSse(response: Response): Promise<RagAnswer> {
    if (!response.body) {
      throw new Error('RAG API returned an empty body.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    const parser = createParser((event) => {
      if (event.type !== 'event') {
        return;
      }

      if (!event.data) {
        return;
      }

      try {
        this.handleEvent(event.event ?? 'message', event.data);
      } catch (error) {
        log.error({ error }, 'Failed to parse RAG SSE payload');
      }
    });

    this.currentAnswer = '';
    this.currentCitations = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      parser.feed(decoder.decode(value, { stream: true }));
    }

    const answer = sanitizeMarkdown(this.currentAnswer.trim());

    return {
      answer,
      citations: [...this.currentCitations]
    };
  }

  private currentAnswer = '';
  private currentCitations: RagCitation[] = [];

  private handleEvent(eventName: string, data: string) {
    if (eventName === 'answer') {
      const payload = JSON.parse(data) as {
        answerPartial?: { answer: string };
      };

      if (payload.answerPartial?.answer) {
        this.currentAnswer += payload.answerPartial.answer;
      }
      return;
    }

    if (eventName === 'citation') {
      const payload = JSON.parse(data) as {
        textCitations?: CitationPayload[];
      };

      if (Array.isArray(payload.textCitations)) {
        const mapped = this.mapCitations(payload.textCitations);
        this.currentCitations = this.mergeCitations(this.currentCitations, mapped);
      }
    }
  }

  private mapCitations(citations: CitationPayload[]): RagCitation[] {
    return citations.map((citation) => ({
      id: citation.ref_id ?? citation.title ?? 'source',
      title: citation.title ?? citation.ref_id ?? 'Source',
      url: citation.url,
      snippet: citation.snippet ?? citation.content
    }));
  }

  private mergeCitations(existing: RagCitation[], incoming: RagCitation[]): RagCitation[] {
    const merged = new Map<string, RagCitation>();

    for (const citation of existing) {
      merged.set(citation.id, citation);
    }

    for (const citation of incoming) {
      merged.set(citation.id, citation);
    }

    return Array.from(merged.values());
  }
}

export const ragClient = new RagClient(appConfig.ragApiBaseUrl, appConfig.requestTimeoutMs, appConfig.requestRetryCount);
