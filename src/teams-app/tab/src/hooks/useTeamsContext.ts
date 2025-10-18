import { useEffect, useMemo, useState } from 'react';
import { app } from '@microsoft/teams-js';

export type TeamsTheme = 'default' | 'dark' | 'contrast';

interface TeamsDetails {
  theme: TeamsTheme;
  userName?: string;
  userObjectId?: string;
  tenantId?: string;
  locale?: string;
  entityId?: string;
  initialized: boolean;
  error?: Error;
}

const defaultState: TeamsDetails = {
  theme: 'default',
  initialized: false
};

export function useTeamsContext(): TeamsDetails {
  const [state, setState] = useState<TeamsDetails>(defaultState);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        await app.initialize();
        const context = await app.getContext();
        if (cancelled) {
          return;
        }

        setState({
          theme: (context.app?.theme as TeamsTheme) ?? 'default',
          userName: context.user?.userPrincipalName,
          userObjectId: context.user?.id,
          tenantId: context.user?.tenant?.id,
          locale: context.app?.locale,
          entityId: context.page?.id,
          initialized: true
        });

        app.registerOnThemeChangeHandler((newTheme) => {
          setState((prev) => ({
            ...prev,
            theme: (newTheme as TeamsTheme) ?? 'default'
          }));
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState({
          ...defaultState,
          initialized: true,
          error: error instanceof Error ? error : new Error('Failed to initialize Teams SDK')
        });
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  return useMemo(() => state, [state]);
}
