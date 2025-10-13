import { useEffect, useState } from 'react';
import * as microsoftTeams from '@microsoft/teams-js';

export interface TeamsContext {
  isInTeams: boolean;
  userId?: string;
  userPrincipalName?: string;
  theme?: string;
  locale?: string;
  teamId?: string;
  channelId?: string;
  hostName?: string;
}

export function useTeamsContext(): TeamsContext {
  const [context, setContext] = useState<TeamsContext>({
    isInTeams: false
  });

  useEffect(() => {
    const initializeTeams = async () => {
      try {
        // Initialize Teams SDK
        await microsoftTeams.app.initialize();
        
        // Get Teams context
        const teamsContext = await microsoftTeams.app.getContext();
        
        const newContext: TeamsContext = {
          isInTeams: true
        };

        if (teamsContext.user?.id) newContext.userId = teamsContext.user.id;
        if (teamsContext.user?.userPrincipalName) newContext.userPrincipalName = teamsContext.user.userPrincipalName;
        if (teamsContext.app?.theme) newContext.theme = teamsContext.app.theme;
        if (teamsContext.app?.locale) newContext.locale = teamsContext.app.locale;
        if (teamsContext.team?.internalId) newContext.teamId = teamsContext.team.internalId;
        if (teamsContext.channel?.id) newContext.channelId = teamsContext.channel.id;
        if (teamsContext.app?.host?.name) newContext.hostName = teamsContext.app.host.name;

        setContext(newContext);

        // Notify Teams that the app has loaded
        microsoftTeams.app.notifySuccess();
        
        console.log('Teams integration initialized successfully', teamsContext);
      } catch (error) {
        // Not running in Teams, that's okay
        console.log('Not running in Teams environment:', error);
        setContext({
          isInTeams: false
        });
      }
    };

    initializeTeams();
  }, []);

  return context;
}

// Hook for Teams theme integration
export function useTeamsTheme() {
  const [theme, setTheme] = useState<string>('default');

  useEffect(() => {
    const handleThemeChange = (newTheme: string) => {
      setTheme(newTheme);
      // Apply theme to document
      document.body.setAttribute('data-teams-theme', newTheme);
    };

    const initTheme = async () => {
      try {
        await microsoftTeams.app.initialize();
        const context = await microsoftTeams.app.getContext();
        handleThemeChange(context.app.theme || 'default');

        // Listen for theme changes
        microsoftTeams.app.registerOnThemeChangeHandler(handleThemeChange);
      } catch (error) {
        // Not in Teams, use default theme
        handleThemeChange('default');
      }
    };

    initTheme();
  }, []);

  return theme;
}