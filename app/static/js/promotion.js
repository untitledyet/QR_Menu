function fetchPromotionDetails(promotionId) {
    const slug = document.body.dataset.venue || 'demo';
    return fetch(`/${slug}/promotion/${promotionId}`).then(r => r.text());
}

function handlePromotionClick(card, promotionId) {
    const detailContainer = document.getElementById('promotion-detail-container');
    const isAlreadyActive = detailContainer.dataset.activePromotionId === promotionId.toString();

    if (isAlreadyActive) {
        detailContainer.innerHTML = '';
        detailContainer.removeAttribute('data-active-promotion-id');
    } else {
        fetchPromotionDetails(promotionId).then(data => {
            detailContainer.innerHTML = data;
            detailContainer.dataset.activePromotionId = promotionId;

            const closeButton = detailContainer.querySelector('.close-button');
            if (closeButton) {
                closeButton.addEventListener('click', function () {
                    detailContainer.innerHTML = '';
                    detailContainer.removeAttribute('data-active-promotion-id');
                });
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.promo-card').forEach(card => {
        card.addEventListener('click', function () {
            const promotionId = this.dataset.promotionId;
            if (promotionId) handlePromotionClick(this, promotionId);
        });
    });

    initPromoDots();
});

function initPromoDots() {
    const grid = document.querySelector('.promo-grid');
    const cards = grid ? grid.querySelectorAll('.promo-card') : [];
    if (!grid || cards.length < 2) return;

    const dotsContainer = document.createElement('div');
    dotsContainer.classList.add('promo-dots');
    cards.forEach((_, i) => {
        const dot = document.createElement('span');
        dot.classList.add('promo-dot');
        if (i === 0) dot.classList.add('active');
        dot.addEventListener('click', () => {
            cards[i].scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'start' });
        });
        dotsContainer.appendChild(dot);
    });
    grid.parentNode.insertBefore(dotsContainer, grid.nextSibling);

    const dots = dotsContainer.querySelectorAll('.promo-dot');

    grid.addEventListener('scroll', function () {
        const scrollLeft = grid.scrollLeft;
        const maxScroll = grid.scrollWidth - grid.clientWidth;

        // If scrolled to the end, activate last dot
        if (maxScroll - scrollLeft < 2) {
            dots.forEach((dot, i) => dot.classList.toggle('active', i === cards.length - 1));
            return;
        }

        // Find which card is most visible
        let activeIndex = 0;
        let minDistance = Infinity;
        cards.forEach((card, i) => {
            const cardLeft = card.offsetLeft - grid.offsetLeft;
            const distance = Math.abs(scrollLeft - cardLeft);
            if (distance < minDistance) {
                minDistance = distance;
                activeIndex = i;
            }
        });

        dots.forEach((dot, i) => dot.classList.toggle('active', i === activeIndex));
    });
}
