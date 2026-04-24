document.addEventListener('DOMContentLoaded', function () {
    const trashIcon = document.querySelector('.trash-icon');
    const cartContent = document.querySelector('.cart-content');
    const emptyCart = document.querySelector('.empty-cart');
    const cartKey = typeof getCartKey === 'function' ? getCartKey() : 'cart_default';
    let cart = JSON.parse(localStorage.getItem(cartKey)) || [];

    function render() {
        if (!cartContent || !emptyCart) return;
        cartContent.querySelectorAll('.cart-item').forEach(el => el.remove());

        if (cart.length === 0) {
            emptyCart.style.display = 'block';
        } else {
            emptyCart.style.display = 'none';
            cart.forEach(item => {
                const el = document.createElement('div');
                el.classList.add('cart-item');
                el.innerHTML = `
                    <img class="cart-item__img" src="/static/images/${item.imageFilename || 'default-image.png'}" alt="${item.name}">
                    <div class="cart-item__info">
                        <div class="cart-item__name">${item.name}</div>
                        <div class="cart-item__mods">${buildModTags(item)}</div>
                    </div>
                    <div class="cart-item__right">
                        <div class="cart-item__qty">
                            <button class="cart-item__qty-btn" data-action="decrease">−</button>
                            <span class="cart-item__qty-num">${item.quantity}</span>
                            <button class="cart-item__qty-btn" data-action="increase">+</button>
                        </div>
                        <div class="cart-item__price">₾${(item.price * item.quantity).toFixed(2)}</div>
                        <button class="cart-item__remove" aria-label="Remove"><i class="fas fa-times"></i></button>
                    </div>
                `;
                cartContent.appendChild(el);
                el.querySelector('[data-action="decrease"]').addEventListener('click', () => updateQty(item.id, item.ingredientKey, -1));
                el.querySelector('[data-action="increase"]').addEventListener('click', () => updateQty(item.id, item.ingredientKey, 1));
                el.querySelector('.cart-item__remove').addEventListener('click', () => removeItem(item.id, item.ingredientKey));
            });
        }
    }

    function buildModTags(item) {
        let html = '';
        if (Array.isArray(item.ingredients)) {
            item.ingredients.forEach(ing => {
                if (!ing) return;
                if (ing.action === 'remove') html += `<span class="cart-item__tag cart-item__tag--remove">✕ ${ing.name}</span>`;
                else if (ing.action === 'add') html += `<span class="cart-item__tag cart-item__tag--add">✦ ${ing.name}</span>`;
            });
        }
        if (item.comment) html += `<span class="cart-item__tag cart-item__tag--comment">💬 ${item.comment}</span>`;
        return html;
    }

    function updateQty(id, key, delta) {
        const item = cart.find(i => i.id === id && i.ingredientKey === key);
        if (!item) return;
        item.quantity = Math.max(1, item.quantity + delta);
        save();
    }

    function removeItem(id, key) {
        cart = cart.filter(i => !(i.id === id && i.ingredientKey === key));
        save();
    }

    function save() {
        localStorage.setItem(cartKey, JSON.stringify(cart));
        render();
        if (typeof updateCartItemCount === 'function') updateCartItemCount();
    }

    if (trashIcon) {
        trashIcon.addEventListener('click', function (e) {
            e.preventDefault();
            if (confirm(typeof t === 'function' ? t('clearConfirm') : 'Clear cart?')) {
                cart = [];
                save();
            }
        });
    }

    render();
});
