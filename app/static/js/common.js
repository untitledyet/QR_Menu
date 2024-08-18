/**
 * Populate the items container with a list of item cards
 * @param {Array} items - The list of items to display
 * @param {HTMLElement} container - The container to populate
 */
function populateItemsContainer(items, container) {
    container.innerHTML = '';
    items.forEach(item => {
        container.appendChild(createItemCard(item));
    });
}

/**
 * Reset the main content to the default view
 */
function resetMainContent() {
    fetch(`/`)
        .then(response => response.text())
        .then(html => {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = html;

            // Reset the categories
            document.querySelector('.category-scroll').innerHTML = tempDiv.querySelector('.category-scroll').innerHTML;

            // Reset the items container (popular dishes)
            const itemsContainer = document.getElementById('items-container');
            itemsContainer.innerHTML = tempDiv.querySelector('#items-container').innerHTML;

            // Reset the section title
            document.getElementById('section-title').textContent = tempDiv.querySelector('#section-title').textContent;

            // Reset the subcategories container
            document.querySelector('.subcategories-container').innerHTML = tempDiv.querySelector('.subcategories-container').innerHTML;

            // Initialize the category cards again after reset
            initializeCategoryCards();

            // Populate popular dishes again if needed
            const popularDishes = JSON.parse(tempDiv.querySelector('script[type="application/json"]').textContent);
            populateItemsContainer(popularDishes, itemsContainer);
        })
        .catch(error => console.error('Error:', error));
}
