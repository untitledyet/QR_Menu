/**
 * Fetch data for a specific category by its ID
 * @param {number} categoryId - The ID of the category to fetch data for
 * @returns {Promise} - A promise that resolves to the category data
 */
function fetchCategoryData(categoryId) {
    return fetch(`/category/${categoryId}`).then(response => response.json());
}

/**
 * Handle click event for category cards
 * @param {HTMLElement} card - The category card that was clicked
 * @param {NodeList} categoryCards - The list of all category cards
 * @param {HTMLElement} itemsContainer - The container to populate with items
 * @param {HTMLElement} sectionTitle - The section title element to update
 * @param {HTMLElement} subcategoriesContainer - The container to populate with subcategories
 */
function handleCategoryClick(card, categoryCards, itemsContainer, sectionTitle, subcategoriesContainer) {
    const isActive = card.classList.contains('active');
    categoryCards.forEach(card => card.classList.remove('active'));

    if (!isActive) {
        card.classList.add('active');
        const categoryId = card.dataset.categoryId;
        const categoryName = card.dataset.categoryName;

        fetchCategoryData(categoryId)
            .then(data => {
                sectionTitle.textContent = `${categoryName}`;
                populateItemsContainer(data.items, itemsContainer);
                populateSubcategoriesContainer(data.subcategories, categoryId, subcategoriesContainer);
            })
            .catch(error => console.error('Error:', error));
    } else {
        resetMainContent();
    }
}

/**
 * Initialize category card click events
 */
function initializeCategoryCards() {
    const categoryCards = document.querySelectorAll('.category-card');
    const itemsContainer = document.getElementById('items-container');
    const sectionTitle = document.getElementById('section-title');
    const subcategoriesContainer = document.querySelector('.subcategories-container');

    categoryCards.forEach(card => {
        card.addEventListener('click', function () {
            handleCategoryClick(this, categoryCards, itemsContainer, sectionTitle, subcategoriesContainer);
        });
    });
}

// Initialize category cards on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function () {
    initializeCategoryCards();
});
