
export interface ReportData {
    id: string;
    title: string;
    type: string;
    createdAt: Date;
    status: 'generating' | 'completed';
}

// Mock API for now since backend doesn't have report endpoint yet
export const generateReport = async (type: string, timeRange: string): Promise<ReportData> => {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 2000));

    const typeLabels: Record<string, string> = {
        production: '生產分析報表',
        quality: '品質分析報表',
        equipment: '設備效能報表',
        cost: '成本分析報表'
    };

    const timeLabels: Record<string, string> = {
        today: '今日',
        week: '本週',
        month: '本月',
        quarter: '本季',
        custom: '自訂區間'
    };

    return {
        id: Date.now().toString(),
        title: `${typeLabels[type] || '報表'} - ${timeLabels[timeRange] || ''}`,
        type: typeLabels[type] || '報表',
        createdAt: new Date(),
        status: 'completed'
    };
};
