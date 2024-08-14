/**
 * Fetch promotion details by its ID
 * @param {number} promotionId - The ID of the promotion to fetch details for
 * @returns {Promise} - A promise that resolves to the promotion data
 */
function fetchPromotionDetails(promotionId) {
    return fetch(`/promotion/${promotionId}`).then(response => response.text());
}

/**
 * Handle click event for promotion cards
 */
function handlePromotionClick(card, promotionId) {
    const detailContainer = document.getElementById('promotion-detail-container');

    // Check if the clicked promotion is already active
    const isAlreadyActive = detailContainer.dataset.activePromotionId === promotionId.toString();

    if (isAlreadyActive) {
        // If already active, hide the container and remove the active ID
        detailContainer.innerHTML = '';
        detailContainer.removeAttribute('data-active-promotion-id');
    } else {
        // Fetch and display the promotion details
        fetchPromotionDetails(promotionId)
            .then(data => {
                detailContainer.innerHTML = data;
                detailContainer.dataset.activePromotionId = promotionId;

                // Add event listener for the close button
                const closeButton = detailContainer.querySelector('.close-button');
                closeButton.addEventListener('click', function () {
                    detailContainer.innerHTML = '';
                    detailContainer.removeAttribute('data-active-promotion-id');
                });

                // Only scroll to the promotion detail section if it wasn't already visible
                if (!detailContainer.hasAttribute('data-active-promotion-id')) {
                    detailContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            })
            .catch(error => console.error('Error:', error));
    }
}

/**
 * Initialize promotion card click events
 */
function initializePromotionCards() {
    const promotionCards = document.querySelectorAll('.promotion-card');
    promotionCards.forEach(card => {
        card.addEventListener('click', function () {
            const promotionId = this.dataset.promotionId;
            if (promotionId) {
                handlePromotionClick(this, promotionId);
            } else {
                console.error('Promotion ID is undefined.');
            }
        });
    });
}

// Initialize promotion cards on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function () {
    initializePromotionCards();
});
