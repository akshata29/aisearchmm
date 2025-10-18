export interface RagCitation {
  id?: string;
  title?: string;
  snippet?: string;
  url?: string;
}

export interface RagAnswer {
  answer: string;
  citations: RagCitation[];
}
