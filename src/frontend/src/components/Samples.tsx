import React from "react";

import "./Samples.css";
import samplesData from "../content/samples.json";

interface Props {
    handleQuery: (q: string, isNew?: boolean) => void;
}

const newQuery = "New query...";

const Samples: React.FC<Props> = ({ handleQuery }) => {
    const samples: string[] = samplesData.queries;

    return (
        <div className="samples-container">
            <div className="samples-wrapper">
                {samples &&
                    samples.map((sample, index) => (
                        <div
                            key={index}
                            onClick={() => handleQuery(sample, sample === newQuery)}
                            className="samples"
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    handleQuery(sample, sample === newQuery);
                                }
                            }}
                        >
                            {sample}
                        </div>
                    ))}
            </div>
        </div>
    );
};

export default Samples;
