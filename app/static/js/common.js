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

            document.querySelector('.category-scroll').innerHTML = tempDiv.querySelector('.category-scroll').innerHTML;
            document.getElementById('items-container').innerHTML = tempDiv.querySelector('#items-container').innerHTML;
            document.getElementById('section-title').textContent = tempDiv.querySelector('#section-title').textContent;
            document.querySelector('.subcategories-container').innerHTML = tempDiv.querySelector('.subcategories-container').innerHTML;

            initializeCategoryCards();
        })
        .catch(error => console.error('Error:', error));
}
