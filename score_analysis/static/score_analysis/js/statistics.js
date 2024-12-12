document.addEventListener('DOMContentLoaded', function() {
    // 获取数据
    const scienceData = JSON.parse(document.getElementById('science-data').textContent);
    const artsData = JSON.parse(document.getElementById('arts-data').textContent);

    // Tab切换功能
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabId = button.getAttribute('data-tab');

            // 更新按钮状态
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');

            // 更新内容显示
            tabContents.forEach(content => {
                content.classList.remove('active');
                if (content.id === `${tabId}-content`) {
                    content.classList.add('active');
                }
            });
        });
    });

    // 填充数据函数
    function fillData(data, prefix) {
        // 基础数据
        document.getElementById(`${prefix}_school_count`).textContent = data.school_count || '-';
        document.getElementById(`${prefix}_student_count`).textContent = data.student_count || '-';
        document.getElementById(`${prefix}_mean_score`).textContent = (data.mean_score || 0).toFixed(2);
        document.getElementById(`${prefix}_max_score`).textContent = data.max_score || '-';
        document.getElementById(`${prefix}_top_school`).textContent = data.top_school || '-';

        // 分数线数据
        const thresholds = ['qb', '985', '211'];
        thresholds.forEach(threshold => {
            document.getElementById(`${prefix}_${threshold}_line`).textContent = data[`${threshold}_line`] || '-';
            document.getElementById(`${prefix}_${threshold}_count`).textContent = data[`${threshold}_count`] || '-';
            document.getElementById(`${prefix}_${threshold}_rate`).textContent =
                ((data[`${threshold}_rate`] || 0) * 100).toFixed(2);
        });

        // 平均分数据
        const subjects = prefix === 'science'
            ? ['total', 'chinese', 'math', 'english', 'physics', 'chemistry', 'biology']
            : ['total', 'chinese', 'math', 'english', 'politics', 'history', 'geography'];

        subjects.forEach(subject => {
            document.getElementById(`${prefix}_${subject}_avg`).textContent =
                (data[`${subject}_avg`] || 0).toFixed(2);
        });

        // 优秀生分布
        const ranks = ['10', '20', '50', '100', '200', '500'];
        if (prefix === 'science') ranks.push('1250');

        ranks.forEach(rank => {
            document.getElementById(`${prefix}_top${rank}_min`).textContent =
                data[`top${rank}_min`] || '-';
            document.getElementById(`${prefix}_top${rank}_total`).textContent =
                data[`top${rank}_total`] || '-';
        });

        // 填充学校数据
        if (data.school_stats) {
            const tbody = document.querySelector(`#${prefix}-school-stats-body`);
            tbody.innerHTML = '';

            data.school_stats.forEach((school, index) => {
                const row = document.createElement('tr');
                row.id = `${prefix}_school_avg_${index + 1}`;

                // 添加学校数据列
                row.innerHTML = `
                    <td>${school.name}</td>
                    ${subjects.map(subject => `
                        <td>${(school.scores[subject].avg || 0).toFixed(2)}</td>
                        <td>${school.scores[subject].rank || '-'}</td>
                    `).join('')}
                `;

                tbody.appendChild(row);
            });
        }
    }

    // 填充数据
    if (scienceData) fillData(scienceData, 'science');
    if (artsData) fillData(artsData, 'arts');
});