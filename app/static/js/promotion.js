/**
 * Initialize the promotion carousel
 * Adds event listeners for scrolling and updates UI elements accordingly
 */
function initializePromotionCarousel() {
    const promotionScroll = document.querySelector('.promotion-scroll');
    const prevButton = document.querySelector('.carousel-control-prev');
    const nextButton = document.querySelector('.carousel-control-next');

    prevButton.addEventListener('click', () => {
        promotionScroll.scrollBy({ left: -300, behavior: 'smooth' });
    });

    nextButton.addEventListener('click', () => {
        promotionScroll.scrollBy({ left: 300, behavior: 'smooth' });
    });

    // Update button states based on scroll position
    promotionScroll.addEventListener('scroll', () => {
        const scrollLeft = promotionScroll.scrollLeft;
        const maxScrollLeft = promotionScroll.scrollWidth - promotionScroll.clientWidth;

        prevButton.disabled = scrollLeft === 0;
        nextButton.disabled = scrollLeft >= maxScrollLeft;
    });

    // Initial state update
    promotionScroll.dispatchEvent(new Event('scroll'));
}

// Initialize promotion carousel on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function () {
    initializePromotionCarousel();
});
