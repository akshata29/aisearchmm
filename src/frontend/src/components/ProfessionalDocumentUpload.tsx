import React, { useState, useRef, useCallback } from 'react';
import { 
    Card, 
    CardHeader,
    CardPreview,
    CardFooter,
    Button,
    ProgressBar,
    Text,
    Title1,
    Title2,
    Body1,
    Caption1,
    Spinner,
    MessageBar,
    MessageBarIntent,
    Link,
    Dialog,
    DialogSurface,
    DialogTitle,
    DialogContent,
    DialogBody,
    DialogActions
} from '@fluentui/react-components';
import { 
    DocumentPdf24Regular,
    ArrowUpload24Regular,
    Checkmark24Regular,
    Clock24Regular,
    BrainCircuit24Regular,
    Eye24Regular,
    Flash24Regular,
    Cloud24Regular,
    CheckmarkCircle24Filled,
    ErrorCircle24Filled,
    DatabaseSearch24Regular,
    Image24Regular,
    ArrowReset24Regular
} from '@fluentui/react-icons';
import './ProfessionalUpload.css';
import { deleteIndex as deleteIndexApi } from '../api/api';

interface ProcessingDetails {
    steps: Array<{
        step: string;
        status: string;
        timestamp: string;
        message?: string;
        details?: any;
        error?: string;
    }>;
    figures_processed: number;
    total_figures: number;
    pages_processed: number;
    total_pages: number;
    chunks_created: number;
    images_extracted: number;
}

interface Message {
    type: MessageBarIntent;
    text: string;
}

interface UploadProgress {
    status: string;
    message: string;
    progress: number;
    step?: string;
    steps_completed?: number;
    total_steps?: number;
    details?: ProcessingDetails;
}

const ProfessionalDocumentUpload: React.FC = () => {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
    const [message, setMessage] = useState<Message | null>(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const [showErrorDetails, setShowErrorDetails] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [detailsOpen, setDetailsOpen] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [deletingIndex, setDeletingIndex] = useState(false);

    const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) {
            if (file.type === 'application/pdf') {
                setSelectedFile(file);
                setMessage(null);
            } else {
                setMessage({ type: 'error', text: 'Please select a PDF file.' });
            }
        }
    }, []);

    const handleDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        setIsDragOver(false);
        const file = event.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            setSelectedFile(file);
            setMessage(null);
        } else {
            setMessage({ type: 'error', text: 'Please select a PDF file.' });
        }
    }, []);

    const handleDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        setIsDragOver(true);
    }, []);

    const handleDragLeave = useCallback((event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        setIsDragOver(false);
    }, []);

    const pollStatus = async (uploadId: string) => {
        const maxAttempts = 120;
        let attempts = 0;

        const poll = async () => {
            try {
                const response = await fetch(`/upload_status?upload_id=${uploadId}`);
                const result = await response.json();

                if (response.ok) {
                    setUploadProgress(result);

                    if (result.status === 'completed') {
                        setMessage({ type: 'success', text: 'Document processed successfully!' });
                        setUploading(false);
                        return;
                    } else if (result.status === 'error') {
                        setMessage({ type: 'error', text: result.message || 'Processing failed' });
                        setUploading(false);
                        return;
                    }
                }

                attempts++;
                if (attempts < maxAttempts && (result.status === 'uploading' || result.status === 'processing' || result.status === 'analyzing')) {
                    setTimeout(poll, 1000);
                } else if (attempts >= maxAttempts) {
                    setMessage({ type: 'error', text: 'Processing timeout' });
                    setUploading(false);
                }
            } catch (error) {
                console.error('Status polling error:', error);
                attempts++;
                if (attempts < maxAttempts) {
                    setTimeout(poll, 1000);
                } else {
                    setMessage({ type: 'error', text: 'Failed to get processing status' });
                    setUploading(false);
                }
            }
        };

        poll();
    };

    const handleDeleteIndex = async () => {
        try {
            setDeletingIndex(true);
            const out = await deleteIndexApi();
            setMessage({ type: 'success', text: `Index deleted: ${out.deleted || 'unknown'}` });
        } catch (e) {
            setMessage({ type: 'error', text: e instanceof Error ? e.message : 'Failed to delete index' });
        } finally {
            setDeletingIndex(false);
            setDeleteOpen(false);
        }
    };

    const getStepIcon = (step: string) => {
        switch (step) {
            case 'document_analysis': return <Eye24Regular />;
            case 'content_extraction': return <DocumentPdf24Regular />;
            case 'image_processing': return <Image24Regular />;
            case 'embedding_generation': return <BrainCircuit24Regular />;
            case 'indexing_complete': return <DatabaseSearch24Regular />;
            default: return <Clock24Regular />;
        }
    };

    const getStepName = (step: string) => {
        switch (step) {
            case 'document_analysis': return 'Document Analysis';
            case 'content_extraction': return 'Content Extraction';
            case 'image_processing': return 'Image Processing';
            case 'embedding_generation': return 'Embedding Generation';
            case 'indexing_complete': return 'Search Indexing';
            default: return step.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        }
    };

    // Friendlier error extraction for backend errors
    const prettifyError = (text: string) => {
        try {
            const httpCode = (text.match(/Error code:\s*(\d{3})/) || [])[1];
            const svcCode = (text.match(/'code':\s*'([^']+)'/) || [])[1];
            const svcMsg = (text.match(/'message':\s*'([^']+)'/) || [])[1];
            const summaryParts: string[] = [];
            if (svcCode === 'DeploymentNotFound') {
                summaryParts.push('Embedding deployment not found.');
            }
            if (svcMsg) summaryParts.push(svcMsg);
            if (httpCode && !summaryParts.length) summaryParts.push(`Error ${httpCode}`);
            const summary = summaryParts.join(' ');
            return { summary: summary || 'Processing failed', details: text };
        } catch {
            return { summary: text, details: text };
        }
    };

    const handleUpload = async () => {
        if (!selectedFile) return;

        setUploading(true);
        setMessage(null);
        setUploadProgress(null);

        try {
            const formData = new FormData();
            formData.append('file', selectedFile);

            const uploadResponse = await fetch('/upload', {
                method: 'POST',
                body: formData,
            });

            const uploadResult = await uploadResponse.json();

            if (!uploadResponse.ok) {
                throw new Error(uploadResult.error || 'Upload failed');
            }

            const processResponse = await fetch('/process_document', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    upload_id: uploadResult.upload_id,
                }),
            });

            const processResult = await processResponse.json();

            if (!processResponse.ok) {
                throw new Error(processResult.error || 'Processing failed');
            }

            pollStatus(uploadResult.upload_id);

        } catch (error) {
            setUploading(false);
            const text = error instanceof Error ? error.message : 'Upload failed';
            const pretty = prettifyError(text);
            setMessage({ type: 'error', text: pretty.summary });
            // Store raw details in progress object so we can optionally show it
            setUploadProgress((prev) => prev ? prev : ({ status: 'error', message: text, progress: 100 } as UploadProgress));
        }
    };

    const handleReset = () => {
        setSelectedFile(null);
        setUploading(false);
        setUploadProgress(null);
        setMessage(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const formatFileSize = (bytes: number) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    return (
        <div className="professional-upload-container">
            {/* Header Section */}
            <div className="upload-hero">
                <div className="hero-content">
                    <Title1 className="hero-title">
                        <DocumentPdf24Regular className="hero-icon" />
                        AI Document Intelligence
                    </Title1>
                    <Body1 className="hero-subtitle">
                        Transform your PDFs into searchable knowledge with advanced AI processing
                    </Body1>
                </div>
            </div>

            {/* Main Upload Section */}
            <div className="upload-workspace">
                <div className="upload-layout">
                <Card className="upload-card" role="region" aria-label="Upload document">
                    <CardHeader
                        header={
                            <div className="card-header">
                                <Title2>Upload Document</Title2>
                                <Caption1>Supported formats: PDF (up to 50MB)</Caption1>
                            </div>
                        }
                    />
                    
                    <CardPreview>
                        <div 
                            className={`drop-zone ${isDragOver ? 'drag-over' : ''} ${selectedFile ? 'has-file' : ''}`}
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                        >
                            {selectedFile ? (
                                <div className="file-preview">
                                    <DocumentPdf24Regular className="file-icon" />
                                    <div className="file-info">
                                        <Text weight="semibold">{selectedFile.name}</Text>
                                        <Caption1>{formatFileSize(selectedFile.size)}</Caption1>
                                    </div>
                                    <div className="file-badge">PDF</div>
                                </div>
                            ) : (
                                <div className="drop-prompt">
                                    <Cloud24Regular className="upload-icon" />
                                    <Text size={500} weight="medium">Drop your PDF here</Text>
                                    <Caption1>or click to browse files</Caption1>
                                </div>
                            )}
                        </div>

                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf"
                            className="visually-hidden"
                            onChange={handleFileSelect}
                        />
                    </CardPreview>

                    <CardFooter>
                        <div className="card-actions">
                            <Button 
                                appearance="primary" 
                                size="large"
                                disabled={!selectedFile || uploading}
                                onClick={handleUpload}
                                icon={<ArrowUpload24Regular />}
                            >
                                {uploading ? 'Processing...' : 'Upload & Process'}
                            </Button>
                            
                            {selectedFile && !uploading && (
                                <Button 
                                    appearance="subtle" 
                                    onClick={handleReset}
                                    icon={<ArrowReset24Regular />}
                                >
                                    Clear
                                </Button>
                            )}
                            <Button 
                                appearance="secondary"
                                onClick={() => setDeleteOpen(true)}
                                disabled={uploading || deletingIndex}
                            >
                                {deletingIndex ? 'Deleting…' : 'Delete Index'}
                            </Button>
                        </div>
                    </CardFooter>
                </Card>

                {/* Status Messages */}
                {message && (
                    <div className="status-message" role="status" aria-live="polite">
                        <MessageBar intent={message.type}>
                            {message.type === 'success' && <CheckmarkCircle24Filled />}
                            {message.type === 'error' && <ErrorCircle24Filled />}
                            <span>{message.text}</span>
                            {message.type === 'error' && uploadProgress?.message && (
                                <>
                                    {' '}
                                    <Link appearance="subtle" onClick={() => setShowErrorDetails(v => !v)}>
                                        {showErrorDetails ? 'Hide details' : 'Show technical details'}
                                    </Link>
                                </>
                            )}
                        </MessageBar>
                        {showErrorDetails && uploadProgress?.message && (
                            <pre className="error-raw" aria-label="Error details">{uploadProgress.message}</pre>
                        )}
                    </div>
                )}

                {/* Processing Progress */}
                {uploadProgress && (
                    <Card className="progress-card" role="region" aria-label="Processing progress">
                        <CardHeader
                            header={
                                <div className="progress-header">
                                    <div className="progress-title">
                                        <Title2>Processing Document</Title2>
                                        <Caption1 className="progress-message">
                                            {uploadProgress.message}
                                        </Caption1>
                                    </div>
                                    <div className="progress-actions">
                                        {uploading && <Spinner size="medium" />}
                                        {uploadProgress?.details && (
                                            <Button appearance="secondary" size="small" onClick={() => setDetailsOpen(true)}>
                                                View details
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            }
                        />
                        
                        <CardPreview>
                            <div className="progress-content">
                                <div className="progress-bar-section">
                                    <div className="progress-info">
                                        <Text size={300}>{uploadProgress.progress}% Complete</Text>
                                        <Caption1>Status: {uploadProgress.status}</Caption1>
                                    </div>
                                    <ProgressBar 
                                        value={uploadProgress.progress / 100} 
                                        className="main-progress-bar"
                                    />
                                </div>

                                {/* Compact step visualization */}
                                <div className="processing-steps">
                                    <div className={`step ${uploadProgress.progress > 0 ? 'completed' : 'pending'}`}>
                                        <ArrowUpload24Regular />
                                        <span>Upload</span>
                                    </div>
                                    <div className={`step ${uploadProgress.progress > 25 ? 'completed' : uploadProgress.progress > 0 ? 'active' : 'pending'}`}>
                                        <Eye24Regular />
                                        <span>Analysis</span>
                                    </div>
                                    <div className={`step ${uploadProgress.progress > 50 ? 'completed' : uploadProgress.progress > 25 ? 'active' : 'pending'}`}>
                                        <BrainCircuit24Regular />
                                        <span>Processing</span>
                                    </div>
                                    <div className={`step ${uploadProgress.progress > 75 ? 'completed' : uploadProgress.progress > 50 ? 'active' : 'pending'}`}>
                                        <Flash24Regular />
                                        <span>Indexing</span>
                                    </div>
                                    <div className={`step ${uploadProgress.progress >= 100 ? 'completed' : uploadProgress.progress > 75 ? 'active' : 'pending'}`}>
                                        <Checkmark24Regular />
                                        <span>Complete</span>
                                    </div>
                                </div>

                                {/* Compact KPIs */}
                                {uploadProgress.details && (
                                    <div className="stats-grid compact">
                                        <div className="stat-card">
                                            <div className="stat-value">{uploadProgress.details.pages_processed || 0}</div>
                                            <div className="stat-label">Pages</div>
                                        </div>
                                        <div className="stat-card">
                                            <div className="stat-value">{uploadProgress.details.images_extracted || 0}</div>
                                            <div className="stat-label">Images</div>
                                        </div>
                                        <div className="stat-card">
                                            <div className="stat-value">{uploadProgress.details.figures_processed || 0}</div>
                                            <div className="stat-label">Figures</div>
                                        </div>
                                        <div className="stat-card">
                                            <div className="stat-value">{uploadProgress.details.chunks_created || 0}</div>
                                            <div className="stat-label">Chunks</div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </CardPreview>
                    </Card>
                )}
                {/* Details Dialog */}
                <Dialog open={detailsOpen} onOpenChange={(_, data) => setDetailsOpen(!!data.open)}>
                    <DialogSurface>
                        <DialogBody>
                            <DialogTitle>Processing Details</DialogTitle>
                            <DialogContent>
                                {uploadProgress?.details ? (
                                    <div className="processing-details">
                                        <div className="stats-grid">
                                            <div className="stat-card">
                                                <div className="stat-value">{uploadProgress.details.pages_processed || 0}</div>
                                                <div className="stat-label">Pages Processed</div>
                                            </div>
                                            <div className="stat-card">
                                                <div className="stat-value">{uploadProgress.details.images_extracted || 0}</div>
                                                <div className="stat-label">Images Extracted</div>
                                            </div>
                                            <div className="stat-card">
                                                <div className="stat-value">{uploadProgress.details.figures_processed || 0}</div>
                                                <div className="stat-label">Figures Processed</div>
                                            </div>
                                            <div className="stat-card">
                                                <div className="stat-value">{uploadProgress.details.chunks_created || 0}</div>
                                                <div className="stat-label">Text Chunks</div>
                                            </div>
                                        </div>

                                        {uploadProgress.details.steps && uploadProgress.details.steps.length > 0 && (
                                            <div className="processing-timeline">
                                                <Title2>Processing Timeline</Title2>
                                                <div className="timeline">
                                                    {uploadProgress.details.steps.map((step, index) => (
                                                        <div key={index} className={`timeline-item ${step.status}`}>
                                                            <div className="timeline-marker">
                                                                {getStepIcon(step.step)}
                                                            </div>
                                                            <div className="timeline-content">
                                                                <Text weight="semibold" className="break-words">
                                                                    {getStepName(step.step)}
                                                                </Text>
                                                                <Caption1 className="break-words">
                                                                    {step.message || step.status}
                                                                </Caption1>
                                                                <Caption1 className="timestamp">
                                                                    {new Date(step.timestamp).toLocaleTimeString()}
                                                                </Caption1>
                                                                {step.error && (
                                                                    <MessageBar 
                                                                        intent="error" 
                                                                        className="error-details break-words"
                                                                    >
                                                                        {step.error}
                                                                    </MessageBar>
                                                                )}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <Caption1>No details available yet.</Caption1>
                                )}
                            </DialogContent>
                            <DialogActions>
                                <Button appearance="primary" onClick={() => setDetailsOpen(false)}>Close</Button>
                            </DialogActions>
                        </DialogBody>
                    </DialogSurface>
                </Dialog>
                {/* Delete Index Confirmation */}
                <Dialog open={deleteOpen} onOpenChange={(_, data) => setDeleteOpen(!!data.open)}>
                    <DialogSurface>
                        <DialogBody>
                            <DialogTitle>Delete Search Index</DialogTitle>
                            <DialogContent>
                                <Body1>This will delete the configured search index and cannot be undone. Continue?</Body1>
                            </DialogContent>
                            <DialogActions>
                                <Button appearance="secondary" onClick={() => setDeleteOpen(false)} disabled={deletingIndex}>Cancel</Button>
                                <Button appearance="primary" onClick={handleDeleteIndex} disabled={deletingIndex}>Delete</Button>
                            </DialogActions>
                        </DialogBody>
                    </DialogSurface>
                </Dialog>
                </div>
            </div>
        </div>
    );
};

export default ProfessionalDocumentUpload;
