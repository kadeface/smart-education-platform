(function($) {
    $(document).ready(function() {
        console.log("Config JS loaded");

        // 添加排名范围
        $('.add-rank').on('click', function() {
            alert("添加按钮被点击");
            var area = $(this).data('area');
            var container = $(this).closest('.rank-ranges');
            var newInput = $('<input>')
                .attr('type', 'number')
                .attr('name', 'rank_ranges_' + area)
                .attr('min', '1')
                .addClass('rank-input');
            $(this).before(newInput);
        });

        // 删除最后一个排名范围
        $('.remove-rank').on('click', function() {
            alert("删除按钮被点击");
            var container = $(this).closest('.rank-ranges');
            var inputs = container.find('input[type="number"]');
            if (inputs.length > 1) {
                inputs.last().remove();
            }
        });
    });
})(django.jQuery);