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
            <img src="/static/images/${item.ImageFilename || 'default-image.png'}" class="card-img-top" alt="${item.FoodName || 'Unnamed Item'}">
            <div class="card-body">
                <h5 class="card-title">${item.FoodName || 'Unnamed Item'}</h5>
                <p class="card-text">${item.Ingredients || 'No ingredients specified'}</p>
                <p class="card-text"><strong>$${item.Price.toFixed(2)}</strong></p>
                <a href="#" class="add-to-cart" data-item-id="${item.FoodItemID}">
                    <img src="/static/images/cart-icon.png" alt="Add to Cart" title="Add to Cart">
                </a>
            </div>
        </div>
    `;

    // Add click event for the "Add to Cart" button
    itemCard.querySelector('.add-to-cart').addEventListener('click', function (event) {
        event.preventDefault();
        showItemPopup(item);
    });

    return itemCard;
}

/**
 * Populate the items container with popular dishes
 * @param {Array} dishes - The list of popular dishes to display
 * @param {HTMLElement} container - The container to populate
 */
function populateItemsContainer(dishes, container) {
    container.innerHTML = '';
    dishes.forEach(dish => {
        container.appendChild(createItemCard(dish));
    });
}

/**
 * Show a popup with item details
 * @param {Object} item - The item data
 */
function showItemPopup(item) {
    const modalImage = document.querySelector('#item-modal .modal-body img');
    const modalTitle = document.querySelector('#item-modal .modal-title');
    const modalIngredientsList = document.querySelector('#item-modal .modal-body ul');

    modalImage.src = `/static/images/${item.ImageFilename || 'default-image.png'}`;
    modalImage.alt = item.FoodName || 'Unnamed Item';
    modalTitle.textContent = item.FoodName || 'Unnamed Item';

    // Clear existing ingredients
    modalIngredientsList.innerHTML = '';

    // Store modified ingredients
    const modifiedIngredients = [];

    // Add ingredients to the list
    const ingredients = item.Ingredients ? item.Ingredients.split(',') : [];
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
    const ingredientKey = item.FoodItemID + '-' +
        (modifiedIngredients.length > 0
            ? modifiedIngredients.sort((a, b) => a.name.localeCompare(b.name)).map(ing => `${ing.name}-${ing.action}`).join('|')
            : item.Ingredients ? item.Ingredients.split(',').sort().map(name => `${name.trim()}-default`).join('|')
                : 'default');


    // Check if an item with the same ID and ingredientKey exists in the cart
    const existingItemIndex = cart.findIndex(cartItem =>
        cartItem.id === item.FoodItemID &&
        cartItem.ingredientKey === ingredientKey
    );


    if (existingItemIndex !== -1) {

        cart[existingItemIndex].quantity += 1;


        //alert(`${item.FoodName} is already in the cart with the same ingredients!`);
    } else {
        // If the item doesn't exist in the cart, add it
        const cartItem = {
            id: item.FoodItemID,
            name: item.FoodName || 'Unnamed Item',
            price: item.Price,
            imageFilename: item.ImageFilename || 'default-image.png',
            ingredients: modifiedIngredients.length > 0 ? modifiedIngredients : item.Ingredients ? item.Ingredients.split(',').map(name => ({
                name: name.trim(),
                action: 'default'
            })) : [],
            quantity: 1, // Start with quantity 1
            ingredientKey: ingredientKey // Store the unique key
        };

        cart.push(cartItem);
    }

    sessionStorage.setItem('cart', JSON.stringify(cart));
    //alert(`${item.FoodName} added to cart!`);
    $('#item-modal').modal('hide');
}


/**
 * Load popular dishes and new dishes on DOMContentLoaded
 */
document.addEventListener('DOMContentLoaded', function () {
    const itemsContainer = document.getElementById('items-container');
    const newItemsContainer = document.getElementById('new-dishes-container');

    const popularDishes = JSON.parse(document.querySelector('#popular-dishes-data').textContent);
    populateItemsContainer(popularDishes, itemsContainer);

    const newDishes = JSON.parse(document.querySelector('#new-dishes-data').textContent);
    populateItemsContainer(newDishes, newItemsContainer);
});
