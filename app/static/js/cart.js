document.addEventListener('DOMContentLoaded', function() {
    const trashIcon = document.querySelector('.trash-icon');
    if (trashIcon) {
        trashIcon.addEventListener('click', function() {
            if (confirm('დარწმუნებული ხართ, რომ გსურთ კალათის გასუფთავება?')) {
                // კალათის გასუფთავების ფუნქცია
            }
        });
    }
});
