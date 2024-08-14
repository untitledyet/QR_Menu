/**
 * Create an item card element for a food item
 * @param {Object} item - The item data
 * @returns {HTMLElement} - The item card element
 */
function createItemCard(item) {
    const itemCard = document.createElement('div');
    itemCard.classList.add('col-12', 'col-sm-6', 'col-lg-4', 'mb-4');
    itemCard.innerHTML = `
        <div class="card shadow-sm">
            <img src="/static/images/${item.ImageFilename}" class="card-img-top" alt="${item.FoodName}">
            <div class="card-body">
                <h5 class="card-title">${item.FoodName}</h5>
                <p class="card-text">${item.Ingredients}</p>
                <p class="card-text"><strong>$${item.Price}</strong></p>
            </div>
        </div>
    `;
    return itemCard;
}
