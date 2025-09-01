import React from "react";

import { Caption1Strong, InteractionTag, InteractionTagPrimary } from "@fluentui/react-components";
import { ImageCopy24Filled, Text12Filled, ImageMultiple20Filled } from "@fluentui/react-icons";

import { Citation } from "../../../api/models";
import CitationViewer from "../CitationViewer/CitationViewer";
import "./Citations.css";

interface CitationsProps {
    highlightedCitation?: string;
    imageCitations: Citation[];
    textCitations: Citation[];
}

const Citations: React.FC<CitationsProps> = ({ imageCitations, textCitations, highlightedCitation }) => {
    const [citationsView, setCitationsView] = React.useState(false);
    const [selectedCitation, setSelectedCitation] = React.useState<Citation>();

    const truncateText = (maxLength: number, text?: string) => {
        if (!text) return "";
        if (text.length <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength) + "...";
    };

    return (
        <>
            <div>
                {!!(textCitations.length || imageCitations.length) && (
                    <>
                        <Caption1Strong className="citations-title" block>
                            Citations
                        </Caption1Strong>
                        <div className="citations">
                            {!!textCitations.length &&
                                textCitations.map((citation, index) => (
                                    <InteractionTag
                                        className="citation-interaction"
                                        key={index}
                                        appearance={highlightedCitation === `${citation.content_id}` ? "brand" : "filled"}
                                    >
                                        <InteractionTagPrimary
                                            secondaryText={`Page ${citation.locationMetadata?.pageNumber || 1}${citation.show_image ? " • Contains Figure" : ""}`}
                                            onClick={() => {
                                                setCitationsView(true);
                                                setSelectedCitation(citation);
                                            }}
                                            icon={citation.show_image ? <ImageMultiple20Filled /> : <Text12Filled />}
                                        >
                                            {truncateText(40, citation.text || citation.title)}
                                        </InteractionTagPrimary>
                                    </InteractionTag>
                                ))}
                            {!!imageCitations.length &&
                                imageCitations.map((citation, index) => (
                                    <InteractionTag
                                        key={index}
                                        className="citation-interaction"
                                        appearance={highlightedCitation === `${citation.content_id}` ? "brand" : "filled"}
                                    >
                                        <InteractionTagPrimary
                                            secondaryText={citation.is_image ? `Image - Page ${citation.locationMetadata?.pageNumber || 1}` : `Page ${citation.locationMetadata?.pageNumber || 1}`}
                                            onClick={() => {
                                                setCitationsView(true);
                                                setSelectedCitation(citation);
                                            }}
                                            icon={<ImageCopy24Filled className="citation-image-icon" />}
                                        >
                                            {truncateText(40, citation.title)}
                                        </InteractionTagPrimary>
                                    </InteractionTag>
                                ))}
                        </div>
                    </>
                )}
            </div>
            {selectedCitation && <CitationViewer show={citationsView} toggle={() => setCitationsView(false)} citation={selectedCitation} onClose={() => setCitationsView(false)} />}
        </>
    );
};

export default Citations;
