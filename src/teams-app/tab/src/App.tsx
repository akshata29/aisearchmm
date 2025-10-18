import { useCallback, useEffect, useMemo, useState } from 'react';
import { FluentProvider, MessageBar, MessageBarBody, MessageBarTitle, teamsDarkTheme, teamsHighContrastTheme, teamsLightTheme } from '@fluentui/react-components';
import { motion } from 'framer-motion';
import { TeamsTabHeader } from '@/components/TeamsTabHeader';
import { SearchForm } from '@/components/SearchForm';
import { AnswerPanel } from '@/components/AnswerPanel';
import { useTeamsContext } from '@/hooks/useTeamsContext';
import { useQueryParam } from '@/hooks/useQueryParam';
import { askRag } from '@/lib/api';
import type { RagAnswer } from '@/lib/types';

const SAMPLE_QUERIES = [
  'What are the newest investment insights on global markets?',
  'Summarize the compliance guidance for advisors in Q3.',
  'Which citations mention multimodal research wins recently?'
];

export default function App() {
  const teams = useTeamsContext();
  const initialQuery = useQueryParam('q') ?? SAMPLE_QUERIES[0];
  const [answer, setAnswer] = useState<RagAnswer | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [info, setInfo] = useState<string | undefined>();

  const theme = useMemo(() => {
    switch (teams.theme) {
      case 'dark':
        return teamsDarkTheme;
      case 'contrast':
        return teamsHighContrastTheme;
      default:
        return teamsLightTheme;
    }
  }, [teams.theme]);

  const updateUrl = useCallback((query: string) => {
    if (typeof window === 'undefined') {
      return;
    }
    const next = new URL(window.location.href);
    if (query) {
      next.searchParams.set('q', query);
    } else {
      next.searchParams.delete('q');
    }
    window.history.replaceState(null, document.title, next.toString());
  }, []);

  const runQuery = useCallback(
    async (query: string) => {
      setIsLoading(true);
      setError(undefined);
      setInfo(undefined);
      try {
        const response = await askRag(query);
        setAnswer(response);
        setError(undefined);
        setInfo(`Answer refreshed for “${query.slice(0, 48)}${query.length > 48 ? '…' : ''}”.`);
        updateUrl(query);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error contacting the RAG service.';
        setError(message);
        setAnswer(undefined);
        setInfo(undefined);
        updateUrl(query);
      } finally {
        setIsLoading(false);
      }
    },
    [updateUrl]
  );

  useEffect(() => {
    if (!initialQuery) {
      return;
    }
    void runQuery(initialQuery);
  }, [initialQuery, runQuery]);

  const handleStandaloneOpen = useCallback(() => {
    const baseUrl = new URL(window.location.href);
    const url = `${baseUrl.origin}${baseUrl.pathname}?q=${encodeURIComponent(initialQuery ?? '')}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  }, [initialQuery]);

  const handleReset = useCallback(() => {
    setAnswer(undefined);
    setError(undefined);
    setInfo(undefined);
    updateUrl('');
  }, [updateUrl]);

  return (
    <FluentProvider theme={theme} className="tab-shell">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <TeamsTabHeader
          userName={teams.userName}
          entityId={teams.entityId}
          onOpenStandalone={handleStandaloneOpen}
          onReset={handleReset}
          isBusy={isLoading}
        />
      </motion.div>

      <SearchForm defaultQuery={initialQuery} onSubmit={runQuery} isBusy={isLoading} />

      {info && !error && (
        <MessageBar intent="info" role="status">
          <MessageBarBody>
            <MessageBarTitle>Update</MessageBarTitle>
            {info}
          </MessageBarBody>
        </MessageBar>
      )}

      {error && (
        <MessageBar intent="error" role="alert">
          <MessageBarBody>
            <MessageBarTitle>We hit a snag</MessageBarTitle>
            {error}
          </MessageBarBody>
        </MessageBar>
      )}

      <AnswerPanel answer={answer} isLoading={isLoading} />

      <footer className="meta-footnote">
        Responses reflect the latest indexed content and may link to external documents.
      </footer>
    </FluentProvider>
  );
}
