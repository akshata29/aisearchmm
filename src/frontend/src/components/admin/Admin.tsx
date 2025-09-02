import React, { useState, useEffect } from 'react';
import {
    Text,
    Button,
    Table,
    TableHeader,
    TableRow,
    TableHeaderCell,
    TableBody,
    TableCell,
    Card,
    CardHeader,
    CardPreview,
    Spinner,
    MessageBar,
    Dialog,
    DialogSurface,
    DialogTitle,
    DialogContent,
    DialogBody,
    DialogActions,
    Field,
    Input,
    Badge,
    CounterBadge,
} from '@fluentui/react-components';
import {
    DeleteRegular,
    DocumentRegular,
    ImageRegular,
    AlertRegular,
} from '@fluentui/react-icons';
import './Admin.css';
import { TIMEOUTS } from '../../constants/app';

interface DocumentStats {
    document_title: string;
    text_chunks: number;
    image_chunks: number;
    total_chunks: number;
    document_type: string;
    published_date?: string;
    text_document_ids: string[];
    image_document_ids: string[];
}

interface DocumentChunk {
    content_id: string;
    document_title: string;
    content_text?: string;
    content_path?: string;
    text_document_id?: string;
    image_document_id?: string;
    document_type: string;
    published_date?: string;
    locationMetadata?: any;
}

interface AdminStats {
    total_documents: number;
    total_chunks: number;
    documents: DocumentStats[];
}

export const Admin: React.FC = () => {
    const [stats, setStats] = useState<AdminStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState<{ type: 'document' | 'chunk'; id: string; title?: string } | null>(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [searchFilter, setSearchFilter] = useState('');
    const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
    const [documentChunks, setDocumentChunks] = useState<DocumentChunk[]>([]);
    const [chunksLoading, setChunksLoading] = useState(false);

    const fetchStats = async () => {
        try {
            setLoading(true);
            setError(null);
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), TIMEOUTS.API_REQUEST);
            
            const response = await fetch('/api/admin/documents', {
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`Failed to fetch statistics: ${response.statusText}`);
            }
            const data = await response.json();
            setStats(data);
        } catch (err) {
            if (err instanceof DOMException && err.name === 'AbortError') {
                setError('Request timed out while fetching document statistics');
            } else {
                setError(err instanceof Error ? err.message : 'Failed to fetch statistics');
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchStats();
    }, []);

    const handleDeleteDocument = async (documentTitle: string) => {
        setDeleteTarget({ type: 'document', id: documentTitle, title: documentTitle });
        setDeleteConfirmOpen(true);
    };

    const fetchDocumentChunks = async (documentTitle: string) => {
        try {
            setChunksLoading(true);
            setError(null);
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), TIMEOUTS.API_REQUEST);
            
            const response = await fetch(`/api/admin/document_chunks?document_title=${encodeURIComponent(documentTitle)}`, {
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`Failed to fetch document chunks: ${response.statusText}`);
            }
            const data = await response.json();
            // Extract the chunks array from the response object
            const chunks = Array.isArray(data) ? data : (data.chunks || []);
            setDocumentChunks(chunks);
            setSelectedDocument(documentTitle);
        } catch (err) {
            if (err instanceof DOMException && err.name === 'AbortError') {
                setError('Request timed out while fetching document chunks');
            } else {
                setError(err instanceof Error ? err.message : 'Failed to fetch document chunks');
            }
            setDocumentChunks([]); // Reset to empty array on error
        } finally {
            setChunksLoading(false);
        }
    };

    const handleDocumentClick = (documentTitle: string) => {
        if (selectedDocument === documentTitle) {
            // If already selected, close the details
            setSelectedDocument(null);
            setDocumentChunks([]);
        } else {
            // Fetch and show chunks for this document
            fetchDocumentChunks(documentTitle);
        }
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;

        try {
            setDeleteLoading(true);
            const endpoint = deleteTarget.type === 'document' 
                ? '/api/admin/delete_document' 
                : '/api/admin/delete_chunk';
            
            const body = deleteTarget.type === 'document'
                ? { document_title: deleteTarget.id }
                : { content_id: deleteTarget.id };

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(body),
            });

            if (!response.ok) {
                throw new Error(`Delete failed: ${response.statusText}`);
            }

            // Refresh stats after successful deletion
            await fetchStats();
            setDeleteConfirmOpen(false);
            setDeleteTarget(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Delete operation failed');
        } finally {
            setDeleteLoading(false);
        }
    };

    const filteredDocuments = stats?.documents.filter(doc =>
        doc.document_title.toLowerCase().includes(searchFilter.toLowerCase())
    ) || [];

    if (loading) {
        return (
            <div className="admin-container">
                <div className="admin-loading">
                    <Spinner size="large" />
                    <Text>Loading document statistics...</Text>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="admin-container">
                <MessageBar intent="error">
                    <Text>{error}</Text>
                    <Button onClick={fetchStats}>Retry</Button>
                </MessageBar>
            </div>
        );
    }

    return (
        <div className="admin-container">
            <div className="admin-header">
                <Text as="h1" size={600} weight="semibold">Document Administration</Text>
                <Button onClick={fetchStats} disabled={loading}>
                    Refresh
                </Button>
            </div>

            {/* Summary Cards */}
            <div className="admin-summary">
                <Card className="summary-card">
                    <CardHeader>
                        <Text weight="semibold">Total Documents</Text>
                    </CardHeader>
                    <CardPreview>
                        <div className="summary-value">
                            <DocumentRegular className="summary-icon" />
                            <div className="summary-text">
                                <Text size={800} weight="bold">{stats?.total_documents || 0}</Text>
                                <Text size={200}>Documents</Text>
                            </div>
                        </div>
                    </CardPreview>
                </Card>

                <Card className="summary-card">
                    <CardHeader>
                        <Text weight="semibold">Total Chunks</Text>
                    </CardHeader>
                    <CardPreview>
                        <div className="summary-value">
                            <div className="summary-text">
                                <Text size={800} weight="bold">{stats?.total_chunks || 0}</Text>
                                <Text size={200}>Chunks</Text>
                            </div>
                        </div>
                    </CardPreview>
                </Card>
            </div>

            {/* Search Filter */}
            <div className="admin-filter">
                <Field label="Filter documents">
                    <Input
                        placeholder="Search by document title..."
                        value={searchFilter}
                        onChange={(_, data) => setSearchFilter(data.value)}
                    />
                </Field>
            </div>

            {/* Documents Table */}
            <div className="admin-table-container">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHeaderCell>Document Title</TableHeaderCell>
                            <TableHeaderCell>Type</TableHeaderCell>
                            <TableHeaderCell>Text Chunks</TableHeaderCell>
                            <TableHeaderCell>Image Chunks</TableHeaderCell>
                            <TableHeaderCell>Total Chunks</TableHeaderCell>
                            <TableHeaderCell>Published Date</TableHeaderCell>
                            <TableHeaderCell>Actions</TableHeaderCell>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {filteredDocuments.map((doc, index) => (
                            <React.Fragment key={index}>
                                <TableRow>
                                    <TableCell>
                                        <Button 
                                            appearance="subtle" 
                                            onClick={() => handleDocumentClick(doc.document_title)}
                                            style={{ padding: 0, minWidth: 'auto' }}
                                        >
                                            <Text weight="semibold" style={{ color: 'var(--colorBrandForeground1)', cursor: 'pointer' }}>
                                                {doc.document_title}
                                            </Text>
                                        </Button>
                                    </TableCell>
                                    <TableCell>
                                        <Badge appearance="filled">
                                            {doc.document_type}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        <div className="chunk-count">
                                            <DocumentRegular />
                                            <CounterBadge count={doc.text_chunks} appearance="filled" />
                                        </div>
                                    </TableCell>
                                    <TableCell>
                                        <div className="chunk-count">
                                            <ImageRegular />
                                            <CounterBadge count={doc.image_chunks} appearance="filled" />
                                        </div>
                                    </TableCell>
                                    <TableCell>
                                        <CounterBadge count={doc.total_chunks} appearance="filled" color="important" />
                                    </TableCell>
                                    <TableCell>
                                        <Text size={200}>
                                            {doc.published_date ? new Date(doc.published_date).toLocaleDateString() : 'N/A'}
                                        </Text>
                                    </TableCell>
                                    <TableCell>
                                        <Button
                                            appearance="subtle"
                                            icon={<DeleteRegular />}
                                            onClick={() => handleDeleteDocument(doc.document_title)}
                                            title="Delete entire document"
                                        >
                                            Delete Document
                                        </Button>
                                    </TableCell>
                                </TableRow>
                                
                                {/* Document Chunks Details */}
                                {selectedDocument === doc.document_title && (
                                    <TableRow>
                                        <TableCell colSpan={7}>
                                            <div className="document-chunks-container">
                                                {chunksLoading ? (
                                                    <div className="chunks-loading">
                                                        <Spinner size="small" />
                                                        <Text>Loading chunks...</Text>
                                                    </div>
                                                ) : (
                                                    <div className="document-chunks">
                                                        <Text weight="semibold" size={400} style={{ marginBottom: '12px' }}>
                                                            Document Chunks ({Array.isArray(documentChunks) ? documentChunks.length : 0})
                                                        </Text>
                                                        <div className="chunks-grid">
                                                            {Array.isArray(documentChunks) && documentChunks.map((chunk, chunkIndex) => (
                                                                <Card key={chunkIndex} className="chunk-card">
                                                                    <CardHeader>
                                                                        <div className="chunk-header">
                                                                            <Text weight="semibold" size={300}>
                                                                                {chunk.text_document_id ? 'Text Chunk' : 'Image Chunk'}
                                                                            </Text>
                                                                            <Badge appearance="outline" size="small">
                                                                                ID: {chunk.content_id}
                                                                            </Badge>
                                                                        </div>
                                                                    </CardHeader>
                                                                    <CardPreview>
                                                                        <div className="chunk-content">
                                                                            {/* Content Preview */}
                                                                            {chunk.content_text && (
                                                                                <div className="chunk-content-preview">
                                                                                    <Text size={200} weight="semibold" style={{ marginBottom: '4px' }}>
                                                                                        Content Preview:
                                                                                    </Text>
                                                                                    <Text size={200} className="chunk-text">
                                                                                        {chunk.content_text.length > 150 
                                                                                            ? `${chunk.content_text.substring(0, 150)}...` 
                                                                                            : chunk.content_text
                                                                                        }
                                                                                    </Text>
                                                                                </div>
                                                                            )}
                                                                            
                                                                            {chunk.content_path && (
                                                                                <div className="chunk-content-preview">
                                                                                    <Text size={200} weight="semibold">
                                                                                        Image Path:
                                                                                    </Text>
                                                                                    <Text size={200} style={{ fontStyle: 'italic' }}>
                                                                                        {chunk.content_path}
                                                                                    </Text>
                                                                                </div>
                                                                            )}

                                                                            {/* Metadata Table */}
                                                                            <table className="chunk-metadata-table">
                                                                                <thead>
                                                                                    <tr>
                                                                                        <th>Property</th>
                                                                                        <th>Value</th>
                                                                                    </tr>
                                                                                </thead>
                                                                                <tbody>
                                                                                    <tr>
                                                                                        <td>Content ID</td>
                                                                                        <td>{chunk.content_id || 'N/A'}</td>
                                                                                    </tr>
                                                                                    <tr>
                                                                                        <td>Document Type</td>
                                                                                        <td>{chunk.document_type || 'N/A'}</td>
                                                                                    </tr>
                                                                                    <tr>
                                                                                        <td>Text Document ID</td>
                                                                                        <td>{chunk.text_document_id || 'N/A'}</td>
                                                                                    </tr>
                                                                                    <tr>
                                                                                        <td>Image Document ID</td>
                                                                                        <td>{chunk.image_document_id || 'N/A'}</td>
                                                                                    </tr>
                                                                                    <tr>
                                                                                        <td>Published Date</td>
                                                                                        <td>
                                                                                            {chunk.published_date 
                                                                                                ? new Date(chunk.published_date).toLocaleDateString() 
                                                                                                : 'N/A'
                                                                                            }
                                                                                        </td>
                                                                                    </tr>
                                                                                    <tr>
                                                                                        <td>Page Number</td>
                                                                                        <td>
                                                                                            {chunk.locationMetadata?.pageNumber || 'N/A'}
                                                                                        </td>
                                                                                    </tr>
                                                                                    {chunk.locationMetadata && Object.keys(chunk.locationMetadata).length > 1 && (
                                                                                        <tr>
                                                                                            <td>Location Metadata</td>
                                                                                            <td>
                                                                                                <pre style={{ fontSize: '10px', margin: 0, whiteSpace: 'pre-wrap' }}>
                                                                                                    {JSON.stringify(chunk.locationMetadata, null, 2)}
                                                                                                </pre>
                                                                                            </td>
                                                                                        </tr>
                                                                                    )}
                                                                                </tbody>
                                                                            </table>
                                                                        </div>
                                                                    </CardPreview>
                                                                </Card>
                                                            ))}
                                                            {(!Array.isArray(documentChunks) || documentChunks.length === 0) && (
                                                                <div style={{ padding: '20px', textAlign: 'center' }}>
                                                                    <Text>No chunks found for this document.</Text>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                )}
                            </React.Fragment>
                        ))}
                    </TableBody>
                </Table>

                {filteredDocuments.length === 0 && (
                    <div className="no-documents">
                        <Text>No documents found matching your search criteria.</Text>
                    </div>
                )}
            </div>

            {/* Delete Confirmation Dialog */}
            <Dialog open={deleteConfirmOpen} onOpenChange={(_, data) => setDeleteConfirmOpen(data.open)}>
                <DialogSurface>
                    <DialogTitle>Confirm Deletion</DialogTitle>
                    <DialogContent>
                        <DialogBody>
                            <div className="delete-warning">
                                <AlertRegular className="warning-icon" />
                                <div>
                                    <Text weight="semibold">
                                        Are you sure you want to delete {deleteTarget?.type === 'document' ? 'the entire document' : 'this chunk'}?
                                    </Text>
                                    <Text>
                                        {deleteTarget?.type === 'document' 
                                            ? `This will permanently delete all chunks for "${deleteTarget.title}".`
                                            : `This will permanently delete the selected chunk from "${deleteTarget?.title}".`
                                        }
                                    </Text>
                                    <Text weight="semibold" style={{ color: 'red' }}>
                                        This action cannot be undone.
                                    </Text>
                                </div>
                            </div>
                        </DialogBody>
                        <DialogActions>
                            <Button 
                                appearance="secondary" 
                                onClick={() => setDeleteConfirmOpen(false)}
                                disabled={deleteLoading}
                            >
                                Cancel
                            </Button>
                            <Button 
                                appearance="primary" 
                                onClick={confirmDelete}
                                disabled={deleteLoading}
                                icon={deleteLoading ? <Spinner size="tiny" /> : <DeleteRegular />}
                            >
                                {deleteLoading ? 'Deleting...' : 'Delete'}
                            </Button>
                        </DialogActions>
                    </DialogContent>
                </DialogSurface>
            </Dialog>
        </div>
    );
};

export default Admin;
