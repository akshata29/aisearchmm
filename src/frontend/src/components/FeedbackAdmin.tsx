import React, { useState, useEffect } from 'react';
import { 
    Card, 
    Title2, 
    Title3,
    Body1, 
    MessageBar, 
    Spinner, 
    Button, 
    Textarea,
    Switch,
    Label,
    Dialog,
    DialogSurface,
    DialogTitle,
    DialogContent,
    DialogBody,
    DialogActions,
    Text
} from '@fluentui/react-components';
import { 
    ArrowClockwise24Regular, 
    Edit24Regular, 
    Save24Regular, 
    Dismiss24Regular
} from '@fluentui/react-icons';
import { 
    getFeedbackList, 
    getFeedbackDetail, 
    updateFeedback 
} from '../api/enhanced-api';
import type { 
    FeedbackEntry, 
    Citation, 
    FeedbackProcessingStep 
} from '../api/models';
import './FeedbackAdmin.css';

interface EditForm {
    response_text: string;
    admin_notes: string;
    is_reviewed: boolean;
}

const FeedbackAdmin: React.FC = () => {
    const [feedbackList, setFeedbackList] = useState<FeedbackEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editForm, setEditForm] = useState<EditForm | null>(null);
    const [saving, setSaving] = useState(false);
    const [citationsLoaded, setCitationsLoaded] = useState<Set<string>>(new Set());

    
    // Modal states
    const [showCitationsModal, setShowCitationsModal] = useState(false);
    const [showStepsModal, setShowStepsModal] = useState(false);
    const [detailedFeedback, setDetailedFeedback] = useState<FeedbackEntry | null>(null);
    const [loadingDetails, setLoadingDetails] = useState(false);

    const loadFeedbackList = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await getFeedbackList();
            if (response.status === 'success' && response.data) {
                setFeedbackList(response.data.feedback_items);
            } else {
                setError('Failed to load feedback');
            }
        } catch (err) {
            setError('Error loading feedback list');
            console.error('Error loading feedback:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadFeedbackList();
    }, []);

    const getFeedbackIcon = (type: string) => {
        return type === 'thumbs_up' ? '👍' : '👎';
    };

    const formatDate = (timestamp: string) => {
        return new Date(timestamp).toLocaleDateString('en-US', {
            month: 'short',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    // Citation enhancement functions
    const createCitationMapping = (feedback: FeedbackEntry): Map<string, string> => {
        const citationMap = new Map<string, string>();
        
        // Add text citations - map content_id to title
        feedback.text_citations?.forEach(citation => {
            if (citation.content_id) {
                const displayName = citation.title || 'Unnamed Document';
                citationMap.set(citation.content_id, displayName);
            }
        });
        
        // Add image citations - map content_id to title
        feedback.image_citations?.forEach(citation => {
            if (citation.content_id) {
                const displayName = citation.title || 'Unnamed Image';
                citationMap.set(citation.content_id, displayName);
            }
        });
        
        return citationMap;
    };

    const replaceCitationsInText = (text: string, citationMap: Map<string, string>): JSX.Element => {
        // GUID pattern: 8 chars - 4 chars - 4 chars - 4 chars - 12 chars
        const guidPattern = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
        
        const matches = text.match(guidPattern) || [];
        const parts = text.split(guidPattern);
        const result: (string | JSX.Element)[] = [];
        
        parts.forEach((part, index) => {
            result.push(part);
            if (index < matches.length) {
                const guid = matches[index];
                if (guid) {
                    const citationName = citationMap.get(guid);
                    if (citationName) {
                        result.push(
                            <span 
                                key={`citation-${guid}-${index}`}
                                className="feedback-citation-reference"
                                title={`Citation: ${citationName}`}
                            >
                                [{citationName}]
                            </span>
                        );
                    } else {
                        result.push(guid); // fallback to original GUID if not found
                    }
                }
            }
        });
        
        return <>{result}</>;
    };

    const handleEdit = async (feedback: FeedbackEntry) => {
        if (feedback.is_reviewed) return;
        
        setEditingId(feedback.feedback_id);
        setEditForm({
            response_text: feedback.response_text,
            admin_notes: feedback.admin_notes || '',
            is_reviewed: feedback.is_reviewed
        });

        // Load detailed feedback with citations for proper citation mapping
        try {
            const response = await getFeedbackDetail(feedback.feedback_id);
            
            if (response.status === 'success' && response.data) {
                // Update the feedback in the list with detailed citation data
                setFeedbackList(prev => prev.map(item => 
                    item.feedback_id === feedback.feedback_id 
                        ? { ...item, ...response.data }
                        : item
                ));
                
                // Mark citations as loaded for this feedback
                setCitationsLoaded(prev => new Set(prev).add(feedback.feedback_id));
            }
        } catch (err) {
            console.error('Error loading detailed feedback for edit:', err);
        }
    };

    const handleCancelEdit = () => {
        setEditingId(null);
        setEditForm(null);
    };

    const handleSave = async (feedbackId: string) => {
        if (!editForm) return;
        
        setSaving(true);
        try {
            const response = await updateFeedback(feedbackId, editForm);
            if (response.status === 'success') {
                await loadFeedbackList();
                setEditingId(null);
                setEditForm(null);
            } else {
                setError('Failed to save changes');
            }
        } catch (err) {
            setError('Error saving feedback');
            console.error('Error saving feedback:', err);
        } finally {
            setSaving(false);
        }
    };

    const handleViewCitations = async (feedbackId: string) => {
        setLoadingDetails(true);
        setShowCitationsModal(true);
        try {
            const response = await getFeedbackDetail(feedbackId);
            if (response.status === 'success' && response.data) {
                setDetailedFeedback(response.data);
            }
        } catch (err) {
            console.error('Error loading feedback details:', err);
        } finally {
            setLoadingDetails(false);
        }
    };

    const handleViewProcessingSteps = async (feedbackId: string) => {
        setLoadingDetails(true);
        setShowStepsModal(true);
        try {
            const response = await getFeedbackDetail(feedbackId);
            if (response.status === 'success' && response.data) {
                setDetailedFeedback(response.data);
            }
        } catch (err) {
            console.error('Error loading feedback details:', err);
        } finally {
            setLoadingDetails(false);
        }
    };

    const renderCitation = (citation: Citation, index: number) => (
        <div key={index} className="feedback-citation-item">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <Text style={{ fontWeight: '600', fontSize: '14px' }}>
                    {citation.title || 'Untitled'}
                </Text>
                {citation.is_image && (
                    <span style={{ 
                        backgroundColor: 'var(--colorCompoundBrandBackground1)', 
                        color: 'var(--colorCompoundBrandForeground1)', 
                        padding: '2px 8px', 
                        borderRadius: '12px', 
                        fontSize: '12px',
                        fontWeight: '500'
                    }}>
                        Image
                    </span>
                )}
            </div>
            {citation.text && (
                <Text className="feedback-citation-text">
                    {citation.text}
                </Text>
            )}
            {citation.locationMetadata?.pageNumber !== undefined && (
                <Text className="feedback-citation-page">
                    Page {citation.locationMetadata.pageNumber}
                </Text>
            )}
        </div>
    );

    const renderProcessingStep = (step: FeedbackProcessingStep, index: number) => (
        <div key={index} className="feedback-step-item">
            <div className="feedback-step-header">
                <span className="feedback-step-number">Step {index + 1}</span>
                <Text className="feedback-step-title">
                    {step.title}
                </Text>
            </div>
            {step.description && (
                <Text className="feedback-step-description">
                    {step.description}
                </Text>
            )}
            <div className="feedback-step-duration">
                Duration: {step.duration_ms}ms | Status: {step.status}
            </div>
        </div>
    );

    if (loading) {
        return (
            <div className="feedback-loading">
                <Spinner size="large" />
            </div>
        );
    }

    return (
        <div className="feedback-admin-container">
            <div className="feedback-admin-header">
                <Title2 className="feedback-admin-title">Feedback Management</Title2>
                <Button 
                    icon={<ArrowClockwise24Regular />}
                    onClick={loadFeedbackList}
                    disabled={loading}
                >
                    Refresh
                </Button>
            </div>

            {error && (
                <MessageBar intent="error" className="feedback-admin-error">
                    <Body1>{error}</Body1>
                </MessageBar>
            )}

            <Body1 className="feedback-admin-total">
                Total feedback entries: {feedbackList.length}
            </Body1>

            <div className="feedback-admin-grid">
                {feedbackList.map((feedback) => (
                    <Card key={feedback.feedback_id} className="feedback-card">
                        {editingId === feedback.feedback_id ? (
                            // Edit Mode - Professional modern layout
                            <div className="feedback-edit-container">
                                {/* Professional Header with gradient */}
                                <div className="feedback-edit-header">
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                                        <div style={{ fontSize: '28px' }}>
                                            {getFeedbackIcon(feedback.feedback_type)}
                                        </div>
                                        <div style={{ flex: 1 }}>
                                            <Title2 style={{ margin: 0, color: 'white', fontWeight: '600' }}>
                                                {feedback.is_reviewed ? '👀 Reviewing Entry' : '✏️ Editing Feedback'}
                                            </Title2>
                                            <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: '14px' }}>
                                                ID: {feedback.feedback_id} • Session: {feedback.session_id}
                                            </span>
                                        </div>
                                        {feedback.is_reviewed && (
                                            <div className="feedback-reviewed-badge">
                                                ✓ REVIEWED
                                            </div>
                                        )}
                                    </div>
                                </div>
                                
                                {/* Content with better spacing and organization */}
                                <div className="feedback-edit-content">
                                    <div className="feedback-edit-grid">
                                        {/* Left Column - Main Content */}
                                        <div className="feedback-edit-left">
                                            {/* Question Section */}
                                            <div className="feedback-section feedback-section-question">
                                                <Label className="feedback-section-label">
                                                    📝 Question
                                                </Label>
                                                <div className="feedback-question-display">
                                                    <Body1 className="feedback-question-text">
                                                        {feedback.question}
                                                    </Body1>
                                                </div>
                                            </div>

                                            {/* Response Section */}
                                            <div className="feedback-section feedback-section-response">
                                                <Label className="feedback-section-label">
                                                    💬 Response
                                                </Label>
                                                {/* Enhanced Response Display */}
                                                <div className="feedback-enhanced-response">
                                                    {citationsLoaded.has(feedback.feedback_id) && (feedback.text_citations || feedback.image_citations) ? (
                                                        <div 
                                                            className="feedback-enhanced-response-content"
                                                            style={{
                                                                border: '1px solid var(--colorNeutralStroke2)',
                                                                borderRadius: '8px',
                                                                padding: '12px',
                                                                minHeight: '300px',
                                                                backgroundColor: feedback.is_reviewed ? 'var(--colorNeutralBackground2)' : 'var(--colorNeutralBackground1)',
                                                                fontSize: '14px',
                                                                lineHeight: '1.6',
                                                                fontFamily: 'var(--fontFamilyBase)',
                                                                whiteSpace: 'pre-wrap',
                                                                overflow: 'auto',
                                                                cursor: feedback.is_reviewed ? 'default' : 'text'
                                                            }}
                                                            contentEditable={!feedback.is_reviewed}
                                                            suppressContentEditableWarning={true}
                                                            onInput={(e) => {
                                                                if (!feedback.is_reviewed) {
                                                                    const text = e.currentTarget.textContent || '';
                                                                    setEditForm(prev => prev ? {...prev, response_text: text} : null);
                                                                }
                                                            }}
                                                            onBlur={(e) => {
                                                                if (!feedback.is_reviewed) {
                                                                    const text = e.currentTarget.textContent || '';
                                                                    setEditForm(prev => prev ? {...prev, response_text: text} : null);
                                                                }
                                                            }}
                                                        >
                                                            {replaceCitationsInText(editForm?.response_text || feedback.response_text || '', createCitationMapping(feedback))}
                                                        </div>
                                                    ) : (
                                                        <Textarea
                                                            value={editForm?.response_text || feedback.response_text || ''}
                                                            onChange={(_, data) => setEditForm(prev => prev ? {...prev, response_text: data.value} : null)}
                                                            rows={15}
                                                            disabled={feedback.is_reviewed}
                                                            className="feedback-textarea"
                                                            placeholder="Enter response text... (Loading citation data)"
                                                            style={{ minHeight: '300px' }}
                                                        />
                                                    )}
                                                </div>
                                            </div>

                                            {/* Admin Notes Section - Right After Response */}
                                            <div className="feedback-section feedback-section-notes">
                                                <Label className="feedback-section-label">
                                                    📋 Admin Notes
                                                </Label>
                                                <Textarea
                                                    value={editForm?.admin_notes || ''}
                                                    onChange={(_, data) => setEditForm(prev => prev ? {...prev, admin_notes: data.value} : null)}
                                                    rows={2}
                                                    disabled={feedback.is_reviewed}
                                                    className="feedback-textarea"
                                                    placeholder="Add internal admin notes..."
                                                    style={{ minHeight: '60px' }}
                                                />
                                            </div>

                                        </div>

                                        {/* Right Column - Sidebar */}
                                        <div className="feedback-edit-right">
                                            {/* Stats Cards */}
                                            <div className="feedback-section feedback-section-stats">
                                                <Title3 style={{ 
                                                    margin: '0 0 16px 0', 
                                                    fontSize: '18px'
                                                }} className="feedback-section-label">
                                                    📊 Content Overview
                                                </Title3>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                                    <Button
                                                        appearance="subtle"
                                                        onClick={() => handleViewCitations(feedback.feedback_id)}
                                                        className="feedback-stat-button feedback-citations-button"
                                                    >
                                                        <div className="feedback-stat-text">
                                                            <div className="feedback-stat-label">
                                                                📚 Text Citations
                                                            </div>
                                                            <div className="feedback-stat-count">
                                                                {feedback.text_citations_count}
                                                            </div>
                                                        </div>
                                                    </Button>
                                                    
                                                    <Button
                                                        appearance="subtle"
                                                        onClick={() => handleViewCitations(feedback.feedback_id)}
                                                        className="feedback-stat-button feedback-images-button"
                                                    >
                                                        <div className="feedback-stat-text">
                                                            <div className="feedback-stat-label">
                                                                🖼️ Image Citations
                                                            </div>
                                                            <div className="feedback-stat-count">
                                                                {feedback.image_citations_count}
                                                            </div>
                                                        </div>
                                                    </Button>
                                                    
                                                    <Button
                                                        appearance="subtle"
                                                        onClick={() => handleViewProcessingSteps(feedback.feedback_id)}
                                                        className="feedback-stat-button feedback-steps-button"
                                                    >
                                                        <div className="feedback-stat-text">
                                                            <div className="feedback-stat-label">
                                                                ⚙️ Processing Steps
                                                            </div>
                                                            <div className="feedback-stat-count">
                                                                {feedback.processing_steps?.length || 0}
                                                            </div>
                                                        </div>
                                                    </Button>
                                                </div>
                                            </div>

                                            {/* Metadata */}
                                            <div className="feedback-section feedback-section-metadata">
                                                <Title3 className="feedback-section-label" style={{ 
                                                    margin: '0 0 16px 0', 
                                                    fontSize: '18px'
                                                }}>
                                                    🕒 Metadata
                                                </Title3>
                                                <div className="feedback-metadata-text">
                                                    <div style={{ marginBottom: '8px' }}>
                                                        <strong>Created:</strong> {new Date(feedback.timestamp).toLocaleString()}
                                                    </div>
                                                    <div style={{ marginBottom: '8px' }}>
                                                        <strong>Modified:</strong> {feedback.last_modified 
                                                            ? new Date(feedback.last_modified).toLocaleString() 
                                                            : 'Never'
                                                        }
                                                    </div>
                                                    {feedback.modified_by && (
                                                        <div>
                                                            <strong>By:</strong> {feedback.modified_by}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Review Status */}
                                            <div style={{
                                                background: feedback.is_reviewed 
                                                    ? 'linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%)'
                                                    : 'linear-gradient(135deg, #fee2e2 0%, #fecaca 100%)',
                                                borderRadius: '12px',
                                                padding: '24px',
                                                border: `1px solid ${feedback.is_reviewed ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`
                                            }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                                                    <div style={{ fontSize: '20px' }}>
                                                        {feedback.is_reviewed ? '✅' : '⏳'}
                                                    </div>
                                                    <Title3 style={{ 
                                                        margin: 0, 
                                                        color: feedback.is_reviewed ? '#065f46' : '#991b1b',
                                                        fontSize: '18px'
                                                    }}>
                                                        Review Status
                                                    </Title3>
                                                </div>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                                    <Switch
                                                        checked={editForm?.is_reviewed || false}
                                                        onChange={(_, data) => setEditForm(prev => prev ? {...prev, is_reviewed: data.checked} : null)}
                                                        disabled={feedback.is_reviewed}
                                                    />
                                                    <Label style={{ 
                                                        fontWeight: '600',
                                                        color: feedback.is_reviewed ? '#065f46' : '#991b1b'
                                                    }}>
                                                        {editForm?.is_reviewed ? 'Reviewed' : 'Mark as reviewed'}
                                                    </Label>
                                                </div>
                                            </div>

                                            {/* Action Buttons */}
                                            <div style={{
                                                background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
                                                borderRadius: '12px',
                                                padding: '24px',
                                                border: '1px solid rgba(148, 163, 184, 0.2)',
                                                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                                            }}>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                                    <Button 
                                                        appearance="secondary" 
                                                        icon={<Dismiss24Regular />}
                                                        onClick={handleCancelEdit}
                                                        disabled={saving}
                                                        style={{
                                                            height: '48px',
                                                            fontSize: '16px',
                                                            borderRadius: '8px'
                                                        }}
                                                    >
                                                        Cancel Changes
                                                    </Button>
                                                    <Button 
                                                        appearance="primary" 
                                                        icon={<Save24Regular />}
                                                        onClick={() => handleSave(feedback.feedback_id)}
                                                        disabled={saving || feedback.is_reviewed}
                                                        style={{
                                                            height: '48px',
                                                            fontSize: '16px',
                                                            fontWeight: '600',
                                                            borderRadius: '8px'
                                                        }}
                                                    >
                                                        {saving ? '💾 Saving...' : feedback.is_reviewed ? '🔒 Read Only' : '💾 Save Changes'}
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>


                                </div>
                            </div>
                        ) : (
                            // View Mode - Clean card layout  
                            <div>
                                {/* Header Section with gradient background */}
                                <div className={`feedback-view-header ${
                                    feedback.feedback_type === 'thumbs_up' 
                                        ? 'feedback-view-header-positive' 
                                        : 'feedback-view-header-negative'
                                }`}>
                                    <div className="feedback-view-content">
                                        <div className="feedback-icon">
                                            {getFeedbackIcon(feedback.feedback_type)}
                                        </div>
                                        <div className="feedback-view-info">
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '8px' }}>
                                                <Title2 className="feedback-view-title">
                                                    {feedback.feedback_type === 'thumbs_up' ? 'Positive Feedback' : 'Negative Feedback'}
                                                </Title2>
                                                {feedback.is_reviewed && (
                                                    <div className="feedback-reviewed-badge">
                                                        ✓ REVIEWED
                                                    </div>
                                                )}
                                            </div>
                                            <div className="feedback-view-meta">
                                                <span>📅 {formatDate(feedback.timestamp)}</span>
                                                <span>🔗 Session: {feedback.session_id.substring(0, 12)}...</span>
                                                <span>📊 ID: {feedback.feedback_id.substring(0, 8)}...</span>
                                            </div>
                                        </div>
                                    </div>
                                    <Button 
                                        appearance="subtle" 
                                        icon={<Edit24Regular />}
                                        onClick={() => handleEdit(feedback)}
                                        disabled={feedback.is_reviewed}
                                        className="feedback-view-edit-button"
                                    >
                                        {feedback.is_reviewed ? 'View Details' : 'Edit Entry'}
                                    </Button>
                                </div>

                                {/* Content Section */}
                                <div style={{ padding: '24px' }}>
                                    {/* Question */}
                                    <div style={{ marginBottom: '20px' }}>
                                        <Label className="feedback-view-section-label">
                                            Question
                                        </Label>
                                        <div className="feedback-view-question-content">
                                            <Body1 className="feedback-view-question-text">
                                                {feedback.question}
                                            </Body1>
                                        </div>
                                    </div>

                                    {/* Response */}
                                    <div style={{ marginBottom: '20px' }}>
                                        <Label className="feedback-view-section-label">
                                            Response
                                        </Label>
                                        <div className="feedback-view-response-content">
                                            <Body1 className="feedback-view-response-text">
                                                {/* Only replace citations if we have citation data, otherwise show raw text */}
                                                {feedback.text_citations || feedback.image_citations 
                                                    ? replaceCitationsInText(feedback.response_text, createCitationMapping(feedback))
                                                    : feedback.response_text
                                                }
                                            </Body1>
                                        </div>
                                    </div>

                                    {feedback.admin_notes && (
                                        <div style={{ marginBottom: '20px' }}>
                                            <Label className="feedback-view-section-label">
                                                Admin Notes
                                            </Label>
                                            <div className="feedback-view-notes-content">
                                                <Body1 className="feedback-view-notes-text">
                                                    {feedback.admin_notes}
                                                </Body1>
                                            </div>
                                        </div>
                                    )}

                                    {/* Actions Row */}
                                    <div className="feedback-view-actions-row">
                                        <Button
                                            appearance="subtle"
                                            onClick={() => handleViewCitations(feedback.feedback_id)}
                                            className="feedback-view-action-button feedback-view-citations-button"
                                            disabled={feedback.text_citations_count === 0 && feedback.image_citations_count === 0}
                                            style={{
                                                opacity: feedback.text_citations_count + feedback.image_citations_count > 0 ? 1 : 0.6
                                            }}
                                        >
                                            <div className="feedback-view-action-content">
                                                <div className="feedback-view-action-header">
                                                    📚 Citations
                                                    <div className="feedback-view-action-badge feedback-citations-badge">
                                                        {feedback.text_citations_count + feedback.image_citations_count}
                                                    </div>
                                                </div>
                                            </div>
                                        </Button>

                                        <Button
                                            appearance="subtle"
                                            onClick={() => handleViewProcessingSteps(feedback.feedback_id)}
                                            className="feedback-view-action-button feedback-view-steps-button"
                                            disabled={(feedback.processing_steps?.length || 0) === 0}
                                            style={{
                                                opacity: (feedback.processing_steps?.length || 0) > 0 ? 1 : 0.6
                                            }}
                                        >
                                            <div className="feedback-view-action-content">
                                                <div className="feedback-view-action-header">
                                                    ⚙️ Processing Steps
                                                    <div className="feedback-view-action-badge feedback-steps-badge">
                                                        {feedback.processing_steps?.length || 0}
                                                    </div>
                                                </div>
                                            </div>
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        )}
                    </Card>
                ))}
            </div>

            {feedbackList.length === 0 && !loading && (
                <div style={{ 
                    textAlign: 'center', 
                    padding: '60px 20px',
                    backgroundColor: '#f8fafc',
                    borderRadius: '12px',
                    border: '2px dashed #cbd5e1'
                }}>
                    <div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.6 }}>📝</div>
                    <Title2 style={{ margin: '0 0 8px 0', color: '#64748b' }}>No feedback entries found</Title2>
                    <Body1 style={{ color: '#94a3b8' }}>Feedback entries will appear here when users submit feedback.</Body1>
                </div>
            )}

            {/* Citations Modal */}
            <Dialog open={showCitationsModal} onOpenChange={(_, data) => setShowCitationsModal(data.open)}>
                <DialogSurface className="feedback-modal-surface" style={{ maxWidth: '900px', maxHeight: '80vh' }}>
                    <DialogBody>
                        <DialogTitle className="feedback-modal-title">Citations for Feedback Entry</DialogTitle>
                        <DialogContent className="feedback-modal-content">
                            {loadingDetails ? (
                                <div className="feedback-modal-loading">
                                    <Spinner size="medium" />
                                </div>
                            ) : detailedFeedback ? (
                                <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
                                    {detailedFeedback.text_citations && detailedFeedback.text_citations.length > 0 && (
                                        <div style={{ marginBottom: '24px' }}>
                                            <Title3 style={{ marginBottom: '12px', color: '#374151' }}>
                                                Text Citations ({detailedFeedback.text_citations.length})
                                            </Title3>
                                            {detailedFeedback.text_citations.map((citation: Citation, index: number) =>
                                                renderCitation(citation, index)
                                            )}
                                        </div>
                                    )}
                                    
                                    {detailedFeedback.image_citations && detailedFeedback.image_citations.length > 0 && (
                                        <div>
                                            <Title3 style={{ marginBottom: '12px', color: '#374151' }}>
                                                Image Citations ({detailedFeedback.image_citations.length})
                                            </Title3>
                                            {detailedFeedback.image_citations.map((citation: Citation, index: number) =>
                                                renderCitation(citation, index)
                                            )}
                                        </div>
                                    )}

                                    {(!detailedFeedback.text_citations?.length && !detailedFeedback.image_citations?.length) && (
                                        <Body1 style={{ textAlign: 'center', color: '#666', padding: '40px' }}>
                                            No citations found for this feedback entry.
                                        </Body1>
                                    )}
                                </div>
                            ) : (
                                <Body1 style={{ textAlign: 'center', color: '#666' }}>
                                    Failed to load citations.
                                </Body1>
                            )}
                        </DialogContent>
                        <DialogActions>
                            <Button 
                                appearance="secondary" 
                                onClick={() => setShowCitationsModal(false)}
                            >
                                Close
                            </Button>
                        </DialogActions>
                    </DialogBody>
                </DialogSurface>
            </Dialog>

            {/* Processing Steps Modal */}
            <Dialog open={showStepsModal} onOpenChange={(_, data) => setShowStepsModal(data.open)}>
                <DialogSurface className="feedback-modal-surface" style={{ maxWidth: '800px', maxHeight: '80vh' }}>
                    <DialogBody>
                        <DialogTitle className="feedback-modal-title">Processing Steps for Feedback Entry</DialogTitle>
                        <DialogContent className="feedback-modal-content">
                            {loadingDetails ? (
                                <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
                                    <Spinner size="medium" />
                                </div>
                            ) : detailedFeedback?.processing_steps ? (
                                <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
                                    {detailedFeedback.processing_steps.map((step: FeedbackProcessingStep, index: number) => 
                                        renderProcessingStep(step, index)
                                    )}
                                </div>
                            ) : (
                                <Body1 style={{ textAlign: 'center', color: '#666' }}>
                                    No processing steps found for this feedback entry.
                                </Body1>
                            )}
                        </DialogContent>
                        <DialogActions>
                            <Button 
                                appearance="secondary" 
                                onClick={() => setShowStepsModal(false)}
                            >
                                Close
                            </Button>
                        </DialogActions>
                    </DialogBody>
                </DialogSurface>
            </Dialog>
        </div>
    );
};

export default FeedbackAdmin;