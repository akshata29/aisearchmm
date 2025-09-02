import { Spinner, Card, Body1 } from '@fluentui/react-components';

interface LoadingProps {
    message?: string;
    size?: 'tiny' | 'extra-small' | 'small' | 'medium' | 'large' | 'extra-large' | 'huge';
    inline?: boolean;
    overlay?: boolean;
}

export function Loading({ 
    message = 'Loading...', 
    size = 'medium', 
    inline = false,
    overlay = false
}: LoadingProps) {
    const content = (
        <>
            <Spinner size={size} />
            {message && (
                <Body1 style={{ marginTop: inline ? 0 : '12px', marginLeft: inline ? '12px' : 0 }}>
                    {message}
                </Body1>
            )}
        </>
    );

    if (overlay) {
        return (
            <div 
                style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    backgroundColor: 'rgba(0, 0, 0, 0.5)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 9999
                }}
            >
                <Card style={{ padding: '24px', textAlign: 'center' }}>
                    {content}
                </Card>
            </div>
        );
    }

    if (inline) {
        return (
            <div style={{ display: 'flex', alignItems: 'center' }}>
                {content}
            </div>
        );
    }

    return (
        <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center', 
            justifyContent: 'center',
            padding: '24px',
            textAlign: 'center'
        }}>
            {content}
        </div>
    );
}
