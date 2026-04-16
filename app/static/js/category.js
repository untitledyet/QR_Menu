let initialPopularDishes = [];
let initialNewDishes = [];

document.addEventListener('DOMContentLoaded', function () {
    try {
        const el = document.querySelector('#popular-dishes');
        if (el) initialPopularDishes = JSON.parse(el.textContent);
    } catch (e) {}
    try {
        const el = document.querySelector('#new-dishes-data');
        if (el) initialNewDishes = JSON.parse(el.textContent);
    } catch (e) {}
    initializeCategoryCards();
});

function fetchCategoryData(categoryId) {
    const slug = document.body.dataset.venue || 'demo';
    return fetch(`/${slug}/category/${categoryId}`).then(r => r.json());
}

function restoreInitialState(itemsContainer, sectionTitle, subcategoriesContainer) {
    lockPageHeight();
    sectionTitle.textContent = t('popular');
    populateItemsContainer(initialPopularDishes, itemsContainer);
    subcategoriesContainer.replaceChildren();
    const newContainer = document.getElementById('new-dishes-container');
    const newTitle = document.getElementById('new-dishes-title');
    if (newContainer && newTitle) {
        newTitle.style.visibility = '';
        populateItemsContainer(initialNewDishes, newContainer);
    }
    requestAnimationFrame(() => unlockPageHeight());
}

function handleCategoryClick(card, categoryCards, itemsContainer, sectionTitle, subcategoriesContainer) {
    const isActive = card.classList.contains('active');
    categoryCards.forEach(c => c.classList.remove('active'));

    if (!isActive) {
        card.classList.add('active');
        const categoryId = card.dataset.categoryId;
        const lang = typeof getLang === 'function' ? getLang() : 'ka';
        const categoryName = (lang === 'en' && card.dataset.categoryNameEn)
            ? card.dataset.categoryNameEn : card.dataset.categoryName;

        lockPageHeight();
        showLoadingSkeleton(itemsContainer, 4);

        fetchCategoryData(categoryId).then(data => {
            lockPageHeight();
            sectionTitle.textContent = categoryName;
            populateItemsContainer(data.items, itemsContainer);
            populateSubcategoriesContainer(data.subcategories, categoryId, subcategoriesContainer);
            const newContainer = document.getElementById('new-dishes-container');
            const newTitle = document.getElementById('new-dishes-title');
            if (newContainer) newContainer.replaceChildren();
            if (newTitle) newTitle.style.visibility = 'hidden';
            requestAnimationFrame(() => unlockPageHeight());
        });
    } else {
        restoreInitialState(itemsContainer, sectionTitle, subcategoriesContainer);
    }
}

function initializeCategoryCards() {
    const cards = document.querySelectorAll('.cat-chip');
    const itemsContainer = document.getElementById('items-container');
    const sectionTitle = document.getElementById('section-title');
    const subcategoriesContainer = document.querySelector('.subcategories-container');
    cards.forEach(card => {
        card.addEventListener('click', function () {
            handleCategoryClick(this, cards, itemsContainer, sectionTitle, subcategoriesContainer);
        });
    });
}
