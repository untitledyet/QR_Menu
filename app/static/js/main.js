/**
 * General functions to be used across the website
 */

document.addEventListener('DOMContentLoaded', function () {
    updateCartItemCount();

    // Any other general initialization code can go here
});

/**
 * Update the cart item count display on the cart icon
 */
function updateCartItemCount() {
    const cart = JSON.parse(sessionStorage.getItem('cart')) || [];
    const cartItemCount = cart.reduce((total, item) => total + item.quantity, 0);
    const cartItemCountElement = document.querySelector('.cart-item-count');

    if (cartItemCountElement) {
        cartItemCountElement.textContent = cartItemCount;
    } else {
        console.warn('Cart item count element not found.');
    }
}

/**
 * Utility function to handle errors globally
 * @param {Error} error - The error object
 */
function handleError(error) {
    console.error('An error occurred:', error);
    alert('An unexpected error occurred. Please try again later.');
}
