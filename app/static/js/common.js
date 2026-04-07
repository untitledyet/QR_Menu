/**
 * Atomically replace container children without emptying it.
 * replaceChildren() is a single DOM operation — the container never
 * becomes empty, so the browser's scroll anchor is never lost.
 */

/**
 * Lock the page height to its current value so that scroll position
 * cannot change when content shrinks. Call before any DOM mutation.
 */
function lockPageHeight() {
    const shell = document.querySelector('.app-shell');
    if (!shell) return;
    shell.style.setProperty('--locked-height', document.documentElement.scrollHeight + 'px');
    shell.classList.add('app-shell--locked');
}

function unlockPageHeight() {
    const shell = document.querySelector('.app-shell');
    if (!shell) return;
    shell.classList.remove('app-shell--locked');
    shell.style.removeProperty('--locked-height');
}

function createItemCard(item) {
    const card = document.createElement('div');
    card.classList.add('food-card');
    card.innerHTML = `
        <img class="food-card__img" src="/static/images/${item.ImageFilename || 'default-image.png'}" alt="${item.FoodName || ''}">
        <div class="food-card__body">
            <div class="food-card__name">${item.FoodName || 'Unnamed'}</div>
            <div class="food-card__desc">${item.Ingredients || ''}</div>
            <div class="food-card__footer">
                <span class="food-card__price">₾${item.Price.toFixed(2)}</span>
                <button class="food-card__add" data-item-id="${item.FoodItemID}" aria-label="Add to cart">+</button>
            </div>
        </div>
    `;
    card.querySelector('.food-card__add').addEventListener('click', function (e) {
        e.stopPropagation();
        showItemPopup(item);
    });
    card.addEventListener('click', function () { showItemPopup(item); });
    return card;
}

function populateItemsContainer(dishes, container) {
    lockPageHeight();
    const newCards = dishes.map(dish => createItemCard(dish));
    container.replaceChildren(...newCards);
    requestAnimationFrame(() => unlockPageHeight());
}

function showLoadingSkeleton(container, count) {
    lockPageHeight();
    const skeletons = [];
    for (let i = 0; i < count; i++) {
        const skel = document.createElement('div');
        skel.classList.add('skeleton-card');
        skel.innerHTML = `
            <div class="skeleton-card__img"></div>
            <div class="skeleton-card__body">
                <div class="skeleton-card__line"></div>
                <div class="skeleton-card__line skeleton-card__line--short"></div>
                <div class="skeleton-card__line skeleton-card__line--price"></div>
            </div>
        `;
        skeletons.push(skel);
    }
    container.replaceChildren(...skeletons);
    requestAnimationFrame(() => unlockPageHeight());
}

function showItemPopup(item) {
    const modal = document.getElementById('item-modal');
    const modalImage = modal.querySelector('.modal-body img');
    const modalTitle = modal.querySelector('.modal-title');
    const modalList = modal.querySelector('.modal-body ul');

    modalImage.src = `/static/images/${item.ImageFilename || 'default-image.png'}`;
    modalImage.alt = item.FoodName || '';
    modalTitle.textContent = item.FoodName || '';
    modalList.innerHTML = '';
    modalList.classList.add('ingredients-list');

    const modifiedIngredients = [];
    const ingredients = item.Ingredients ? item.Ingredients.split(',') : [];
    const canCustomize = item.AllowCustomization !== false; // default true if field missing

    const removedLabel = typeof t === 'function' ? t('without') : 'without';
    const extraLabel = typeof t === 'function' ? t('extra') : 'extra';

    if (canCustomize) {
        ingredients.forEach((ingredient, index) => {
            if (!ingredient) return;
            const name = ingredient.trim();
            const li = document.createElement('li');
            li.classList.add('ingredient-item');
            li.innerHTML = `
                <span class="ingredient-name">${name}</span>
                <div class="ingredient-item__actions">
                    <button class="ing-btn ing-btn--remove" aria-label="Remove" title="${removedLabel}">−</button>
                    <button class="ing-btn ing-btn--extra" aria-label="Extra" title="${extraLabel}">+</button>
                </div>
            `;
            modalList.appendChild(li);

            const removeBtn = li.querySelector('.ing-btn--remove');
            const extraBtn = li.querySelector('.ing-btn--extra');

            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (li.classList.contains('ingredient-item--removed')) {
                    // Already removed → back to default
                    li.className = 'ingredient-item';
                    removeBtn.classList.remove('active');
                    modifiedIngredients[index] = { name, action: 'default' };
                } else {
                    // Default or extra → remove
                    li.className = 'ingredient-item ingredient-item--removed';
                    removeBtn.classList.add('active');
                    extraBtn.classList.remove('active');
                    modifiedIngredients[index] = { name, action: 'remove' };
                }
            });

            extraBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (li.classList.contains('ingredient-item--extra')) {
                    // Already extra → back to default
                    li.className = 'ingredient-item';
                    extraBtn.classList.remove('active');
                    modifiedIngredients[index] = { name, action: 'default' };
                } else {
                    // Default or removed → extra
                    li.className = 'ingredient-item ingredient-item--extra';
                    extraBtn.classList.add('active');
                    removeBtn.classList.remove('active');
                    modifiedIngredients[index] = { name, action: 'add' };
                }
            });
        });
    } else {
        // Read-only: show ingredients as inline tags
        const tagsLi = document.createElement('li');
        tagsLi.classList.add('ingredient-tags-readonly');
        tagsLi.innerHTML = ingredients
            .filter(i => i && i.trim())
            .map(i => `<span class="ingredient-tag-ro">${i.trim()}</span>`)
            .join('');
        modalList.appendChild(tagsLi);
    }

    const addBtn = document.getElementById('modal-add-to-cart');
    const newBtn = addBtn.cloneNode(true);
    addBtn.parentNode.replaceChild(newBtn, addBtn);

    const commentField = document.getElementById('item-comment');
    if (commentField) {
        commentField.value = '';
        commentField.placeholder = typeof t === 'function' ? t('commentPlaceholder') : 'Add a comment...';
    }

    newBtn.addEventListener('click', () => addToCart(item, modifiedIngredients));

    $('#item-modal').modal('show');
}

/**
 * Venue + table scoped cart key.
 * Each venue's each table has its own cart.
 * Uses localStorage so cart survives tab close/reopen.
 */
function getCartKey() {
    const slug = document.body.dataset.venue || 'default';
    const table = document.body.dataset.table || '0';
    return `cart_${slug}_${table}`;
}

function addToCart(item, modifiedIngredients) {
    let cart = JSON.parse(localStorage.getItem(getCartKey())) || [];
    const comment = (document.getElementById('item-comment')?.value || '').trim();

    const ingredientKey = item.FoodItemID + '-' +
        (modifiedIngredients.length > 0
            ? modifiedIngredients.sort((a, b) => a.name.localeCompare(b.name)).map(ing => `${ing.name}-${ing.action}`).join('|')
            : item.Ingredients ? item.Ingredients.split(',').sort().map(name => `${name.trim()}-default`).join('|') : 'default')
        + (comment ? '-c:' + comment : '');

    const existingIdx = cart.findIndex(c => c.id === item.FoodItemID && c.ingredientKey === ingredientKey);
    if (existingIdx !== -1) {
        cart[existingIdx].quantity += 1;
    } else {
        cart.push({
            id: item.FoodItemID, name: item.FoodName || 'Unnamed', price: item.Price,
            imageFilename: item.ImageFilename || 'default-image.png',
            ingredients: modifiedIngredients.length > 0 ? modifiedIngredients :
                (item.Ingredients ? item.Ingredients.split(',').map(n => ({ name: n.trim(), action: 'default' })) : []),
            quantity: 1, ingredientKey: ingredientKey,
            comment: comment
        });
    }
    localStorage.setItem(getCartKey(), JSON.stringify(cart));
    updateCartItemCount();
    showCartToast(item.FoodName || 'Item');
    $('#item-modal').modal('hide');
}

function showCartToast(itemName) {
    const toast = document.getElementById('cart-toast');
    if (!toast) return;
    toast.textContent = `${itemName} ${t('addedToCart')}`;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2000);
}

function updateCartItemCount() {
    const cart = JSON.parse(localStorage.getItem(getCartKey())) || [];
    const count = cart.reduce((t, i) => t + i.quantity, 0);
    const badge = document.querySelector('.cart-item-count');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'flex' : 'none';
        badge.classList.remove('bounce');
        void badge.offsetWidth;
        badge.classList.add('bounce');
    }
}

function setActiveNavTab() {
    const page = document.body.dataset.page;
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.nav === page);
    });
}

(function () {
    if (window._qrMenuInit) return;
    window._qrMenuInit = true;
    document.addEventListener('DOMContentLoaded', function () {
        const itemsContainer = document.getElementById('items-container');
        const newContainer = document.getElementById('new-dishes-container');
        try {
            const el = document.querySelector('#popular-dishes');
            if (el && itemsContainer) populateItemsContainer(JSON.parse(el.textContent), itemsContainer);
        } catch (e) { console.error('Popular dishes error:', e); }
        try {
            const el = document.querySelector('#new-dishes-data');
            if (el && newContainer) populateItemsContainer(JSON.parse(el.textContent), newContainer);
        } catch (e) { console.error('New dishes error:', e); }
        updateCartItemCount();
        setActiveNavTab();
    });
})();
