import React, { useEffect, useState } from "react";

import { Button, Drawer, DrawerBody, DrawerFooter, DrawerHeader, DrawerHeaderTitle } from "@fluentui/react-components";
import { Dismiss20Regular } from "@fluentui/react-icons";

import { getCitationDocument } from "../../../api/api";
import { Citation } from "../../../api/models";
import "./CitationViewer.css";
import PdfHighlighter from "../../shared/PdfHighlighter/PdfHighlighter";

interface Props {
    show: boolean;
    citation: Citation;
    onClose: () => void;
    toggle: () => void;
}

const CitationViewer: React.FC<Props> = ({ show, toggle, citation }) => {
    const [pdfPath, setPDFPath] = useState<string>("");

    useEffect(() => {
        // Only fetch PDF document if this is not an image citation
        if (!citation.is_image) {
            getCitationDocument(citation.title).then((response: string) => {
                setPDFPath(response);
            });
        }
    }, [citation]);

    return (
        <Drawer size="medium" position="end" separator open={show} onOpenChange={toggle} className="citation-drawer">
            <DrawerHeader>
                <DrawerHeaderTitle action={<Button appearance="subtle" aria-label="Close" icon={<Dismiss20Regular />} onClick={toggle} />}>
                    {citation.is_image ? "Image Citation" : "Citation"}
                </DrawerHeaderTitle>
            </DrawerHeader>

            <DrawerBody>
                <div className="citation-content">
                    {citation.is_image && citation.image_url ? (
                        <div className="image-citation-container">
                            <img 
                                src={citation.image_url} 
                                alt={citation.title || "Citation image"}
                                style={{
                                    maxWidth: "100%",
                                    height: "auto",
                                    borderRadius: "4px",
                                    boxShadow: "0 2px 8px rgba(0,0,0,0.1)"
                                }}
                                onError={(e) => {
                                    console.error("Failed to load image:", citation.image_url);
                                    (e.target as HTMLImageElement).style.display = "none";
                                }}
                            />
                            <div style={{ marginTop: "12px", fontSize: "14px", color: "#666" }}>
                                <strong>Source:</strong> {citation.title}
                            </div>
                            {citation.locationMetadata?.pageNumber && (
                                <div style={{ fontSize: "14px", color: "#666" }}>
                                    <strong>Page:</strong> {citation.locationMetadata.pageNumber}
                                </div>
                            )}
                        </div>
                    ) : citation.is_image ? (
                        <div className="image-citation-fallback">
                            <p style={{ color: "#999", fontStyle: "italic" }}>
                                Image citation: {citation.title}
                            </p>
                            <p style={{ color: "#666", fontSize: "14px" }}>
                                Image preview unavailable
                            </p>
                        </div>
                    ) : (
                        <>
                            {/* Show linked image for text citations that reference figures */}
                            {citation.show_image && citation.image_url && (
                                <div className="linked-image-container" style={{ marginBottom: "16px" }}>
                                    <div style={{ marginBottom: "8px", fontSize: "14px", fontWeight: "600", color: "#333" }}>
                                        Referenced Figure:
                                    </div>
                                    <img 
                                        src={citation.image_url} 
                                        alt={`Figure referenced in ${citation.title}`}
                                        style={{
                                            maxWidth: "100%",
                                            height: "auto",
                                            borderRadius: "4px",
                                            boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
                                            border: "1px solid #e0e0e0"
                                        }}
                                        onError={(e) => {
                                            console.error("Failed to load linked image:", citation.image_url);
                                            (e.target as HTMLImageElement).style.display = "none";
                                        }}
                                    />
                                </div>
                            )}
                            
                            {pdfPath && (
                                <PdfHighlighter
                                    pdfPath={pdfPath}
                                    pageNumber={citation.locationMetadata?.pageNumber || 1}
                                    boundingPolygons={citation.locationMetadata?.boundingPolygons}
                                />
                            )}
                            {citation.text ? <p>{citation.text}</p> : null}
                        </>
                    )}
                </div>
            </DrawerBody>
            <DrawerFooter>
                <Button appearance="primary" onClick={toggle}>
                    Close
                </Button>
            </DrawerFooter>
        </Drawer>
    );
};

export default CitationViewer;
