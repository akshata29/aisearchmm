import React from "react";

import Editor from "@monaco-editor/react";

import {
    Body1,
    Body2,
    Button,
    Caption1,
    Dialog,
    DialogActions,
    DialogBody,
    DialogContent,
    DialogSurface,
    DialogTrigger,
    Subtitle2
} from "@fluentui/react-components";
import { ExpandUpRight20Regular } from "@fluentui/react-icons";

import { ProcessingStepType, ProcessingStepsMessage } from "../../../api/models";
import "./VerticalTimeline.css";

interface TimelineProps {
    processingStepMsg: Record<string, ProcessingStepsMessage[]>;
    darkMode?: boolean;
}

const VerticalTimeline: React.FC<TimelineProps> = ({ processingStepMsg, darkMode = false }) => {
    const [editorJSON, setEditorJSON] = React.useState<string | undefined>();
    // Detect whether Monaco (or its loader/require) is available in the page.
    // On some Azure deployments the CDN loader/worker may be blocked which causes
    // the Editor to show a permanent "Loading..." placeholder. In that case we
    // render a plain <pre> JSON fallback so the user can still read processing steps.
    const [monacoReady, setMonacoReady] = React.useState<boolean | null>(null);

    React.useEffect(() => {
        if (typeof window === "undefined") {
            setMonacoReady(false);
            return;
        }

        // If monaco or AMD require is already present, consider Monaco available.
        if ((window as any).monaco || (window as any).require) {
            setMonacoReady(true);
            return;
        }

        // Wait briefly for loader to arrive; if it doesn't, fall back.
        const interval = setInterval(() => {
            if ((window as any).monaco || (window as any).require) {
                setMonacoReady(true);
                clearInterval(interval);
                clearTimeout(timeout);
            }
        }, 200);

        const timeout = setTimeout(() => {
            setMonacoReady(false);
            clearInterval(interval);
        }, 1500);

        return () => {
            clearInterval(interval);
            clearTimeout(timeout);
        };
    }, []);
    
    return (
        <>
            <Dialog>
                <div className="timeline-container">
                    {Object.keys(processingStepMsg).map(key => (
                        <>
                            <a>Request: {key}</a>
                            {processingStepMsg[key]?.map((msg, index) => (
                                <div key={index} className="timeline-item">
                                    <div className="timeline-icon">{index + 1}</div>
                                    <div className="timeline-content">
                                        <div className="timeline-section-title">
                                            <Subtitle2>{msg.processingStep.title}</Subtitle2>
                                            {msg.processingStep.type !== ProcessingStepType.Text && (
                                                <DialogTrigger disableButtonEnhancement>
                                                    <Button
                                                        appearance="subtle"
                                                        icon={<ExpandUpRight20Regular />}
                                                        onClick={() => setEditorJSON(JSON.stringify(msg.processingStep.content, null, 2))}
                                                    />
                                                </DialogTrigger>
                                            )}
                                        </div>
                                        {msg.processingStep.type === ProcessingStepType.Text ? (
                                            <Body1 block>{msg.processingStep.content}</Body1>
                                        ) : (
                                            <>
                                                {monacoReady === true ? (
                                                    <Editor
                                                        className="content-editor"
                                                        height="200px"
                                                        defaultLanguage="json"
                                                        defaultValue={JSON.stringify(msg.processingStep.content, null, 2)}
                                                        theme={darkMode ? "vs-dark" : "vs"}
                                                    />
                                                ) : (
                                                    // Fallback when Monaco isn't available: show readable JSON
                                                    <pre style={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>
                                                        {JSON.stringify(msg.processingStep.content, null, 2)}
                                                    </pre>
                                                )}
                                                {Array.isArray(msg.processingStep.content) && (
                                                    <div className="image-container">
                                                        <Body2 className="image-title">Images passed to LLM</Body2> <br />
                                                        <div className="image-grid">
                                                            {msg.processingStep.content
                                                                .flatMap(o => o.content)
                                                                .filter(c => c?.type === "image_url")
                                                                .map(c => (
                                                                    <img className="image-item" key={c.image_url.url} src={c.image_url.url} alt="Filtered" />
                                                                )).length > 0 ? (
                                                                msg.processingStep.content
                                                                    .flatMap(o => o.content)
                                                                    .filter(c => c?.type === "image_url")
                                                                    .map(c => (
                                                                        <img
                                                                            className="image-item"
                                                                            key={c.image_url.url}
                                                                            src={c.image_url.url}
                                                                            alt="Filtered"
                                                                        />
                                                                    ))
                                                            ) : (
                                                                <Caption1>None</Caption1>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </>
                    ))}
                </div>

                        <DialogSurface className="editor-dialog">
                            <DialogBody>
                                <DialogContent>
                                    {monacoReady === true ? (
                                        <Editor height="700px" defaultLanguage="json" defaultValue={editorJSON || ""} theme={darkMode ? "vs-dark" : "vs"} />
                                    ) : (
                                        <pre style={{ whiteSpace: "pre-wrap", maxHeight: 700, overflow: "auto" }}>{editorJSON || ""}</pre>
                                    )}
                                </DialogContent>
                                <DialogActions>
                                    <DialogTrigger disableButtonEnhancement>
                                        <Button appearance="secondary">Close</Button>
                                    </DialogTrigger>
                                </DialogActions>
                            </DialogBody>
                        </DialogSurface>
            </Dialog>
        </>
    );
};

export default VerticalTimeline;
