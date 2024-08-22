document.addEventListener('DOMContentLoaded', function() {
    const trashIcon = document.querySelector('.trash-icon');
    const cartContent = document.querySelector('.cart-content');
    const emptyCartMessage = document.querySelector('.empty-cart');

    // Retrieve cart items from sessionStorage
    let cart = JSON.parse(sessionStorage.getItem('cart')) || [];

    // Function to render the cart items
    function renderCartItems() {
        if (!cartContent || !emptyCartMessage) {
            console.error('Cart content or empty cart message element not found');
            return;
        }

        cartContent.innerHTML = ''; // Clear existing content

        if (cart.length === 0) {
            emptyCartMessage.style.display = 'block';
        } else {
            emptyCartMessage.style.display = 'none';

            cart.forEach(item => {
                const imageFilename = item.imageFilename ? item.imageFilename : 'default-image.png'; // Ensure the image exists
                const itemElement = document.createElement('div');
                itemElement.classList.add('cart-item', 'd-flex', 'align-items-center', 'justify-content-between', 'mb-3', 'p-3', 'border', 'rounded');

                // Create the HTML structure for the cart item
                itemElement.innerHTML = `
                    <div class="item-image">
                        <img src="/static/images/${imageFilename}" alt="${item.name || 'Item'}" class="img-fluid rounded">
                    </div>
                    <div class="item-details flex-grow-1">
                        <h5 class="item-name">${item.name || 'Unnamed Item'}</h5>
                        <p class="item-comment">${generateCommentText(item.ingredients || [])}</p>
                    </div>
                    <div class="item-quantity d-flex align-items-center">
                        <button class="btn btn-sm btn-outline-secondary quantity-decrease" data-item-id="${item.id}">-</button>
                        <input type="number" class="quantity-value" value="${item.quantity || 1}" min="1" data-item-id="${item.id}">
                        <button class="btn btn-sm btn-outline-secondary quantity-increase" data-item-id="${item.id}">+</button>
                    </div>
                    <div class="cart-item-price">
                        <strong>$${(item.price * (item.quantity || 1)).toFixed(2)}</strong>
                    </div>
                    <div class="cart-item-actions">
                        <button class="btn btn-sm btn-danger remove-item" data-item-id="${item.id}">Remove</button>
                    </div>
                `;

                // Add the item element to the cart content
                cartContent.appendChild(itemElement);

                // Add event listeners for quantity buttons and remove button
                itemElement.querySelector('.quantity-decrease').addEventListener('click', function() {
                    updateItemQuantity(item.id, 'decrease');
                });

                itemElement.querySelector('.quantity-increase').addEventListener('click', function() {
                    updateItemQuantity(item.id, 'increase');
                });

                itemElement.querySelector('.remove-item').addEventListener('click', function() {
                    removeCartItem(item.id);
                });
            });
        }
    }

    // Function to generate comment text based on modified ingredients
    function generateCommentText(ingredients) {
        if (!Array.isArray(ingredients) || ingredients.length === 0) {
            return "No ingredients specified";
        }

        return ingredients.map(ingredient => {
            if (!ingredient) return "";
            if (ingredient.action === 'remove') {
                return `remove: ${ingredient.name}`;
            } else if (ingredient.action === 'add') {
                return `add: ${ingredient.name}`;
            } else {
                return `${ingredient.name}`;
            }
        }).join(', ');
    }

    // Function to update item quantity by increment/decrement
    function updateItemQuantity(itemId, action) {
        const cartItem = cart.find(item => item.id === itemId);
        if (cartItem) {
            if (action === 'decrease' && cartItem.quantity > 1) {
                cartItem.quantity -= 1;
            } else if (action === 'increase') {
                cartItem.quantity += 1;
            }
            sessionStorage.setItem('cart', JSON.stringify(cart));
            renderCartItems();
        }
    }

    // Function to remove an item from the cart
    function removeCartItem(itemId) {
        cart = cart.filter(item => item.id !== itemId);
        sessionStorage.setItem('cart', JSON.stringify(cart));
        renderCartItems(); // Re-render the cart after removing the item
    }

    // Clear cart event
    if (trashIcon) {
        trashIcon.addEventListener('click', function() {
            if (confirm('დარწმუნებული ხართ, რომ გსურთ კალათის გასუფთავება?')) {
                cart = [];
                sessionStorage.setItem('cart', JSON.stringify(cart));
                renderCartItems(); // Re-render the cart after clearing it
            }
        });
    }

    // Initial render of cart items
    renderCartItems();
});
