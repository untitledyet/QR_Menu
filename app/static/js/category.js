document.addEventListener('DOMContentLoaded', function () {
    initializeCategoryCards();
    loadInitialContent(); // Load initial content on page load
});

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
        loadInitialContent(); // Load initial content when the active category is clicked again
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

/**
 * Load initial content for the main page
 */
function loadInitialContent() {
    const itemsContainer = document.getElementById('items-container');
    const sectionTitle = document.getElementById('section-title');
    const subcategoriesContainer = document.querySelector('.subcategories-container');

    // Fetch initial data (adjust the endpoint and data processing as needed)
    fetch('/initial-content')
        .then(response => response.json())
        .then(data => {
            sectionTitle.textContent = data.title || 'საწყისი კონტენტი'; // Adjust the title as needed
            populateItemsContainer(data.items, itemsContainer);
            populateSubcategoriesContainer(data.subcategories, null, subcategoriesContainer);
        })
        .catch(error => console.error('Error loading initial content:', error));
}
