export interface ConversationEntry {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

// Simple in-memory store that can be replaced with an external cache (e.g. Redis).
export class ConversationStore {
  private readonly store = new Map<string, ConversationEntry[]>();

  constructor(private readonly maxEntries: number) {}

  getHistory(conversationId: string): ConversationEntry[] {
    return this.store.get(conversationId)?.slice() ?? [];
  }

  append(conversationId: string, entry: ConversationEntry): void {
    const history = this.store.get(conversationId) ?? [];
    history.push(entry);

    while (history.length > this.maxEntries) {
      history.shift();
    }

    this.store.set(conversationId, history);
  }

  clear(conversationId: string): void {
    this.store.delete(conversationId);
  }
}
