import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';
import { Card } from '@fluentui/react-components';
import './ProfessionalUpload.css';

interface ProgressChartProps {
    progress: number;
}

export const ProgressChart: React.FC<ProgressChartProps> = ({ progress }) => {
    const data = [
        { name: 'Completed', value: progress },
        { name: 'Remaining', value: 100 - progress },
    ];

    const COLORS = ['var(--colorBrandBackground)', 'var(--colorNeutralBackground2)'];

    const processingSteps = [
        { name: 'Upload', value: progress > 20 ? 100 : (progress / 20) * 100 },
        { name: 'OCR', value: progress > 40 ? 100 : progress > 20 ? ((progress - 20) / 20) * 100 : 0 },
        { name: 'Analysis', value: progress > 60 ? 100 : progress > 40 ? ((progress - 40) / 20) * 100 : 0 },
        { name: 'Embedding', value: progress > 80 ? 100 : progress > 60 ? ((progress - 60) / 20) * 100 : 0 },
        { name: 'Indexing', value: progress > 80 ? ((progress - 80) / 20) * 100 : 0 },
    ];

    return (
        <Card className="progress-chart-card">
            <div className="chart-container">
                <div className="chart-section">
                    <h4>Overall Progress</h4>
                    <ResponsiveContainer width="100%" height={120}>
                        <PieChart>
                            <Pie
                                data={data}
                                cx="50%"
                                cy="50%"
                                innerRadius={30}
                                outerRadius={50}
                                paddingAngle={2}
                                dataKey="value"
                            >
                                {data.map((_entry, index) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip formatter={(value: any) => `${value}%`} />
                        </PieChart>
                    </ResponsiveContainer>
                </div>
                
                <div className="chart-section">
                    <h4>Processing Steps</h4>
                    <ResponsiveContainer width="100%" height={120}>
                        <BarChart data={processingSteps}>
                            <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                            <YAxis hide />
                            <Tooltip formatter={(value: any) => `${Math.round(Number(value))}%`} />
                            <Bar dataKey="value" fill="var(--colorBrandBackground)" radius={[2, 2, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </Card>
    );
};
