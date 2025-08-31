import React from 'react';
import { CheckCircle, Clock, AlertCircle } from 'lucide-react';
import { Badge, Text, Caption1 } from '@fluentui/react-components';

interface UploadProcessingStepsProps {
    currentStep: string;
    details?: any;
}

const UploadProcessingSteps: React.FC<UploadProcessingStepsProps> = ({ currentStep, details }) => {
    const steps = [
        { id: 'upload', label: 'File Upload', description: 'Uploading document to storage' },
        { id: 'analyzing', label: 'Document Analysis', description: 'Extracting text and structure' },
        { id: 'processing', label: 'Content Processing', description: 'Generating embeddings and chunks' },
        { id: 'indexing', label: 'Search Indexing', description: 'Adding to searchable index' },
        { id: 'completed', label: 'Completed', description: 'Document ready for search' },
    ];

    const getStepStatus = (stepId: string) => {
        const currentStepIndex = steps.findIndex(s => s.id === currentStep);
        const stepIndex = steps.findIndex(s => s.id === stepId);
        
        if (stepIndex < currentStepIndex) return 'completed';
        if (stepIndex === currentStepIndex) return 'active';
        return 'pending';
    };

    const getStepIcon = (status: string) => {
        switch (status) {
            case 'completed': return <CheckCircle className="step-icon completed" />;
            case 'active': return <Clock className="step-icon active" />;
            case 'error': return <AlertCircle className="step-icon error" />;
            default: return <Clock className="step-icon pending" />;
        }
    };

    return (
        <div className="upload-processing-steps">
            <Text weight="semibold" className="steps-title">Processing Pipeline</Text>
            <div className="steps-container">
                {steps.map((step, index) => {
                    const status = getStepStatus(step.id);
                    return (
                        <div key={step.id} className={`step-item ${status}`}>
                            <div className="step-indicator">
                                {getStepIcon(status)}
                                {index < steps.length - 1 && <div className="step-connector" />}
                            </div>
                            <div className="step-content">
                                <div className="step-header">
                                    <Text weight="medium">{step.label}</Text>
                                    <Badge 
                                        appearance="outline" 
                                        color={status === 'completed' ? 'success' : status === 'active' ? 'brand' : 'subtle'}
                                    >
                                        {status}
                                    </Badge>
                                </div>
                                <Caption1>{step.description}</Caption1>
                                {status === 'active' && details && (
                                    <div className="step-details">
                                        <Caption1 className="details-text">
                                            {JSON.stringify(details, null, 2)}
                                        </Caption1>
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default UploadProcessingSteps;
