// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function () {

    /**
     * Fetch data for a specific category by its ID
     * @param {number} categoryId - The ID of the category to fetch data for
     * @returns {Promise} - A promise that resolves to the category data
     */
    function fetchCategoryData(categoryId) {
        return fetch(`/category/${categoryId}`).then(response => response.json());
    }

    /**
     * Fetch data for a specific subcategory by its ID
     * @param {number} subcategoryId - The ID of the subcategory to fetch data for
     * @returns {Promise} - A promise that resolves to the subcategory data
     */
    function fetchSubcategoryData(subcategoryId) {
        return fetch(`/subcategory/${subcategoryId}`).then(response => response.json());
    }

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
                </div>
            </div>
        `;
        return itemCard;
    }

    /**
     * Populate the items container with a list of item cards
     * @param {Array} items - The list of items to display
     * @param {HTMLElement} container - The container to populate
     */
    function populateItemsContainer(items, container) {
        container.innerHTML = '';
        items.forEach(item => {
            container.appendChild(createItemCard(item));
        });
    }

    /**
     * Create a subcategory button element
     * @param {Object} subcategory - The subcategory data
     * @param {number} categoryId - The ID of the parent category
     * @returns {HTMLElement} - The subcategory button element
     */
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

    /**
     * Populate the subcategories container with a list of subcategory buttons
     * @param {Array} subcategories - The list of subcategories to display
     * @param {number} categoryId - The ID of the parent category
     * @param {HTMLElement} container - The container to populate
     */
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

    /**
     * Handle click event for category cards
     * @param {HTMLElement} card - The category card that was clicked
     * @param {NodeList} categoryCards - The list of all category cards
     * @param {HTMLElement} itemsContainer - The container to populate with items
     * @param {HTMLElement} sectionTitle - The section title element to update
     * @param {HTMLElement} subcategoriesContainer - The container to populate with subcategories
     */
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

    /**
     * Handle click event for subcategory buttons
     * @param {HTMLElement} card - The subcategory button that was clicked
     * @param {number} categoryId - The ID of the parent category
     */
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

    /**
     * Reset the main content to the default view
     */
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

    /**
     * Initialize category card click events
     */
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

    /**
     * Initialize the promotion carousel
     * Adds event listeners for scrolling and updates UI elements accordingly
     */
    function initializePromotionCarousel() {
        const promotionScroll = document.querySelector('.promotion-scroll');
        const prevButton = document.querySelector('.carousel-control-prev');
        const nextButton = document.querySelector('.carousel-control-next');

        prevButton.addEventListener('click', () => {
            promotionScroll.scrollBy({ left: -300, behavior: 'smooth' });
        });

        nextButton.addEventListener('click', () => {
            promotionScroll.scrollBy({ left: 300, behavior: 'smooth' });
        });

        // Update button states based on scroll position
        promotionScroll.addEventListener('scroll', () => {
            const scrollLeft = promotionScroll.scrollLeft;
            const maxScrollLeft = promotionScroll.scrollWidth - promotionScroll.clientWidth;

            prevButton.disabled = scrollLeft === 0;
            nextButton.disabled = scrollLeft >= maxScrollLeft;
        });

        // Initial state update
        promotionScroll.dispatchEvent(new Event('scroll'));
    }

    // Initialize category cards
    initializeCategoryCards();

    // Initialize promotion carousel
    initializePromotionCarousel();
});
