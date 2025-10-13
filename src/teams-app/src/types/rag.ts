export interface RagCitation {
  id: string;
  title?: string;
  url?: string;
  snippet?: string;
}

export interface RagAnswer {
  answer: string;
  citations: RagCitation[];
}

export interface RagRequestOptions {
  conversationId: string;
  thread: Array<{ role: 'user' | 'assistant'; content: string }>;
  includeHistory: boolean;
  includeSelection?: string;
  confidentiality?: string;
}

export interface RagSearchResult {
  title: string;
  snippet: string;
  url?: string;
  answer: string;
  citations: RagCitation[];
}
