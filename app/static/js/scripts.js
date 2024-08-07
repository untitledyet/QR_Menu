document.addEventListener('DOMContentLoaded', function() {
    function initializeCategoryCards() {
        const categoryCards = document.querySelectorAll('.category-card');
        const itemsContainer = document.getElementById('items-container');
        const sectionTitle = document.getElementById('section-title');
        const subcategoriesContainer = document.querySelector('.subcategories-container');

        categoryCards.forEach(card => {
            card.addEventListener('click', function() {
                const isActive = this.classList.contains('active');
                categoryCards.forEach(card => card.classList.remove('active'));

                if (!isActive) {
                    this.classList.add('active');
                    const categoryId = this.dataset.categoryId;
                    const categoryName = this.dataset.categoryName;
                    fetch(`/category/${categoryId}`)
                        .then(response => response.json())
                        .then(data => {
                            itemsContainer.innerHTML = '';
                            subcategoriesContainer.innerHTML = '';
                            sectionTitle.textContent = `${categoryName} Dishes`;

                            if (data.subcategories.length > 0) {
                                const subcategoriesWrapper = document.createElement('div');
                                subcategoriesWrapper.classList.add('subcategories');

                                data.subcategories.forEach(sub => {
                                    const subcategoryCard = document.createElement('button');
                                    subcategoryCard.classList.add('subcategory-card', 'btn', 'btn-light', 'mr-2', 'mb-2');
                                    subcategoryCard.dataset.subcategoryId = sub.SubcategoryID;
                                    subcategoryCard.textContent = sub.SubcategoryName.toLowerCase();
                                    subcategoryCard.addEventListener('click', function() {
                                        const subcategoryId = this.dataset.subcategoryId;
                                        const isSubcategoryActive = this.classList.contains('active');
                                        document.querySelectorAll('.subcategory-card').forEach(card => card.classList.remove('active'));

                                        if (!isSubcategoryActive) {
                                            this.classList.add('active');
                                            fetch(`/subcategory/${subcategoryId}`)
                                                .then(response => response.json())
                                                .then(data => {
                                                    itemsContainer.innerHTML = '';
                                                    data.items.forEach(item => {
                                                        const itemCard = document.createElement('div');
                                                        itemCard.classList.add('col-12', 'col-sm-6', 'col-lg-4', 'mb-4');
                                                        itemCard.innerHTML = `
                                                            <div class="card shadow-sm">
                                                                <img src="/static/images/${item.ImageFilename}" class="card-img-top" alt="${item.FoodName}">
                                                                <div class="card-body">
                                                                    <h5 class="card-title">${item.FoodName}</h5>
                                                                    <p class="card-text">${item.Description}</p>
                                                                    <p class="card-text"><strong>$${item.Price}</strong></p>
                                                                </div>
                                                            </div>
                                                        `;
                                                        itemsContainer.appendChild(itemCard);
                                                    });
                                                })
                                                .catch(error => console.error('Error:', error));
                                        } else {
                                            // Reset to the main category items
                                            fetch(`/category/${categoryId}`)
                                                .then(response => response.json())
                                                .then(data => {
                                                    itemsContainer.innerHTML = '';
                                                    data.items.forEach(item => {
                                                        const itemCard = document.createElement('div');
                                                        itemCard.classList.add('col-12', 'col-sm-6', 'col-lg-4', 'mb-4');
                                                        itemCard.innerHTML = `
                                                            <div class="card shadow-sm">
                                                                <img src="/static/images/${item.ImageFilename}" class="card-img-top" alt="${item.FoodName}">
                                                                <div class="card-body">
                                                                    <h5 class="card-title">${item.FoodName}</h5>
                                                                    <p class="card-text">${item.Description}</p>
                                                                    <p class="card-text"><strong>$${item.Price}</strong></p>
                                                                </div>
                                                            </div>
                                                        `;
                                                        itemsContainer.appendChild(itemCard);
                                                    });
                                                })
                                                .catch(error => console.error('Error:', error));
                                        }
                                    });
                                    subcategoriesWrapper.appendChild(subcategoryCard);
                                });

                                subcategoriesContainer.appendChild(subcategoriesWrapper);
                            }

                            data.items.forEach(item => {
                                const itemCard = document.createElement('div');
                                itemCard.classList.add('col-12', 'col-sm-6', 'col-lg-4', 'mb-4');
                                itemCard.innerHTML = `
                                    <div class="card shadow-sm">
                                        <img src="/static/images/${item.ImageFilename}" class="card-img-top" alt="${item.FoodName}">
                                        <div class="card-body">
                                            <h5 class="card-title">${item.FoodName}</h5>
                                            <p class="card-text">${item.Description}</p>
                                            <p class="card-text"><strong>$${item.Price}</strong></p>
                                        </div>
                                    </div>
                                `;
                                itemsContainer.appendChild(itemCard);
                            });
                        })
                        .catch(error => console.error('Error:', error));
                } else {
                    // Reset to the main content
                    fetch(`/`)
                        .then(response => response.text())
                        .then(html => {
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = html;

                            const newCategories = tempDiv.querySelector('.category-scroll').innerHTML;
                            const newItemsContainer = tempDiv.querySelector('#items-container').innerHTML;
                            const newSectionTitle = tempDiv.querySelector('#section-title').textContent;
                            const newSubcategoriesContainer = tempDiv.querySelector('.subcategories-container').innerHTML;

                            document.querySelector('.category-scroll').innerHTML = newCategories;
                            document.getElementById('items-container').innerHTML = newItemsContainer;
                            document.getElementById('section-title').textContent = newSectionTitle;
                            document.querySelector('.subcategories-container').innerHTML = newSubcategoriesContainer;

                            initializeCategoryCards();
                        })
                        .catch(error => console.error('Error:', error));
                }
            });
        });
    }

    initializeCategoryCards();
});
