import React from 'react';
import { useTeamsContext, useTeamsTheme } from '../hooks/useTeamsContext';
import { 
  Card,
  CardHeader,
  Text,
  Badge,
  Divider,
  Title3,
  Button,
  tokens
} from '@fluentui/react-components';

export const TeamsIntegrationTest: React.FC = () => {
  const teamsContext = useTeamsContext();
  const theme = useTeamsTheme();

  const testTeamsFeatures = () => {
    if (teamsContext.isInTeams && (window as any).microsoftTeams) {
      // Test Teams authentication
      (window as any).microsoftTeams.authentication.getAuthToken({
        successCallback: (_token: string) => {
          alert('✅ Teams SSO Token obtained successfully!');
        },
        failureCallback: (error: string) => {
          alert(`❌ Teams SSO failed: ${error}`);
        }
      });
    } else {
      alert('Teams SDK not available. Make sure you\'re running in Teams context.');
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <Card>
        <CardHeader
          header={<Title3>🏢 Microsoft Teams Integration Status</Title3>}
        />
        
        <div style={{ padding: '20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Teams Detection */}
            <div>
              <Text weight="semibold">Teams Environment:</Text>
              <Badge 
                color={teamsContext.isInTeams ? 'success' : 'warning'}
                style={{ marginLeft: '8px' }}
              >
                {teamsContext.isInTeams ? '✅ Running in Teams' : '⚠️ Standalone Mode'}
              </Badge>
            </div>

            <Divider />

            {/* Current Theme */}
            <div>
              <Text weight="semibold">Current Theme: </Text>
              <Badge color="informative" style={{ marginLeft: '8px' }}>
                {theme || teamsContext.theme || 'Default'}
              </Badge>
            </div>

            {teamsContext.isInTeams && (
              <>
                <Divider />
                
                {/* User Information */}
                {teamsContext.userId && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
                      <Text style={{ marginRight: '8px' }}>👤</Text>
                      <Text weight="semibold">User Information</Text>
                    </div>
                    <div style={{ paddingLeft: '24px' }}>
                      <Text>User ID: {teamsContext.userId}</Text><br />
                      {teamsContext.userPrincipalName && (
                        <Text>UPN: {teamsContext.userPrincipalName}</Text>
                      )}
                    </div>
                  </div>
                )}

                {/* Team Information */}
                {teamsContext.teamId && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
                      <Text style={{ marginRight: '8px' }}>👥</Text>
                      <Text weight="semibold">Team Information</Text>
                    </div>
                    <div style={{ paddingLeft: '24px' }}>
                      <Text>Team ID: {teamsContext.teamId}</Text><br />
                      {teamsContext.channelId && (
                        <Text>Channel ID: {teamsContext.channelId}</Text>
                      )}
                      {teamsContext.hostName && (
                        <Text>Host: {teamsContext.hostName}</Text>
                      )}
                    </div>
                  </div>
                )}

                <Divider />

                {/* Test Button */}
                <div>
                  <Button 
                    appearance="primary" 
                    onClick={testTeamsFeatures}
                  >
                    🔑 Test Teams SSO
                  </Button>
                </div>
              </>
            )}

            {!teamsContext.isInTeams && (
              <div style={{ 
                padding: '16px', 
                backgroundColor: tokens.colorNeutralBackground2,
                borderRadius: '8px' 
              }}>
                <Text weight="semibold">💡 To test Teams integration:</Text>
                <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
                  <li>Start the Teams bot: <code>npm start</code> in src/teams-app folder</li>
                  <li>Open Teams DevTools: <code>http://localhost:3979/devtools</code></li>
                  <li>Click "Preview in Teams" to upload the app</li>
                  <li>Navigate to the "RAG Assistant" tab</li>
                </ol>
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
};