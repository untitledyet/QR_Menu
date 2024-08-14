/**
 * Fetch data for a specific subcategory by its ID
 * @param {number} subcategoryId - The ID of the subcategory to fetch data for
 * @returns {Promise} - A promise that resolves to the subcategory data
 */
function fetchSubcategoryData(subcategoryId) {
    return fetch(`/subcategory/${subcategoryId}`).then(response => response.json());
}

/**
 * Create a subcategory button element
 * @param {Object} subcategory - The subcategory data
 * @param {number} categoryId - The ID of the parent category
 * @returns {HTMLElement} - The subcategory button element
 */
function createSubcategoryCard(subcategory, categoryId) {
    const subcategoryCard = document.createElement('button');
    subcategoryCard.classList.add('subcategory-card', 'btn', 'mr-2', 'mb-2');
    subcategoryCard.dataset.subcategoryId = subcategory.SubcategoryID;
    subcategoryCard.textContent = subcategory.SubcategoryName;
    subcategoryCard.addEventListener('click', function () {
        handleSubcategoryClick(this, categoryId);
    });
    return subcategoryCard;
}

/**
 * Populate the subcategories container with a list of subcategory buttons
 * @param {Array} subcategories - The list of subcategories to display
 * @param {number} categoryId - The ID of the parent category
 * @param {HTMLElement} container - The container to populate
 */
function populateSubcategoriesContainer(subcategories, categoryId, container) {
    container.innerHTML = '';
    if (subcategories.length > 0) {
        const subcategoriesWrapper = document.createElement('div');
        subcategoriesWrapper.classList.add('subcategories');

        subcategories.forEach(sub => {
            subcategoriesWrapper.appendChild(createSubcategoryCard(sub, categoryId));
        });

        container.appendChild(subcategoriesWrapper);
    }
}

/**
 * Handle click event for subcategory buttons
 * @param {HTMLElement} card - The subcategory button that was clicked
 * @param {number} categoryId - The ID of the parent category
 */
function handleSubcategoryClick(card, categoryId) {
    const subcategoryId = card.dataset.subcategoryId;
    const isSubcategoryActive = card.classList.contains('active');
    document.querySelectorAll('.subcategory-card').forEach(card => card.classList.remove('active'));

    if (!isSubcategoryActive) {
        card.classList.add('active');
        fetchSubcategoryData(subcategoryId)
            .then(data => {
                const itemsContainer = document.getElementById('items-container');
                populateItemsContainer(data.items, itemsContainer);
            })
            .catch(error => console.error('Error:', error));
    } else {
        fetchCategoryData(categoryId)
            .then(data => {
                const itemsContainer = document.getElementById('items-container');
                populateItemsContainer(data.items, itemsContainer);
            })
            .catch(error => console.error('Error:', error));
    }
}
