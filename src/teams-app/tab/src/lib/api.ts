import { fetchEventSource, type EventSourceMessage } from '@microsoft/fetch-event-source';
import type { RagAnswer, RagCitation } from './types';

const DEFAULT_BASE_URL = (import.meta.env.VITE_RAG_API_BASE_URL ?? '').replace(/\/$/, '');

interface AskOptions {
  abortSignal?: AbortSignal;
}

interface CitationPayload {
  textCitations?: unknown[];
  imageCitations?: unknown[];
}

interface AnswerPayload {
  answerPartial?: { answer?: string };
  answer?: string;
}

interface ErrorPayload {
  message?: string;
  details?: string;
}

export async function askRag(question: string, options: AskOptions = {}): Promise<RagAnswer> {
  const payload = {
    query: question,
    chatThread: [],
    config: {
      use_streaming: true,
      use_chat_history: false,
      chunk_count: 6,
      cache_max_results: 5,
      cache_similarity_threshold: 0.82
    },
    request_id: `teams-tab-${Date.now()}`
  };

  const endpoint = DEFAULT_BASE_URL ? `${DEFAULT_BASE_URL}/chat` : '/chat';
  const controller = new AbortController();
  const externalSignal = options.abortSignal;

  const abortForwarder = () => controller.abort();

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener('abort', abortForwarder, { once: true });
    }
  }

  const answerChunks: string[] = [];
  let citations: RagCitation[] = [];
  let errorMessage: string | undefined;
  let streamEnded = false;

  const appendAnswer = (data: AnswerPayload) => {
    const chunk = data.answerPartial?.answer ?? data.answer;
    if (typeof chunk === 'string' && chunk.length > 0) {
      answerChunks.push(chunk);
    }
  };

  const applyCitations = (data: CitationPayload) => {
    const text = Array.isArray(data.textCitations) ? data.textCitations : [];
    const images = Array.isArray(data.imageCitations) ? data.imageCitations : [];
    const normalized = [...text, ...images]
      .map((c, index) => normalizeCitation(c, index))
      .filter((c): c is RagCitation => Boolean(c));
    if (normalized.length > 0) {
      citations = normalized;
    }
  };

  try {
    await fetchEventSource(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
      onmessage(message: EventSourceMessage) {
        if (!message.event) {
          return;
        }

        try {
          const parsed = message.data ? JSON.parse(message.data) : {};
          switch (message.event) {
            case 'answer':
              appendAnswer(parsed as AnswerPayload);
              break;
            case 'citation':
              applyCitations(parsed as CitationPayload);
              break;
            case 'error':
              errorMessage = (parsed as ErrorPayload)?.message ?? 'Unknown error from RAG service.';
              break;
            case '[END]':
              streamEnded = true;
              controller.abort();
              break;
            default:
              break;
          }
        } catch (error) {
          // If JSON parsing fails, bubble up a more descriptive error for debugging
          throw new Error(`Failed to parse RAG stream payload for event "${message.event}": ${(error as Error).message}`);
        }
      },
      onerror(err: unknown) {
        throw err;
      }
    });
  } catch (error) {
    const aborted = controller.signal.aborted;
    const abortError = error instanceof DOMException && error.name === 'AbortError';

    if (!(aborted && streamEnded && abortError)) {
      throw error instanceof Error ? error : new Error('Failed to reach RAG service.');
    }
  } finally {
    if (externalSignal) {
      externalSignal.removeEventListener('abort', abortForwarder);
    }
  }

  if (errorMessage) {
    throw new Error(errorMessage);
  }

  return {
    answer: answerChunks.join('').trim(),
    citations
  };
}

function normalizeCitation(raw: unknown, fallbackIndex: number): RagCitation | undefined {
  if (!raw || typeof raw !== 'object') {
    return undefined;
  }

  const data = raw as Record<string, unknown>;
  const id = typeof data.content_id === 'string' ? data.content_id : typeof data.ref_id === 'string' ? data.ref_id : undefined;
  const title = typeof data.title === 'string' ? data.title : typeof data.document_title === 'string' ? data.document_title : undefined;
  const snippet = typeof data.text === 'string' ? data.text : undefined;
  const url = typeof data.url === 'string' ? data.url : typeof data.image_url === 'string' ? data.image_url : undefined;

  if (!id && !title && !snippet) {
    return undefined;
  }

  return {
    id: id ?? `citation-${fallbackIndex}`,
    title,
    snippet,
    url
  };
}
