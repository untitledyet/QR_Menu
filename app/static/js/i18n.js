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
        // Reservation keys
        reservations: 'ჯავშნები',
        bookTable: 'მაგიდის დაჯავშნა',
        selectDate: 'აირჩიეთ თარიღი',
        selectTime: 'აირჩიეთ დრო',
        guestCount: 'სტუმრების რაოდენობა',
        availableTables: 'ხელმისაწვდომი მაგიდები',
        reserved: 'დაჯავშნილი',
        available: 'ხელმისაწვდომი',
        bookNow: 'დაჯავშნე',
        pendingPayment: 'გადახდის მოლოდინში',
        confirmed: 'დადასტურებული',
        cancelled: 'გაუქმებული',
        noTablesAvailable: 'მაგიდები არ არის ხელმისაწვდომი',
        bookingSuccess: 'ჯავშანი წარმატებით შეიქმნა',
        myBookings: 'ჩემი ჯავშნები',
        cancelBooking: 'ჯავშნის გაუქმება',
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
        // Reservation keys
        reservations: 'Reservations',
        bookTable: 'Book a Table',
        selectDate: 'Select Date',
        selectTime: 'Select Time',
        guestCount: 'Number of Guests',
        availableTables: 'Available Tables',
        reserved: 'Reserved',
        available: 'Available',
        bookNow: 'Book Now',
        pendingPayment: 'Pending Payment',
        confirmed: 'Confirmed',
        cancelled: 'Cancelled',
        noTablesAvailable: 'No tables available',
        bookingSuccess: 'Booking created successfully',
        myBookings: 'My Bookings',
        cancelBooking: 'Cancel Booking',
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
    const lang = getLang();
    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    // Dynamic content: category chip names, item card names/ingredients, subcategory pills
    document.querySelectorAll('[data-ka][data-en]').forEach(el => {
        el.textContent = lang === 'en' ? (el.dataset.en || el.dataset.ka) : el.dataset.ka;
    });
    // Sub-pills rendered by JS
    document.querySelectorAll('.sub-pill[data-name-ka]').forEach(btn => {
        btn.textContent = lang === 'en' ? (btn.dataset.nameEn || btn.dataset.nameKa) : btn.dataset.nameKa;
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
