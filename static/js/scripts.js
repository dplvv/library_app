
// Анимация загрузки таблицы с книгами
document.addEventListener('DOMContentLoaded', () => {
    const tableRows = document.querySelectorAll('table tbody tr');
    tableRows.forEach((row, index) => {
        row.style.opacity = 0;
        setTimeout(() => {
            row.style.transition = 'opacity 0.5s ease-in-out';
            row.style.opacity = 1;
        }, index * 100); // Задержка между строками
    });
});

// Анимация переключения страниц
const paginationLinks = document.querySelectorAll('.pagination .page-link');
paginationLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const targetUrl = e.target.href;
        document.body.style.opacity = 0;
        setTimeout(() => {
            window.location.href = targetUrl;
        }, 300); // Задержка перед переходом
    });
});
