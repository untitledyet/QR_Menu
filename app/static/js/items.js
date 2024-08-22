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
                <!-- Add to Cart Icon -->
                <a href="#" class="add-to-cart" data-item-id="${item.FoodItemID}">
                    <img src="/static/images/cart-icon.png" alt="Add to Cart" title="Add to Cart">
                </a>
            </div>
        </div>
    `;

    // Add click event for the "Add to Cart" button
    itemCard.querySelector('.add-to-cart').addEventListener('click', function(event) {
        event.preventDefault();
        showItemPopup(item);
    });

    return itemCard;
}

/**
 * Show a popup with item details
 * @param {Object} item - The item data
 */

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
 * Load popular dishes and new dishes on DOMContentLoaded
 */
document.addEventListener('DOMContentLoaded', function () {
    const itemsContainer = document.getElementById('items-container');
    const newItemsContainer = document.getElementById('new-dishes-container');

    // Fetch the popular dishes data embedded in the page
    const popularDishes = JSON.parse(document.querySelector('#popular-dishes-data').textContent);

    // Populate the items container with the fetched popular dishes
    populateItemsContainer(popularDishes, itemsContainer);

    // Fetch the new dishes data embedded in the page
    const newDishes = JSON.parse(document.querySelector('#new-dishes-data').textContent);

    // Populate the new items container with the fetched new dishes
    populateItemsContainer(newDishes, newItemsContainer);
});

function showItemPopup(item) {
    // Populate the modal with item details
    const modalImage = document.querySelector('#item-modal .modal-body img');
    const modalTitle = document.querySelector('#item-modal .modal-title');
    const modalIngredientsList = document.querySelector('#item-modal .modal-body ul');

    modalImage.src = `/static/images/${item.ImageFilename}`;
    modalImage.alt = item.FoodName;
    modalTitle.textContent = item.FoodName;

    // Clear existing ingredients
    modalIngredientsList.innerHTML = '';

    // Store modified ingredients
    let modifiedIngredients = [];

    // Add ingredients to the list
    const ingredients = item.Ingredients.split(','); // Assuming ingredients are comma-separated
    ingredients.forEach((ingredient, index) => {
        const li = document.createElement('li');
        li.classList.add('ingredient-item');

        // Minus button
        const minusBtn = document.createElement('button');
        minusBtn.textContent = '-';
        minusBtn.classList.add('btn', 'btn-minus');
        li.appendChild(minusBtn);

        // Ingredient name
        const span = document.createElement('span');
        span.textContent = ingredient.trim();
        span.classList.add('ingredient-name');
        li.appendChild(span);

        // Plus button
        const plusBtn = document.createElement('button');
        plusBtn.textContent = '+';
        plusBtn.classList.add('btn', 'btn-plus');
        li.appendChild(plusBtn);

        modalIngredientsList.appendChild(li);

        // Add event listeners for the buttons
        minusBtn.addEventListener('click', function () {
            handleIngredientChange(li, 'minus', index, modifiedIngredients);
        });

        plusBtn.addEventListener('click', function () {
            handleIngredientChange(li, 'plus', index, modifiedIngredients);
        });

        // Initially check the button states
        updateButtonStates(li);
    });

    // Add event listener to the "Add to Cart" button
    document.getElementById('modal-add-to-cart').addEventListener('click', function() {
        addToCart(item, modifiedIngredients);
    });

    // Show the modal
    $('#item-modal').modal('show');
}


function handleIngredientChange(li, action, index, modifiedIngredients) {
    if (action === 'minus') {
        if (li.classList.contains('extra')) {
            li.classList.remove('extra');
            modifiedIngredients[index] = 'default';
            updateButtonStates(li);
        } else if (!li.classList.contains('strikethrough')) {
            li.classList.add('strikethrough');
            modifiedIngredients[index] = 'remove';
            updateButtonStates(li);
        }
    } else if (action === 'plus') {
        if (li.classList.contains('strikethrough')) {
            li.classList.remove('strikethrough');
            modifiedIngredients[index] = 'default';
            updateButtonStates(li);
        } else if (!li.classList.contains('extra')) {
            li.classList.add('extra');
            modifiedIngredients[index] = 'add';
            updateButtonStates(li);
        }
    }
}


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


function addToCart(item, modifiedIngredients) {
    const cartItem = {
        id: item.FoodItemID,
        name: item.FoodName,
        price: item.Price,
        ingredients: modifiedIngredients,
    };

    // Store the cart item in session storage or send it to the server
    let cart = JSON.parse(sessionStorage.getItem('cart')) || [];
    cart.push(cartItem);
    sessionStorage.setItem('cart', JSON.stringify(cart));

    // Optionally, you can update the cart UI or redirect the user
    alert(`${item.FoodName} added to cart!`);
    $('#item-modal').modal('hide');
}
