/**
 * Create an item card element for a food item
 * @param {Object} item - The item data
 * @returns {HTMLElement} - The item card element
 */
function createItemCard(item) {
    const itemCard = document.createElement('div');
    itemCard.classList.add('col-12', 'col-sm-6', 'col-lg-4', 'mb-4');
    itemCard.innerHTML = `
        <div class="card shadow-sm item-card">
            <img src="/static/images/${item.ImageFilename || 'default-image.png'}" class="card-img-top" alt="${item.FoodName || 'Unnamed Item'}">
            <div class="card-body item-card-body">
                <h5 class="card-title">${item.FoodName || 'Unnamed Item'}</h5>
                <p class="card-text">${item.Ingredients || 'No ingredients specified'}</p>
                <p class="price-tag"><strong>$${item.Price ? item.Price.toFixed(2) : '0.00'}</strong></p>
                <a href="#" class="add-to-cart-btn" data-item-id="${item.FoodItemID}">
                    <img src="/static/images/cart-icon.png" alt="Add to Cart" title="Add to Cart">
                </a>
            </div>
        </div>
    `;

    // Add click event for the "Add to Cart" button
    itemCard.querySelector('.add-to-cart-btn').addEventListener('click', function (event) {
        event.preventDefault();
        showItemPopup(item);
    });

    return itemCard;
}


/**
 * Populate the items container with food items
 * @param {Array} items - The list of food items to display
 * @param {HTMLElement} container - The container to populate
 */
function populateItemsContainer(items, container) {
    container.innerHTML = '';
    if (items && items.length > 0) {
        items.forEach(item => {
            container.appendChild(createItemCard(item));
        });
    } else {
        container.innerHTML = '<p>No items available.</p>';
    }
}

/**
 * Show a popup with item details
 * @param {Object} item - The item data
 */
function showItemPopup(item) {
    const modalImage = document.querySelector('#item-modal .modal-body img');
    const modalTitle = document.querySelector('#item-modal .modal-title');
    const modalIngredientsList = document.querySelector('#item-modal .modal-body ul');

    if (modalImage && modalTitle && modalIngredientsList) {
        modalImage.src = `/static/images/${item.image_filename || 'default-image.png'}`;
        modalImage.alt = item.name || 'Unnamed Item';
        modalTitle.textContent = item.name || 'Unnamed Item';

        // Clear existing ingredients
        modalIngredientsList.innerHTML = '';

        // Store modified ingredients
        const modifiedIngredients = [];

        // Add ingredients to the list
        const ingredients = item.ingredients ? item.ingredients.split(',') : [];
        ingredients.forEach((ingredient, index) => {
            if (!ingredient) return;

            const li = document.createElement('li');
            li.classList.add('ingredient-item');

            li.innerHTML = `
                <button class="btn btn-minus">-</button>
                <span class="ingredient-name">${ingredient.trim()}</span>
                <button class="btn btn-plus">+</button>
            `;

            modalIngredientsList.appendChild(li);

            // Add event listeners for the buttons
            li.querySelector('.btn-minus').addEventListener('click', function () {
                handleIngredientChange(li, 'minus', index, modifiedIngredients, ingredient.trim());
            });

            li.querySelector('.btn-plus').addEventListener('click', function () {
                handleIngredientChange(li, 'plus', index, modifiedIngredients, ingredient.trim());
            });

            // Initially check the button states
            updateButtonStates(li);
        });

        // Add event listener to the "Add to Cart" button
        document.getElementById('modal-add-to-cart').replaceWith(document.getElementById('modal-add-to-cart').cloneNode(true));

        document.getElementById('modal-add-to-cart').addEventListener('click', function () {
            addToCart(item, modifiedIngredients);
        });

        // Show the modal
        $('#item-modal').modal('show');
    } else {
        console.error('Modal elements not found.');
    }
}

/**
 * Handle ingredient changes within the modal
 * @param {HTMLElement} li - The list item element
 * @param {string} action - The action ('plus' or 'minus')
 * @param {number} index - The index of the ingredient
 * @param {Array} modifiedIngredients - The array to store modified ingredients
 * @param {string} ingredientName - The name of the ingredient
 */
function handleIngredientChange(li, action, index, modifiedIngredients, ingredientName) {
    if (action === 'minus') {
        if (li.classList.contains('extra')) {
            li.classList.remove('extra');
            modifiedIngredients[index] = {name: ingredientName, action: 'default'};
        } else if (!li.classList.contains('strikethrough')) {
            li.classList.add('strikethrough');
            modifiedIngredients[index] = {name: ingredientName, action: 'remove'};
        }
    } else if (action === 'plus') {
        if (li.classList.contains('strikethrough')) {
            li.classList.remove('strikethrough');
            modifiedIngredients[index] = {name: ingredientName, action: 'default'};
        } else if (!li.classList.contains('extra')) {
            li.classList.add('extra');
            modifiedIngredients[index] = {name: ingredientName, action: 'add'};
        }
    }
    updateButtonStates(li);
}

/**
 * Update the states of the ingredient buttons
 * @param {HTMLElement} li - The list item element
 */
function updateButtonStates(li) {
    const minusBtn = li.querySelector('.btn-minus');
    const plusBtn = li.querySelector('.btn-plus');

    if (li.classList.contains('strikethrough')) {
        minusBtn.disabled = true;
        plusBtn.disabled = false;
    } else if (li.classList.contains('extra')) {
        plusBtn.disabled = true;
        minusBtn.disabled = false;
    } else {
        minusBtn.disabled = false;
        plusBtn.disabled = false;
    }
}

/**
 * Add the item to the cart with the modified ingredients
 * @param {Object} item - The item data
 * @param {Array} modifiedIngredients - The modified ingredients
 */
function addToCart(item, modifiedIngredients) {
    let cart = JSON.parse(sessionStorage.getItem('cart')) || [];

    // Generate a unique key based on the item's ID and modified ingredients
    const ingredientKey = item.id + '-' +
        (modifiedIngredients.length > 0
            ? modifiedIngredients.sort((a, b) => a.name.localeCompare(b.name)).map(ing => `${ing.name}-${ing.action}`).join('|')
            : item.ingredients ? item.ingredients.split(',').sort().map(name => `${name.trim()}-default`).join('|')
                : 'default');

    // Check if an item with the same ID and ingredientKey exists in the cart
    const existingItemIndex = cart.findIndex(cartItem =>
        cartItem.id === item.id &&
        cartItem.ingredientKey === ingredientKey
    );

    if (existingItemIndex !== -1) {
        cart[existingItemIndex].quantity += 1;
    } else {
        const cartItem = {
            id: item.id,
            name: item.name || 'Unnamed Item',
            price: item.price,
            image_filename: item.image_filename || 'default-image.png',
            ingredients: modifiedIngredients.length > 0 ? modifiedIngredients : item.ingredients ? item.ingredients.split(',').map(name => ({
                name: name.trim(),
                action: 'default'
            })) : [],
            quantity: 1,
            ingredientKey: ingredientKey
        };

        cart.push(cartItem);
    }

    sessionStorage.setItem('cart', JSON.stringify(cart));
    updateCartItemCount(); // Update the cart item count after adding an item
    $('#item-modal').modal('hide');
}

/**
 * Load popular dishes and new dishes on DOMContentLoaded
 */
// დაუყოვნებლივ ინიციალიზირებული ფუნქცია (IIFE) რომელიც უზრუნველყოფს სქრიპტის ერთად შესასრულებლობას
(function() {
    if (window.hasInitialized) {
        return;
    }

    window.hasInitialized = true;

    document.addEventListener('DOMContentLoaded', function () {
        const itemsContainer = document.getElementById('items-container');
        const newItemsContainer = document.getElementById('new-dishes-container');

        try {
            const popularDishesDataElement = document.querySelector('#popular-dishes-data');
            if (popularDishesDataElement) {
                const popularDishes = JSON.parse(popularDishesDataElement.textContent);
                populateItemsContainer(popularDishes, itemsContainer);
            } else {
                console.error('#popular-dishes-data element not found.');
            }
        } catch (error) {
            console.error('Error loading popular dishes:', error);
        }

        try {
            const newDishesDataElement = document.querySelector('#new-dishes-data');
            if (newDishesDataElement) {
                const newDishes = JSON.parse(newDishesDataElement.textContent);
                populateItemsContainer(newDishes, newItemsContainer);
            } else {
                console.error('#new-dishes-data element not found.');
            }
        } catch (error) {
            console.error('Error loading new dishes:', error);
        }

        updateCartItemCount();
    });
})();





