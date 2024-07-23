document.addEventListener('DOMContentLoaded', function() {
    const categoryCards = document.querySelectorAll('.category-card');
    const itemsContainer = document.getElementById('items-container');
    const sectionTitle = document.getElementById('section-title');

    categoryCards.forEach(card => {
        card.addEventListener('click', function() {
            const categoryId = this.dataset.categoryId;
            const categoryName = this.dataset.categoryName;
            fetch(`/category/${categoryId}`)
                .then(response => response.json())
                .then(data => {
                    itemsContainer.innerHTML = '';
                    sectionTitle.textContent = `${categoryName} Dishes`;
                    data.forEach(item => {
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
        });
    });
});
