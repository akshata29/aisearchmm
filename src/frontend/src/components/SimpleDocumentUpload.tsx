import React, { useState, useRef } from 'react';
import './DocumentUpload.css';

interface Message {
    type: 'success' | 'error' | 'info';
    text: string;
}

interface UploadProgress {
    status: string;
    message: string;
    progress: number;
}

const DocumentUpload: React.FC = () => {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [processing, setProcessing] = useState(false);
    const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
    const [message, setMessage] = useState<Message | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) {
            if (file.type === 'application/pdf') {
                setSelectedFile(file);
                setMessage(null);
            } else {
                setMessage({ type: 'error', text: 'Please select a PDF file.' });
            }
        }
    };

    const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        const file = event.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            setSelectedFile(file);
            setMessage(null);
        } else {
            setMessage({ type: 'error', text: 'Please select a PDF file.' });
        }
    };

    const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
    };

    const pollStatus = async (uploadId: string) => {
        const maxAttempts = 120; // 2 minutes with 1-second intervals
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
                        setProcessing(false);
                        return;
                    } else if (result.status === 'error') {
                        setMessage({ type: 'error', text: result.message || 'Processing failed' });
                        setUploading(false);
                        setProcessing(false);
                        return;
                    }
                }

                attempts++;
                if (attempts < maxAttempts && (result.status === 'uploading' || result.status === 'processing' || result.status === 'analyzing')) {
                    setTimeout(poll, 1000); // Poll every second
                } else if (attempts >= maxAttempts) {
                    setMessage({ type: 'error', text: 'Processing timeout' });
                    setUploading(false);
                    setProcessing(false);
                }
            } catch (error) {
                console.error('Status polling error:', error);
                attempts++;
                if (attempts < maxAttempts) {
                    setTimeout(poll, 1000);
                } else {
                    setMessage({ type: 'error', text: 'Failed to get processing status' });
                    setUploading(false);
                    setProcessing(false);
                }
            }
        };

        poll();
    };

    const handleUpload = async () => {
        if (!selectedFile) return;

        setUploading(true);
        setProcessing(true);
        setMessage(null);
        setUploadProgress({ status: 'uploading', message: 'Preparing upload...', progress: 0 });

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

            // Start processing
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

            // Start polling for status
            pollStatus(uploadResult.upload_id);

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

    const getProgressBarClass = () => {
        if (!uploadProgress) return '';
        switch (uploadProgress.status) {
            case 'completed':
                return 'progress-success';
            case 'error':
                return 'progress-error';
            default:
                return 'progress-active';
        }
    };

    return (
        <div className="document-upload">
            <div className="upload-header">
                <h2>Upload Document</h2>
                <p>Upload a PDF document to add it to your knowledge base</p>
            </div>

            {!uploading && (
                <div
                    className="upload-zone"
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onClick={() => fileInputRef.current?.click()}
                >
                    <div className="upload-icon">📄</div>
                    <p>
                        {selectedFile
                            ? `Selected: ${selectedFile.name}`
                            : 'Drag and drop a PDF file here or click to browse'}
                    </p>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf"
                        onChange={handleFileSelect}
                        style={{ display: 'none' }}
                    />
                </div>
            )}

            {selectedFile && !uploading && (
                <div className="upload-actions">
                    <button className="upload-btn" onClick={handleUpload}>
                        Upload and Process
                    </button>
                    <button className="reset-btn" onClick={handleReset}>
                        Reset
                    </button>
                </div>
            )}

            {uploadProgress && (
                <div className="progress-section">
                    <div className="progress-info">
                        <span className="progress-status">{uploadProgress.message}</span>
                        <span className="progress-percent">{uploadProgress.progress}%</span>
                    </div>
                    <div className="progress-bar">
                        <div
                            className={`progress-fill ${getProgressBarClass()}`}
                            style={{ width: `${uploadProgress.progress}%` }}
                        ></div>
                    </div>
                </div>
            )}

            {message && (
                <div className={`message ${message.type}`}>
                    {message.text}
                </div>
            )}

            {uploading && (
                <div className="upload-status">
                    <div className="spinner"></div>
                    <p>
                        {processing
                            ? uploadProgress?.message || 'Processing document...'
                            : 'Uploading...'}
                    </p>
                </div>
            )}
        </div>
    );
};

export default DocumentUpload;
