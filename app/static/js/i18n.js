const TRANSLATIONS = {
    ka: {
        promotions: 'აქციები',
        categories: 'კატეგორიები',
        popular: 'პოპულარული',
        newDishes: 'ახალი კერძები',
        cart: 'კალათი',
        home: 'სახლი',
        close: 'დახურვა',
        addToCart: 'კალათაში',
        emptyCart: 'შენი კალათა ცარიელია',
        menu: 'მენიუ',
        clearConfirm: 'დარწმუნებული ხართ, რომ გსურთ კალათის გასუფთავება?',
        addedToCart: 'კალათაში დაემატა',
        discount: 'ფასდაკლება',
        promo: 'აქცია',
        commentPlaceholder: 'დაამატე კომენტარი...',
        extra: 'ექსტრა',
        without: 'გარეშე',
        comment: 'კომენტარი',
    },
    en: {
        promotions: 'Promotions',
        categories: 'Categories',
        popular: 'Popular',
        newDishes: 'New Dishes',
        cart: 'Cart',
        home: 'Home',
        close: 'Close',
        addToCart: 'Add to Cart',
        emptyCart: 'Your cart is empty',
        menu: 'Menu',
        clearConfirm: 'Are you sure you want to clear the cart?',
        addedToCart: 'added to cart',
        discount: 'discount',
        promo: 'Promo',
        commentPlaceholder: 'Add a comment...',
        extra: 'extra',
        without: 'without',
        comment: 'Comment',
    }
};

function getLang() {
    return localStorage.getItem('qr_menu_lang') || 'ka';
}

function setLang(lang) {
    localStorage.setItem('qr_menu_lang', lang);
    applyTranslations();
    updateLangButton();
}

function t(key) {
    const lang = getLang();
    return (TRANSLATIONS[lang] && TRANSLATIONS[lang][key]) || key;
}

function toggleLang() {
    setLang(getLang() === 'ka' ? 'en' : 'ka');
}

function updateLangButton() {
    const btn = document.getElementById('lang-toggle');
    if (btn) btn.textContent = getLang() === 'ka' ? 'EN' : 'ქარ';
}

function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = t(el.dataset.i18nPlaceholder);
    });
}

/* Dark mode */
function getTheme() {
    return localStorage.getItem('qr_menu_theme') || 'light';
}

function setTheme(theme) {
    localStorage.setItem('qr_menu_theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeButton();
}

function toggleTheme() {
    setTheme(getTheme() === 'light' ? 'dark' : 'light');
}

function updateThemeButton() {
    const btn = document.getElementById('theme-toggle');
    if (btn) {
        btn.innerHTML = getTheme() === 'light'
            ? '<i class="fas fa-moon"></i>'
            : '<i class="fas fa-sun"></i>';
    }
}

document.addEventListener('DOMContentLoaded', function () {
    // Apply saved theme
    document.documentElement.setAttribute('data-theme', getTheme());
    updateThemeButton();
    updateLangButton();
    applyTranslations();

    // Wire up buttons
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

    const langBtn = document.getElementById('lang-toggle');
    if (langBtn) langBtn.addEventListener('click', toggleLang);
});
