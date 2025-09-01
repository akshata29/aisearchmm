import React from "react";
import { Card, CardHeader, CardPreview, Text, Badge } from "@fluentui/react-components";
import { 
    QuestionCircleRegular,
    MoneyRegular,
    NewsRegular,
    GlobeRegular,
    BrainCircuitRegular,
    PeopleRegular,
    DataTrendingRegular
} from "@fluentui/react-icons";

import "./Samples.css";
import samplesData from "../../../content/samples.json";

interface Props {
    handleQuery: (q: string, isNew?: boolean) => void;
}

const newQuery = "New query...";

// Sample question categories with icons and descriptions
const getCategoryInfo = (question: string) => {
    const lowerQ = question.toLowerCase();
    
    if (lowerQ.includes('invest') || lowerQ.includes('money') || lowerQ.includes('dollar')) {
        return { icon: <MoneyRegular />, category: "Investment Strategy", color: "success" as const };
    }
    if (lowerQ.includes('stock') || lowerQ.includes('market')) {
        return { icon: <DataTrendingRegular />, category: "Market Analysis", color: "important" as const };
    }
    if (lowerQ.includes('ai') || lowerQ.includes('research')) {
        return { icon: <BrainCircuitRegular />, category: "AI & Research", color: "brand" as const };
    }
    if (lowerQ.includes('republican') || lowerQ.includes('democrat') || lowerQ.includes('politic')) {
        return { icon: <PeopleRegular />, category: "Politics & Markets", color: "warning" as const };
    }
    if (lowerQ.includes('oil') || lowerQ.includes('war') || lowerQ.includes('china')) {
        return { icon: <NewsRegular />, category: "Global Events", color: "danger" as const };
    }
    if (lowerQ.includes('global') || lowerQ.includes('us') || lowerQ.includes('s&p')) {
        return { icon: <GlobeRegular />, category: "Global Markets", color: "informative" as const };
    }
    
    return { icon: <QuestionCircleRegular />, category: "General", color: "subtle" as const };
};

const Samples: React.FC<Props> = ({ handleQuery }) => {
    const samples: string[] = samplesData.queries;

    return (
        <div className="samples-container">
            <div className="samples-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center', marginBottom: '8px' }}>
                    <QuestionCircleRegular style={{ fontSize: '20px', color: 'var(--colorBrandForeground1)' }} />
                    <Text as="h2" size={500} weight="semibold">
                        Popular Questions
                    </Text>
                    <Text size={300} className="samples-subtitle">
                        Click on any question to start exploring your financial data
                    </Text>
                </div>
                
            </div>
            
            <div className="samples-wrapper">
                {samples &&
                    samples.map((sample, index) => {
                        const categoryInfo = getCategoryInfo(sample);
                        return (
                            <Card
                                key={index}
                                className="sample-card"
                                onClick={() => handleQuery(sample, sample === newQuery)}
                                role="button"
                                tabIndex={0}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                        handleQuery(sample, sample === newQuery);
                                    }
                                }}
                            >
                                <CardHeader>
                                    <div className="sample-header">
                                        <div className="sample-icon">
                                            {categoryInfo.icon}
                                        </div>
                                        <Badge appearance="tint" size="small">
                                            {categoryInfo.category}
                                        </Badge>
                                    </div>
                                </CardHeader>
                                <CardPreview>
                                    <div className="sample-content">
                                        <Text size={300} weight="medium" className="sample-question">
                                            {sample}
                                        </Text>
                                    </div>
                                </CardPreview>
                            </Card>
                        );
                    })}
            </div>
        </div>
    );
};

export default Samples;
