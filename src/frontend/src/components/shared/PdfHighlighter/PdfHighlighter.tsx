import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { Document, Page } from "react-pdf";
import { pdfjs } from "react-pdf";
import { BoundingPolygon, Coordinates } from "../../../api/models";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

interface PdfHighlighterProps {
    pdfPath: string;
    pageNumber: number;
    boundingPolygons: string;
}

const PdfHighlighter = ({ pdfPath, pageNumber, boundingPolygons }: PdfHighlighterProps) => {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const [pageSize, setPageSize] = useState<{ width: number; height: number } | null>(null);

    // Memoize parsed bounding polygons and filter for more precise highlighting
    const parsedPolygons = useMemo(() => {
        try {
            const polygons = JSON.parse(boundingPolygons) as BoundingPolygon[];
            
            // Filter out polygons that are too large (likely covering entire page/sections)
            const filteredPolygons = polygons.filter(polygon => {
                if (polygon.length < 3) return false; // Invalid polygon
                
                // Calculate bounding box area
                const xs = polygon.map(coord => coord.x);
                const ys = polygon.map(coord => coord.y);
                const width = Math.max(...xs) - Math.min(...xs);
                const height = Math.max(...ys) - Math.min(...ys);
                const area = width * height;
                
                // Filter out polygons that are too large (likely covering most of the page)
                // These thresholds may need adjustment based on your document format
                return area < 0.4; // Less than 40% of page area (adjust as needed)
            });
            
            // If we filtered out too many, take the smallest ones
            if (filteredPolygons.length === 0 && polygons.length > 0) {
                // Sort by area and take the smallest polygons
                const polygonsWithArea = polygons.map(polygon => {
                    const xs = polygon.map(coord => coord.x);
                    const ys = polygon.map(coord => coord.y);
                    const width = Math.max(...xs) - Math.min(...xs);
                    const height = Math.max(...ys) - Math.min(...ys);
                    const area = width * height;
                    return { polygon, area };
                }).sort((a, b) => a.area - b.area);
                
                // Take the 3 smallest polygons
                return polygonsWithArea.slice(0, 3).map(item => item.polygon);
            }
            
            return filteredPolygons.slice(0, 5); // Limit to 5 polygons max
        } catch (error) {
            console.error("Failed to parse boundingPolygons:", error);
            return [];
        }
    }, [boundingPolygons]);

    const onPageLoadSuccess = ({ width, height }: { width: number; height: number }) => {
        setPageSize({ width, height });
    };

    const drawOverlay = useCallback(
        (coords: Coordinates[], index: number = 0) => {
            if (pageSize && canvasRef.current) {
                const canvas = canvasRef.current;
                const ctx = canvas.getContext("2d");

                if (ctx) {
                    // Use different colors/opacity for multiple highlights to distinguish them
                    const alpha = Math.max(0.2, 0.8 - (index * 0.15)); // Decrease opacity for subsequent highlights
                    ctx.fillStyle = `rgba(0, 123, 255, ${alpha})`; // Semi-transparent blue
                    ctx.strokeStyle = "rgba(0, 123, 255, 0.8)";
                    ctx.lineWidth = 2;
                    
                    ctx.beginPath();

                    // Adjust scaling based on page size and zoom level
                    const scaleX = canvas.width / pageSize.width;
                    const scaleY = canvas.height / pageSize.height;

                    coords.forEach((coord, coordIndex) => {
                        const x = coord.x * scaleX * 74;
                        const y = coord.y * scaleY * 72;
                        if (coordIndex === 0) {
                            ctx.moveTo(x, y);
                        } else {
                            ctx.lineTo(x, y);
                        }
                    });
                    
                    ctx.closePath();
                    ctx.fill(); // Fill the polygon with semi-transparent color
                    ctx.stroke(); // Draw the border
                }
            }
        },
        [pageSize]
    );

    // eslint-disable-next-line react-hooks/exhaustive-deps
    const clearAndDraw = useCallback(() => {
        if (!canvasRef.current || !pageSize) return;

        const canvas = canvasRef.current;
        const ctx = canvas.getContext("2d");

        if (ctx) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Use requestAnimationFrame for smoother rendering
            requestAnimationFrame(() => {
                parsedPolygons.forEach((bound, index) => {
                    drawOverlay(bound, index);
                });
            });
        }
    }, [canvasRef, pageSize, parsedPolygons, drawOverlay]);

    useEffect(() => {
        clearAndDraw();
    }, [clearAndDraw, pageSize, parsedPolygons]);

    useEffect(() => {
        const handleResize = () => {
            if (canvasRef.current && pageSize) {
                const container = canvasRef.current.parentElement;
                if (container) {
                    const { width, height } = container.getBoundingClientRect();
                    canvasRef.current.style.width = `${width}px`;
                    canvasRef.current.style.height = `${height}px`;

                    clearAndDraw();
                }
            }
        };

        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, [clearAndDraw, pageSize]);

    return (
        <div className="pdf-highlighter">
            <div className="pdf-highlighter-inner">
                <Document file={pdfPath}>
                    <Page renderTextLayer={false} pageNumber={pageNumber} renderAnnotationLayer={false} onLoadSuccess={onPageLoadSuccess} />
                </Document>

                {pageSize && (
                    <canvas
                        ref={canvasRef}
                        width={pageSize.width}
                        height={pageSize.height}
                        className="pdf-overlay"
                    />
                )}
            </div>
        </div>
    );
};

export default PdfHighlighter;
