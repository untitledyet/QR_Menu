function fetchSubcategoryData(subcategoryId) {
    const slug = document.body.dataset.venue || 'demo';
    return fetch(`/${slug}/subcategory/${subcategoryId}`).then(r => r.json());
}

function createSubcategoryCard(subcategory, categoryId) {
    const btn = document.createElement('button');
    btn.classList.add('sub-pill');
    btn.dataset.subcategoryId = subcategory.SubcategoryID;
    btn.dataset.nameKa = subcategory.SubcategoryName;
    btn.dataset.nameEn = subcategory.SubcategoryName_en || subcategory.SubcategoryName;
    const lang = typeof getLang === 'function' ? getLang() : 'ka';
    btn.textContent = (lang === 'en' && subcategory.SubcategoryName_en) ? subcategory.SubcategoryName_en : subcategory.SubcategoryName;
    btn.addEventListener('click', () => handleSubcategoryClick(btn, categoryId));
    return btn;
}

function populateSubcategoriesContainer(subcategories, categoryId, container) {
    lockPageHeight();
    if (subcategories.length > 0) {
        const wrapper = document.createElement('div');
        wrapper.classList.add('sub-pills');
        subcategories.forEach(sub => wrapper.appendChild(createSubcategoryCard(sub, categoryId)));
        container.replaceChildren(wrapper);
    } else {
        container.replaceChildren();
    }
    requestAnimationFrame(() => unlockPageHeight());
}

function handleSubcategoryClick(card, categoryId) {
    const subcategoryId = card.dataset.subcategoryId;
    const isActive = card.classList.contains('active');
    const itemsContainer = document.getElementById('items-container');

    document.querySelectorAll('.sub-pill').forEach(c => c.classList.remove('active'));

    lockPageHeight();
    showLoadingSkeleton(itemsContainer, 4);

    if (!isActive) {
        card.classList.add('active');
        fetchSubcategoryData(subcategoryId).then(data => {
            lockPageHeight();
            populateItemsContainer(data.items, itemsContainer);
            requestAnimationFrame(() => unlockPageHeight());
        });
    } else {
        fetchCategoryData(categoryId).then(data => {
            lockPageHeight();
            populateItemsContainer(data.items, itemsContainer);
            requestAnimationFrame(() => unlockPageHeight());
        });
    }
}
