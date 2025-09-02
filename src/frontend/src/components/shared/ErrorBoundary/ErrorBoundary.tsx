import { Component, ErrorInfo, ReactNode } from 'react';
import { Button, Card, Title2, Body1, MessageBar } from '@fluentui/react-components';
import { ErrorCircle24Regular, ArrowClockwise24Regular } from '@fluentui/react-icons';

interface ErrorBoundaryProps {
    children: ReactNode;
    fallback?: ReactNode;
    onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface ErrorBoundaryState {
    hasError: boolean;
    error?: Error | undefined;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('ErrorBoundary caught an error:', error, errorInfo);
        this.props.onError?.(error, errorInfo);
    }

    handleRetry = () => {
        this.setState({ hasError: false, error: undefined });
    };

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }

            return (
                <Card style={{ padding: '24px', margin: '16px', textAlign: 'center' }}>
                    <ErrorCircle24Regular style={{ color: 'var(--colorPaletteRedForeground1)', marginBottom: '16px' }} />
                    <Title2 style={{ marginBottom: '12px' }}>Something went wrong</Title2>
                    <Body1 style={{ marginBottom: '16px', color: 'var(--colorNeutralForeground2)' }}>
                        We encountered an unexpected error. Please try refreshing the page or contact support if the problem persists.
                    </Body1>
                    
                    {import.meta.env.DEV && this.state.error && (
                        <MessageBar 
                            intent="error" 
                            style={{ marginBottom: '16px', textAlign: 'left' }}
                        >
                            <strong>Error Details:</strong> {this.state.error.message}
                        </MessageBar>
                    )}
                    
                    <Button 
                        appearance="primary" 
                        icon={<ArrowClockwise24Regular />}
                        onClick={this.handleRetry}
                    >
                        Try Again
                    </Button>
                </Card>
            );
        }

        return this.props.children;
    }
}
