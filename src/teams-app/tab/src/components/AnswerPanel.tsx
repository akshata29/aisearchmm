import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Body1, Body2, Button, Caption1Strong, Card, CardHeader, Divider, Link, Spinner } from '@fluentui/react-components';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import type { RagAnswer, RagCitation } from '@/lib/types';
import { motion } from 'framer-motion';

interface AnswerPanelProps {
  answer?: RagAnswer;
  isLoading?: boolean;
}

interface CitationEntry {
  key: string;
  domId: string;
  index: number;
  citation: RagCitation;
}

function toCitationDomId(rawId: string | undefined, index: number) {
  const base = (rawId ?? `source-${index + 1}`).toString().toLowerCase();
  return `citation-${base.replace(/[^a-z0-9]+/g, '-')}`;
}

export function AnswerPanel({ answer, isLoading }: AnswerPanelProps) {
  const contentRef = useRef<HTMLElement>(null);
  const [activeCitationKey, setActiveCitationKey] = useState<string | undefined>();

  const { renderedHtml, citationsMeta } = useMemo(() => {
    if (!answer?.answer) {
      return { renderedHtml: '', citationsMeta: [] as CitationEntry[] };
    }

    const entries: CitationEntry[] = (answer.citations ?? []).map((citation, index) => {
      const key = citation.id ?? `source-${index + 1}`;
      return {
        key,
        domId: toCitationDomId(citation.id, index),
        index: index + 1,
        citation
      };
    });

    const lookup = new Map(entries.map((entry) => [entry.key, entry]));
    const raw = marked.parse(answer.answer, { async: false }) as string;
    const sanitised = DOMPurify.sanitize(raw);
    const enhanced = sanitised.replace(/\[([^\]]+?)\]/g, (match, rawId) => {
      const key = String(rawId).trim();
      const meta = lookup.get(key);
      if (!meta) {
        return match;
      }

      return `<sup class="citation-ref" data-citation-id="${meta.key}" data-citation-dom="${meta.domId}"><button type="button" class="citation-ref__button">${meta.index}</button></sup>`;
    });

    return {
      renderedHtml: enhanced,
      citationsMeta: entries
    };
  }, [answer?.answer, answer?.citations]);

  useEffect(() => {
    setActiveCitationKey(undefined);
  }, [answer?.answer]);

  useEffect(() => {
    const node = contentRef.current;
    if (!node) {
      return;
    }

    const handler = (event: Event) => {
      const target = (event.target as HTMLElement | null)?.closest<HTMLElement>('.citation-ref');
      if (!target) {
        return;
      }

      const citationKey = target.getAttribute('data-citation-id') ?? undefined;
      const targetDomId = target.getAttribute('data-citation-dom') ?? undefined;

      if (citationKey) {
        setActiveCitationKey(citationKey);
      }

      if (targetDomId) {
        const citeElement = document.getElementById(targetDomId);
        citeElement?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }

      event.preventDefault();
    };

    node.addEventListener('click', handler);
    return () => node.removeEventListener('click', handler);
  }, [citationsMeta]);

  useEffect(() => {
    const node = contentRef.current;
    if (!node) {
      return;
    }

    node.querySelectorAll<HTMLElement>('.citation-ref').forEach((ref) => {
      const isActive = ref.getAttribute('data-citation-id') === activeCitationKey;
      ref.classList.toggle('citation-ref--active', isActive);
    });
  }, [activeCitationKey, renderedHtml]);

  const handleCitationSelect = useCallback(
    (entry: CitationEntry) => {
      setActiveCitationKey(entry.key);

      const articleNode = contentRef.current;
      const targetRef = articleNode?.querySelector<HTMLElement>(`[data-citation-id="${entry.key}"]`);

      if (targetRef) {
        targetRef.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else {
        const fallback = document.getElementById(entry.domId);
        fallback?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    },
    []
  );

  if (isLoading) {
    return (
      <div className="answer-panel answer-panel--loading">
        <Spinner size="huge" label="Generating answer" />
      </div>
    );
  }

  if (!answer) {
    return (
      <Card className="answer-panel answer-panel--empty">
        <CardHeader
          header={<Body1>Ask a question to see rich answers and citations.</Body1>}
          description="We will surface multimodal sources your team trusts."
        />
      </Card>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
      <Card className="answer-panel" appearance="outline">
        <CardHeader header={<Body1 as="h2">Answer</Body1>} description="Synthesized from your knowledge base" />
        <Divider />
        <article
          ref={contentRef}
          className="answer-panel__content"
          dangerouslySetInnerHTML={{ __html: renderedHtml }}
        />
        {citationsMeta.length > 0 && (
          <section className="answer-panel__citations">
            <Caption1Strong as="h3">Sources</Caption1Strong>
            <CitationList entries={citationsMeta} activeKey={activeCitationKey} onSelect={handleCitationSelect} />
          </section>
        )}
      </Card>
    </motion.div>
  );
}

interface CitationListProps {
  entries: CitationEntry[];
  activeKey?: string;
  onSelect?: (entry: CitationEntry) => void;
}

function CitationList({ entries, activeKey, onSelect }: CitationListProps) {
  if (entries.length === 0) {
    return null;
  }

  return (
    <ul className="citations">
      {entries.map((entry) => {
        const { citation, key, domId, index } = entry;
        const isActive = key === activeKey;

        return (
          <li key={key} className={`citations__item${isActive ? ' citations__item--active' : ''}`} id={domId}>
            <Button
              type="button"
              appearance={isActive ? 'primary' : 'secondary'}
              size="small"
              className="citations__trigger"
              onClick={() => onSelect?.(entry)}
            >
              <span className="citations__badge">{index}</span>
              <span className="citations__title">{citation.title ?? citation.id ?? `Source ${index}`}</span>
            </Button>
            {citation.snippet && (
            <Body2 as="p" className="citations__snippet">
              {citation.snippet}
            </Body2>
          )}
          {citation.url && (
            <Link href={citation.url} target="_blank" rel="noreferrer" appearance="subtle">
              View document
            </Link>
          )}
          </li>
        );
      })}
    </ul>
  );
}
