document.addEventListener('DOMContentLoaded', function () {
    // Retrieve the table ID from sessionStorage
    const tableId = sessionStorage.getItem('table_id');
    if (tableId) {
        sessionStorage.setItem('table_id', tableId);
    } else {
        console.error('Table ID not found in session storage.');
    }

    // Initialize category cards for user interaction
    initializeCategoryCards();
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
 * Fetch initial content to reset the page to its original state
 * @returns {Promise} - A promise that resolves to the initial page content
 */
function fetchInitialContent() {
    const tableId = sessionStorage.getItem('table_id');
    if (!tableId) {
        console.error('Table ID not found in sessionStorage.');
        return Promise.reject('Table ID not found.');
    }

    return fetch(`/table/${tableId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.text();
        });
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
        // Activate the clicked card and fetch its data
        card.classList.add('active');
        const categoryId = card.dataset.categoryId;
        const categoryName = card.dataset.categoryName;

        fetchCategoryData(categoryId)
            .then(data => {
                sectionTitle.textContent = `${categoryName} Dishes`;
                populateItemsContainer(data.items, itemsContainer);
                populateSubcategoriesContainer(data.subcategories, categoryId, subcategoriesContainer);
            })
            .catch(error => console.error('Error fetching category data:', error));
    } else {
        // Reset to initial content when the active card is clicked again
        fetchInitialContent()
            .then(html => {
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = html;

                // Update the page content with the initial data
                updatePageContent(tempDiv);

                // Reinitialize category cards after resetting content
                initializeCategoryCards();
            })
            .catch(error => console.error('Error fetching initial content:', error));
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
 * Update the page content with initial HTML data
 * @param {HTMLElement} tempDiv - Temporary container for new HTML content
 */
function updatePageContent(tempDiv) {
    const newCategories = tempDiv.querySelector('.category-scroll');
    const newItemsContainer = tempDiv.querySelector('#items-container');
    const newSectionTitle = tempDiv.querySelector('#section-title');
    const newSubcategoriesContainer = tempDiv.querySelector('.subcategories-container');
    const newPopularDishes = tempDiv.querySelector('#popular-dishes');

    if (newCategories) {
        document.querySelector('.category-scroll').innerHTML = newCategories.innerHTML;
    }

    if (newItemsContainer) {
        document.getElementById('items-container').innerHTML = newItemsContainer.innerHTML;
    }

    if (newSectionTitle) {
        document.getElementById('section-title').textContent = newSectionTitle.textContent;
    }

    if (newSubcategoriesContainer) {
        document.querySelector('.subcategories-container').innerHTML = newSubcategoriesContainer.innerHTML;
    }

    if (newPopularDishes) {
        const popularDishesData = JSON.parse(newPopularDishes.textContent);
        populateItemsContainer(popularDishesData, document.getElementById('items-container'));
    }
}
