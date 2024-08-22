/**
 * Populate the items container with a list of item cards
 * @param {Array} items - The list of items to display
 * @param {HTMLElement} container - The container to populate
 */

const pathArray = window.location.pathname.split('/');
const tableId = pathArray[pathArray.length - 1];
sessionStorage.setItem('table_id', tableId);


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
    // Get table ID from sessionStorage or a similar mechanism
    const tableId = sessionStorage.getItem('table_id');

    if (!tableId) {
        console.error('Table ID is not available');
        return; // Exit the function early if tableId is not available
    }

    fetch(`/table/${tableId}`)
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
            const popularDishes = JSON.parse(tempDiv.querySelector('#popular-dishes-data').textContent);
            populateItemsContainer(popularDishes, itemsContainer);
        })
        .catch(error => console.error('Error:', error));
}
