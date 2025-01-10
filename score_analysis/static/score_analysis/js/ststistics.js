document.addEventListener('DOMContentLoaded', function() {
    // 获取URL参数
    const urlParams = new URLSearchParams(window.location.search);
    const examId = urlParams.get('exam_id');

    if (!examId) {
        console.warn('No exam_id provided');
        return;
    }

    // 获取统计数据
    fetch(`/api/statistics/${examId}/`)
        .then(response => response.json())
        .then(data => {
            updateStatistics(data);
        })
        .catch(error => console.error('Error:', error));
});

function updateStatistics(data) {
    // 更新文理科Tab的显示状态
    updateTabVisibility(data);

    // 更新理科数据
    if (data.science_stats) {
        updateScienceStats(data.science_stats);
    }

    // 更新文科数据
    if (data.arts_stats) {
        updateArtsStats(data.arts_stats);
    }
}

function updateTabVisibility(data) {
    const scienceTab = document.querySelector('[data-tab="science"]');
    const artsTab = document.querySelector('[data-tab="arts"]');

    if (!data.science_stats) {
        scienceTab.style.display = 'none';
    }
    if (!data.arts_stats) {
        artsTab.style.display = 'none';
    }
}

function updateScienceStats(stats) {
    // 更新学校统计表格
    const schoolStatsBody = document.getElementById('science-school-stats-body');
    if (stats.school_distribution && schoolStatsBody) {
        let schoolRows = '';
        Object.entries(stats.school_distribution).forEach(([school, schoolData]) => {
            if (school === 'total') return; // 跳过总计行

            schoolRows += `
                <tr>
                    <td>${school}</td>
                    <td>${schoolData.student_count || '-'}</td>
                    <td>${schoolData.max_score || '-'}</td>
                    <td>${schoolData.min_score || '-'}</td>
                    <td>${schoolData.mean_score ? schoolData.mean_score.toFixed(2) : '-'}</td>
                    <td>${schoolData.mean_rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.C9?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.C9?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.C9?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['985']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['985']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['985']?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['211']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['211']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['211']?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['特控']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['特控']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['特控']?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['本科']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['本科']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['本科']?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['专科']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['专科']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['专科']?.rank || '-'}</td>
                </tr>
            `;
        });
        schoolStatsBody.innerHTML += schoolRows;
    }

    // 更新优秀学生分布表格
    updateTopStudentsTable('science', stats.rank_distribution);
}

function updateArtsStats(stats) {
    // 更新学校统计表格
    const schoolStatsBody = document.getElementById('arts-school-stats-body');
    if (stats.school_distribution && schoolStatsBody) {
        let schoolRows = '';
        Object.entries(stats.school_distribution).forEach(([school, schoolData]) => {
            if (school === 'total') return;

            // 与理科类似的结构
            schoolRows += `
                <tr>
                    <td>${school}</td>
                    <td>${schoolData.student_count || '-'}</td>
                    <td>${schoolData.max_score || '-'}</td>
                    <td>${schoolData.min_score || '-'}</td>
                    <td>${schoolData.mean_score ? schoolData.mean_score.toFixed(2) : '-'}</td>
                    <td>${schoolData.mean_rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.C9?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.C9?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.C9?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['985']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['985']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['985']?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['211']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['211']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['211']?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['特控']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['特控']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['特控']?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['本科']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['本科']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['本科']?.rank || '-'}</td>
                    <td>${schoolData.threshold_stats?.['专科']?.count || '-'}</td>
                    <td>${schoolData.threshold_stats?.['专科']?.rate || '-'}</td>
                    <td>${schoolData.threshold_stats?.['专科']?.rank || '-'}</td>
                </tr>
            `;
        });
        schoolStatsBody.innerHTML += schoolRows;
    }

    // 更新优秀学生分布表格
    updateTopStudentsTable('arts', stats.rank_distribution);
}

function updateTopStudentsTable(type, rankData) {
    if (!rankData) return;

    const tableBody = document.querySelector(`#${type}-top-students-body`);
    if (!tableBody) return;

    let rows = '';
    Object.entries(rankData.school_distribution || {}).forEach(([school, data]) => {
        if (school === 'total') return;

        rows += `
            <tr>
                <td>${school}</td>
                <td>${data.top_10 || '-'}</td>
                <td>${data.top_20 || '-'}</td>
                <td>${data.top_50 || '-'}</td>
                <td>${data.top_100 || '-'}</td>
                <td>${data.top_200 || '-'}</td>
                <td>${data.top_500 || '-'}</td>
            </tr>
        `;
    });
    tableBody.innerHTML += rows;
}

// Tab切换功能
document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', function() {
        // 移除所有active类
        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

        // 添加active类到当前选中的tab
        this.classList.add('active');
        document.getElementById(`${this.dataset.tab}-content`).classList.add('active');
    });
});