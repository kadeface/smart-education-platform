// static/score_analysis/js/exam_list.js
document.addEventListener('DOMContentLoaded', function() {
    // 为生成统计按钮添加确认对话框
    const generateButtons = document.querySelectorAll('a[href*="generate-statistics"]');

    generateButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            if (!confirm('确定要生成统计数据吗？这可能需要一些时间。')) {
                e.preventDefault();
            }
        });
    });
});