document.addEventListener('DOMContentLoaded', function() {
    const trashIcon = document.querySelector('.trash-icon');
    const cartContent = document.querySelector('.cart-content');
    const emptyCartMessage = document.querySelector('.empty-cart');

    // Retrieve cart items from sessionStorage
    let cart = JSON.parse(sessionStorage.getItem('cart')) || [];

    // Function to render the cart items
    function renderCartItems() {
        cartContent.innerHTML = ''; // Clear existing content

        if (cart.length === 0) {
            emptyCartMessage.style.display = 'block';
        } else {
            emptyCartMessage.style.display = 'none';

            cart.forEach(item => {
                const itemElement = document.createElement('div');
                itemElement.classList.add('cart-item');

                // Create the HTML structure for the cart item
                itemElement.innerHTML = `
                    <div class="cart-item-details">
                        <h5>${item.name}</h5>
                        <p>${item.ingredients.join(', ')}</p>
                        <p><strong>$${item.price}</strong></p>
                    </div>
                    <div class="cart-item-actions">
                        <button class="btn btn-sm btn-danger remove-item" data-item-id="${item.id}">Remove</button>
                    </div>
                `;

                // Add the item element to the cart content
                cartContent.appendChild(itemElement);

                // Add event listener for removing the item
                itemElement.querySelector('.remove-item').addEventListener('click', function() {
                    removeCartItem(item.id);
                });
            });
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
