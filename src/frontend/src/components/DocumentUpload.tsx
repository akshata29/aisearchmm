import { useState, useRef, useEffect } from "react";
import {
    Button,
    Card,
    CardHeader,
    CardPreview,
    Text,
    ProgressBar,
    Spinner,
    Body1,
    Title2,
    Caption1,
    MessageBar,
    MessageBarBody,
} from "@fluentui/react-components";
import {
    DocumentRegular,
    ArrowUploadRegular,
    CheckmarkCircleRegular,
    ErrorCircleRegular,
} from "@fluentui/react-icons";

import "./DocumentUpload.css";

interface UploadProgress {
    type: 'progress' | 'complete' | 'error';
    stage: string;
    message: string;
    progress: number;
}

export const DocumentUpload = () => {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [processing, setProcessing] = useState(false);
    const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
    const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        // Initialize WebSocket connection for progress updates
        const websocket = new WebSocket(`ws://localhost:5000/upload_progress`);
        
        websocket.onopen = () => {
            console.log('WebSocket connected');
        };

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data) as UploadProgress;
            setUploadProgress(data);
            
            if (data.type === 'complete') {
                setProcessing(false);
                setMessage({ type: 'success', text: data.message });
            } else if (data.type === 'error') {
                setProcessing(false);
                setMessage({ type: 'error', text: data.message });
            }
        };

        websocket.onclose = () => {
            console.log('WebSocket disconnected');
        };

        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        return () => {
            if (websocket.readyState === WebSocket.OPEN) {
                websocket.close();
            }
        };
    }, []);

    const handleFileSelect = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) {
            if (file.type !== 'application/pdf') {
                setMessage({ type: 'error', text: 'Only PDF files are supported' });
                return;
            }
            setSelectedFile(file);
            setMessage(null);
            setUploadProgress(null);
        }
    };

    const handleUpload = async () => {
        if (!selectedFile) return;

        setUploading(true);
        setMessage(null);

        try {
            // Upload file
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

            setUploading(false);
            setProcessing(true);
            setMessage({ type: 'info', text: 'File uploaded successfully. Starting document processing...' });

            // Start processing
            const processResponse = await fetch('/process_document', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    temp_path: uploadResult.temp_path,
                    filename: uploadResult.filename,
                }),
            });

            const processResult = await processResponse.json();

            if (!processResponse.ok) {
                throw new Error(processResult.error || 'Processing failed');
            }

        } catch (error) {
            setUploading(false);
            setProcessing(false);
            setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Upload failed' });
        }
    };

    const handleReset = () => {
        setSelectedFile(null);
        setUploading(false);
        setProcessing(false);
        setUploadProgress(null);
        setMessage(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const getProgressStageIcon = (stage: string) => {
        switch (stage) {
            case 'complete':
                return <CheckmarkCircleRegular className="progress-icon success" />;
            case 'error':
                return <ErrorCircleRegular className="progress-icon error" />;
            default:
                return <Spinner size="small" />;
        }
    };

    return (
        <div className="document-upload">
            <div className="upload-header">
                <Title2>Upload Documents</Title2>
                <Caption1>Upload PDF documents to add them to your knowledge base</Caption1>
            </div>

            {message && (
                <MessageBar intent={message.type as any} className="upload-message">
                    <MessageBarBody>{message.text}</MessageBarBody>
                </MessageBar>
            )}

            <Card className="upload-card">
                <CardHeader
                    image={<DocumentRegular />}
                    header={<Text weight="semibold">Select Document</Text>}
                    description={<Text size={200}>Choose a PDF file to upload and process</Text>}
                />
                <CardPreview className="upload-area">
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf"
                        onChange={handleFileChange}
                        style={{ display: 'none' }}
                    />
                    
                    {selectedFile ? (
                        <div className="file-selected">
                            <DocumentRegular className="file-icon" />
                            <div className="file-info">
                                <Body1>{selectedFile.name}</Body1>
                                <Caption1>{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</Caption1>
                            </div>
                            <Button 
                                appearance="secondary" 
                                onClick={handleReset}
                                disabled={uploading || processing}
                            >
                                Change File
                            </Button>
                        </div>
                    ) : (
                        <div className="file-drop-zone" onClick={handleFileSelect}>
                            <ArrowUploadRegular className="upload-icon" />
                            <Body1>Click to select a PDF file</Body1>
                            <Caption1>Only PDF files are supported</Caption1>
                        </div>
                    )}
                </CardPreview>

                {selectedFile && (
                    <div className="upload-actions">
                        <Button
                            appearance="primary"
                            icon={uploading || processing ? <Spinner size="small" /> : <ArrowUploadRegular />}
                            onClick={handleUpload}
                            disabled={uploading || processing}
                        >
                            {uploading ? 'Uploading...' : processing ? 'Processing...' : 'Upload & Process'}
                        </Button>
                    </div>
                )}
            </Card>

            {uploadProgress && (
                <Card className="progress-card">
                    <CardHeader
                        image={getProgressStageIcon(uploadProgress.stage)}
                        header={<Text weight="semibold">Processing Progress</Text>}
                        description={<Text size={200}>{uploadProgress.message}</Text>}
                    />
                    
                    {uploadProgress.type !== 'error' && uploadProgress.type !== 'complete' && (
                        <div className="progress-content">
                            <ProgressBar value={uploadProgress.progress / 100} />
                            <Caption1>{uploadProgress.progress}% complete</Caption1>
                        </div>
                    )}
                </Card>
            )}
        </div>
    );
};
