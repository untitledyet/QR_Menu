window.addEventListener('load', function() {
    var footerNav = document.querySelector('.footer-nav');
    var parent = document.querySelector('.mt-5');

    // Define adjustments for width and positioning
    var widthAdjustment = -20; // Modify this value to decrease or increase the width
    var positionAdjustment = 10; // Modify this value to shift the menu left or right

    function adjustFooterWidth() {
        var parentWidth = parent.clientWidth;
        footerNav.style.width = (parentWidth + widthAdjustment) + 'px';
        footerNav.style.left = (parent.getBoundingClientRect().left + positionAdjustment) + 'px';
    }

    adjustFooterWidth();

    window.addEventListener('resize', adjustFooterWidth);
});
