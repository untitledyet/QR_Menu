document.addEventListener('DOMContentLoaded', function () {
    function fetchCategoryData(categoryId) {
        return fetch(`/category/${categoryId}`).then(response => response.json());
    }

    function fetchSubcategoryData(subcategoryId) {
        return fetch(`/subcategory/${subcategoryId}`).then(response => response.json());
    }

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
                </div>
            </div>
        `;
        return itemCard;
    }

    function populateItemsContainer(items, container) {
        container.innerHTML = '';
        items.forEach(item => {
            container.appendChild(createItemCard(item));
        });
    }

    function createSubcategoryCard(subcategory, categoryId) {
        const subcategoryCard = document.createElement('button');
        subcategoryCard.classList.add('subcategory-card', 'btn', 'mr-2', 'mb-2');
        subcategoryCard.dataset.subcategoryId = subcategory.SubcategoryID;
        subcategoryCard.textContent = subcategory.SubcategoryName;
        subcategoryCard.addEventListener('click', function () {
            handleSubcategoryClick(this, categoryId);
        });
        return subcategoryCard;
    }

    function populateSubcategoriesContainer(subcategories, categoryId, container) {
        container.innerHTML = '';
        if (subcategories.length > 0) {
            const subcategoriesWrapper = document.createElement('div');
            subcategoriesWrapper.classList.add('subcategories');

            subcategories.forEach(sub => {
                subcategoriesWrapper.appendChild(createSubcategoryCard(sub, categoryId));
            });

            container.appendChild(subcategoriesWrapper);
        }
    }

    function handleCategoryClick(card, categoryCards, itemsContainer, sectionTitle, subcategoriesContainer) {
        const isActive = card.classList.contains('active');
        categoryCards.forEach(card => card.classList.remove('active'));

        if (!isActive) {
            card.classList.add('active');
            const categoryId = card.dataset.categoryId;
            const categoryName = card.dataset.categoryName;

            fetchCategoryData(categoryId)
                .then(data => {
                    sectionTitle.textContent = `${categoryName}`;
                    populateItemsContainer(data.items, itemsContainer);
                    populateSubcategoriesContainer(data.subcategories, categoryId, subcategoriesContainer);
                })
                .catch(error => console.error('Error:', error));
        } else {
            resetMainContent();
        }
    }

    function handleSubcategoryClick(card, categoryId) {
        const subcategoryId = card.dataset.subcategoryId;
        const isSubcategoryActive = card.classList.contains('active');
        document.querySelectorAll('.subcategory-card').forEach(card => card.classList.remove('active'));

        if (!isSubcategoryActive) {
            card.classList.add('active');
            fetchSubcategoryData(subcategoryId)
                .then(data => {
                    const itemsContainer = document.getElementById('items-container');
                    populateItemsContainer(data.items, itemsContainer);
                })
                .catch(error => console.error('Error:', error));
        } else {
            fetchCategoryData(categoryId)
                .then(data => {
                    const itemsContainer = document.getElementById('items-container');
                    populateItemsContainer(data.items, itemsContainer);
                })
                .catch(error => console.error('Error:', error));
        }
    }

    function resetMainContent() {
        fetch(`/`)
            .then(response => response.text())
            .then(html => {
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = html;

                document.querySelector('.category-scroll').innerHTML = tempDiv.querySelector('.category-scroll').innerHTML;
                document.getElementById('items-container').innerHTML = tempDiv.querySelector('#items-container').innerHTML;
                document.getElementById('section-title').textContent = tempDiv.querySelector('#section-title').textContent;
                document.querySelector('.subcategories-container').innerHTML = tempDiv.querySelector('.subcategories-container').innerHTML;

                initializeCategoryCards();
            })
            .catch(error => console.error('Error:', error));
    }

    function initializeCategoryCards() {
        const categoryCards = document.querySelectorAll('.category-card');
        const itemsContainer = document.getElementById('items-container');
        const sectionTitle = document.getElementById('section-title');
        const subcategoriesContainer = document.querySelector('.subcategories-container');

        categoryCards.forEach(card => {
            card.addEventListener('click', function () {
                handleCategoryClick(this, categoryCards, itemsContainer, sectionTitle, subcategoriesContainer);
            });
        });
    }

    initializeCategoryCards();
});
